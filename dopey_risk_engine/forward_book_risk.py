"""Forward-book risk: portfolio Greeks + PnL attribution for the ex-ante paper book.

Two lenses on the forward-walk ledger, both computed only from REAL staged quotes:

1. BOOK GREEKS - every open position is re-priced against the latest validated
   chain snapshot; per-position and aggregate dollar Greeks (delta$, gamma$ per
   1% spot move, vega$ per vol point, theta$ per day) plus symbol/sector premium
   concentration. Positions whose contract is absent from the latest snapshot
   are flagged unmarkable, never silently carried at stale Greeks.

2. PNL ATTRIBUTION - each open position's unrealized move is decomposed into
   direction (delta+gamma on the real spot move), volatility (vega on the real
   IV change), decay (theta on calendar days held), friction (measured entry
   half-spread + latent exit half-spread + commissions), and a residual. The
   decomposition satisfies an exact identity against the ledger's bid-side
   unrealized PnL, so the buckets always sum to the truth.

This explains WHY the paper book is up or down - spread, direction, vol, or
decay - instead of reporting a bare number. Paper-only, live-blocked; no
sizing, no orders, nothing here can transact.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from dopey_analysis.market_context_fusion import SECTOR_MAP
from dopey_options.chain_snapshot_loader import load_latest_chain_snapshot
from dopey_options.greeks_engine import bs_greeks
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
BOOK_RISK_DIR = REPO_ROOT / "artifacts" / "dopey" / "forward_book_risk"
BOOK_RISK_PATH = BOOK_RISK_DIR / "forward_book_risk.json"
POSITION_RISK_PATH = BOOK_RISK_DIR / "position_risk_rows.jsonl"
BOOK_RISK_REPORT_PATH = REPORTS_DIR / "DOPEY_FORWARD_BOOK_RISK_REPORT.md"

from dopey_options.risk_free_rate import resolve_risk_free_rate

RISK_FREE_RATE, RISK_FREE_SOURCE = resolve_risk_free_rate()
COMMISSION_PREMIUM_UNITS = 0.0065
CONTRACT_MULTIPLIER = 100.0


def year_fraction(earlier: str, later: str) -> float:
    """Calendar-day year fraction between two ISO dates; never negative."""
    try:
        days = (date.fromisoformat(later) - date.fromisoformat(earlier)).days
    except ValueError:
        return 0.0
    return max(days, 0) / 365.0


def dollar_greeks(greeks: dict[str, float], spot: float) -> dict[str, float]:
    """Per-share BS greeks -> per-contract dollar exposures (1 long contract)."""
    return {
        "delta_dollars": round(greeks["delta"] * spot * CONTRACT_MULTIPLIER, 2),
        "gamma_dollars_per_1pct": round(greeks["gamma"] * 0.01 * spot * spot * CONTRACT_MULTIPLIER, 2),
        "vega_dollars_per_vol_pt": round(greeks["vega"] * CONTRACT_MULTIPLIER, 2),
        "theta_dollars_per_day": round(greeks["theta"] * CONTRACT_MULTIPLIER, 2),
    }


def attribute_open_position(position: dict[str, Any], row: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Decompose a position's bid-side unrealized PnL (premium units per share).

    Identity: unrealized = (direction + volatility + decay + residual) - friction,
    where direction+volatility+decay+residual == mid-to-mid move exactly.
    """
    entry_spot = float(position["entry_spot"])
    entry_iv = float(position["entry_iv"])
    entry_bid = float(position["entry_bid"])
    entry_ask = float(position["entry_ask"])
    entry_fill = float(position["entry_fill"])
    entry_mid = (entry_bid + entry_ask) / 2.0
    strike = float(position["strike"])
    option_type = str(position["option_type"])
    expiry = str(position["expiry"])
    entry_date = str(position["entry_date"])

    spot_now = float(row["underlying_spot"])
    iv_now = float(row["implied_vol"])
    bid_now = float(row["bid"])
    ask_now = float(row["ask"])
    mid_now = (bid_now + ask_now) / 2.0

    entry_greeks = bs_greeks(entry_spot, strike, year_fraction(entry_date, expiry), RISK_FREE_RATE, entry_iv, option_type)
    spot_move = spot_now - entry_spot
    iv_move_pts = (iv_now - entry_iv) * 100.0
    days_held = max((date.fromisoformat(as_of) - date.fromisoformat(entry_date)).days, 0)

    direction = entry_greeks["delta"] * spot_move + 0.5 * entry_greeks["gamma"] * spot_move * spot_move
    volatility = entry_greeks["vega"] * iv_move_pts
    decay = entry_greeks["theta"] * days_held
    mid_move = mid_now - entry_mid
    residual = mid_move - (direction + volatility + decay)

    entry_half_spread = entry_ask - entry_mid
    exit_half_spread_latent = mid_now - bid_now
    friction = entry_half_spread + exit_half_spread_latent + 2.0 * COMMISSION_PREMIUM_UNITS
    unrealized = (bid_now - COMMISSION_PREMIUM_UNITS) - entry_fill

    return {
        "position_id": str(position["position_id"]),
        "symbol": str(position["symbol"]),
        "candidate_strategy": str(position["candidate_strategy"]),
        "days_held": days_held,
        "direction_pnl": round(direction, 6),
        "volatility_pnl": round(volatility, 6),
        "decay_pnl": round(decay, 6),
        "residual_pnl": round(residual, 6),
        "friction_cost": round(friction, 6),
        "mid_move": round(mid_move, 6),
        "unrealized_pnl_bid_side": round(unrealized, 6),
        "attribution_identity_gap": round(unrealized - (mid_move - friction), 6),
        "quote_derived": True,
    }


def run_forward_book_risk() -> dict[str, Any]:
    snapshot = load_latest_chain_snapshot()
    if snapshot["chain_snapshot_status"] != "real_chain_snapshot_validated":
        summary = _base(snapshot["chain_snapshot_status"])
        _write_json(BOOK_RISK_PATH, summary)
        return summary
    if not LEDGER_PATH.exists():
        summary = _base("blocked_missing_forward_ledger")
        _write_json(BOOK_RISK_PATH, summary)
        return summary
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    open_positions = list(ledger.get("open_positions", []))
    as_of = str(snapshot["snapshot_date"])
    rows_by_contract = {
        (row["symbol"], row["expiry"], row["option_type"], float(row["strike"])): row
        for row in snapshot["rows"]
    }

    position_rows: list[dict[str, Any]] = []
    attributions: list[dict[str, Any]] = []
    unmarkable: list[str] = []
    aggregate = {"delta_dollars": 0.0, "gamma_dollars_per_1pct": 0.0, "vega_dollars_per_vol_pt": 0.0, "theta_dollars_per_day": 0.0}
    premium_by_symbol: dict[str, float] = {}
    for position in open_positions:
        key = (position["symbol"], position["expiry"], position["option_type"], float(position["strike"]))
        row = rows_by_contract.get(key)
        if row is None:
            unmarkable.append(str(position["position_id"]))
            continue
        spot_now = float(row["underlying_spot"])
        greeks = bs_greeks(
            spot_now, float(position["strike"]), year_fraction(as_of, str(position["expiry"])),
            RISK_FREE_RATE, float(row["implied_vol"]), str(position["option_type"]),
        )
        dollars = dollar_greeks(greeks, spot_now)
        for name in aggregate:
            aggregate[name] += dollars[name]
        premium_by_symbol[str(position["symbol"])] = premium_by_symbol.get(str(position["symbol"]), 0.0) + float(position["entry_fill"])
        position_rows.append({
            "artifact_type": "forward_book_position_risk",
            "position_id": str(position["position_id"]),
            "symbol": str(position["symbol"]),
            "option_type": str(position["option_type"]),
            "strike": float(position["strike"]),
            "expiry": str(position["expiry"]),
            **{name: round(greeks[name], 6) for name in ("delta", "gamma", "vega", "theta")},
            **dollars,
            "paper_only": True, "live_blocked": True,
        })
        attributions.append(attribute_open_position(position, row, as_of))

    total_premium = sum(premium_by_symbol.values())
    premium_by_sector: dict[str, float] = {}
    for symbol, premium in premium_by_symbol.items():
        sector = SECTOR_MAP.get(symbol, "Unmapped")
        premium_by_sector[sector] = premium_by_sector.get(sector, 0.0) + premium
    top_symbol_share = max(premium_by_symbol.values()) / total_premium if total_premium > 0 else 0.0
    bucket_totals = {
        bucket: round(sum(float(item[bucket]) for item in attributions), 6)
        for bucket in ("direction_pnl", "volatility_pnl", "decay_pnl", "residual_pnl", "friction_cost", "unrealized_pnl_bid_side")
    }
    max_identity_gap = max((abs(float(item["attribution_identity_gap"])) for item in attributions), default=0.0)

    summary = _base("forward_book_risk_complete")
    summary.update({
        "as_of_snapshot_date": as_of,
        "open_positions": len(open_positions),
        "marked_positions": len(position_rows),
        "unmarkable_position_ids": sorted(unmarkable),
        "book_dollar_greeks": {name: round(value, 2) for name, value in aggregate.items()},
        "premium_at_risk_by_symbol": {symbol: round(value, 6) for symbol, value in sorted(premium_by_symbol.items())},
        "premium_at_risk_by_sector": {sector: round(value, 6) for sector, value in sorted(premium_by_sector.items())},
        "top_symbol_premium_share": round(top_symbol_share, 4),
        "pnl_attribution_totals_premium_units": bucket_totals,
        "attribution_max_identity_gap": round(max_identity_gap, 9),
        "attribution_buckets": "direction(delta+gamma) + volatility(vega) + decay(theta) + residual == mid_move; unrealized == mid_move - friction",
    })
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    _write_json(BOOK_RISK_PATH, summary)
    _write_jsonl(POSITION_RISK_PATH, position_rows + [{"artifact_type": "forward_book_pnl_attribution", **item} for item in attributions])
    _write_report(summary)
    return summary


def _base(status: str) -> dict[str, Any]:
    return {
        "artifact_type": "forward_book_risk_summary",
        "book_risk_status": status,
        "risk_free_rate": RISK_FREE_RATE,
        "risk_free_source": RISK_FREE_SOURCE,
        "evidence_class": "quote_derived_snapshot",
        "not_profitability_claim": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _write_report(summary: dict[str, Any]) -> None:
    greeks = summary.get("book_dollar_greeks", {})
    buckets = summary.get("pnl_attribution_totals_premium_units", {})
    lines = [
        "# DOPEY Forward Book Risk Report",
        "",
        f"- as of snapshot: `{summary.get('as_of_snapshot_date', '')}` | open `{summary.get('open_positions', 0)}` | marked `{summary.get('marked_positions', 0)}` | unmarkable `{len(summary.get('unmarkable_position_ids', []))}`",
        "",
        "## Book Dollar Greeks (1-contract paper positions)",
        f"- net delta$: `{greeks.get('delta_dollars', 0.0)}` | gamma$/1%: `{greeks.get('gamma_dollars_per_1pct', 0.0)}` | vega$/vol-pt: `{greeks.get('vega_dollars_per_vol_pt', 0.0)}` | theta$/day: `{greeks.get('theta_dollars_per_day', 0.0)}`",
        f"- top-symbol premium share: `{summary.get('top_symbol_premium_share', 0.0)}`",
        "",
        "## Why the Book Moved (premium units, entry -> now)",
        f"- direction (delta+gamma): `{buckets.get('direction_pnl', 0.0)}`",
        f"- volatility (vega): `{buckets.get('volatility_pnl', 0.0)}`",
        f"- decay (theta): `{buckets.get('decay_pnl', 0.0)}`",
        f"- residual (higher-order/smile): `{buckets.get('residual_pnl', 0.0)}`",
        f"- friction (spreads+commissions): `-{buckets.get('friction_cost', 0.0)}`",
        f"- unrealized (bid side): `{buckets.get('unrealized_pnl_bid_side', 0.0)}`",
        f"- identity gap (must be ~0): `{summary.get('attribution_max_identity_gap', 0.0)}`",
        "",
        "## Honest Limits",
        "- Greeks are Black-Scholes at snapshot IV; no smile dynamics model is claimed.",
        "- Attribution explains the paper book only; it is not a profitability claim.",
        "- paper_only: `true`; live_blocked: `true`.",
    ]
    BOOK_RISK_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records) + ("\n" if records else ""), encoding="utf-8")
