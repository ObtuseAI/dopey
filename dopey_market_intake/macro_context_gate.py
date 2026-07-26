"""Macro-context gate: load, validate, and distill the operator-staged macro lanes.

Gates mirror the chain-snapshot loader: manifest present and finalized, license
reviewed, sha256 pins match, schemas exact. Rows that pass become four validated
lanes (treasury par yield curve, vol term structure, FINRA short volume, CFTC
COT E-mini positioning) plus distilled per-run states:

- risk_free: interpolated par yield at the ~30d tenor (the REAL risk-free rate)
- vol term structure: VIX9D/VIX3M slope -> contango / backwardation / flat
- SKEW: latest level and trailing-252d percentile (tail-risk pricing)
- short flow: latest short-volume ratio per universe symbol
- positioning: COT non-commercial net z-score vs trailing year

Everything here is VISIBILITY and foundry input - no entry-bias change is wired
from these lanes until the foundry/truth layer earns one. Paper-only.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
MACRO_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "macro_context"
MACRO_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "macro_context_manifest.json"
MACRO_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"

VALID_LICENSE_STATUSES = {"reviewed_allowed_internal_research", "reviewed_public_domain"}
SCHEMAS = {
    "treasury_yield_curve.csv": ("date", "label", "maturity_years", "yield_pct"),
    "vol_term_structure.csv": ("date", "symbol", "close"),
    "finra_short_volume.csv": ("date", "symbol", "short_volume", "short_exempt_volume", "total_volume"),
    "cftc_cot_es.csv": ("report_date", "noncomm_long", "noncomm_short", "noncomm_net", "open_interest"),
    "wikipedia_pageviews.csv": ("date", "symbol", "article", "views"),
    "crypto_series.csv": ("date", "symbol", "close"),
    "fed_liquidity.csv": ("date", "series", "value"),
    "congress_trades.csv": ("transaction_date", "disclosure_date", "symbol", "member", "type", "amount_range"),
    "fundamentals.csv": (
        "date", "symbol", "theme", "in_universe", "market_cap",
        "enterprise_value", "total_revenue", "trailing_pe", "forward_pe",
        "price_to_sales", "price_to_book", "profit_margin", "revenue_growth",
        "free_cashflow", "total_debt", "total_cash", "first_trade_date",
    ),
    "short_crowding.csv": (
        "date", "symbol", "shares_short", "shares_short_prior_month",
        "short_percent_float", "short_ratio", "float_shares",
        "shares_outstanding", "held_percent_institutions",
        "held_percent_insiders", "average_volume", "market_cap", "source",
    ),
    "finra_margin_statistics.csv": (
        "month", "debit_balances_millions", "free_credit_cash_millions",
        "free_credit_margin_millions", "source",
    ),
}
LANE_RECENCY_DAYS: dict[str, tuple[str, int]] = {
    "treasury_yield_curve.csv": ("date", 7),
    "vol_term_structure.csv": ("date", 7),
    "finra_short_volume.csv": ("date", 7),
    "cftc_cot_es.csv": ("report_date", 14),
    "wikipedia_pageviews.csv": ("date", 7),
    "crypto_series.csv": ("date", 3),
    "fed_liquidity.csv": ("date", 14),
    "congress_trades.csv": ("disclosure_date", 180),
    "fundamentals.csv": ("date", 90),
    "short_crowding.csv": ("date", 45),
    "finra_margin_statistics.csv": ("month", 90),
}
ATTENTION_Z_WINDOW = 60
ATTENTION_CROWDED_Z = 2.0
# Fundamentals screen thresholds - documented HEURISTICS, not evidence. A name
# is a short-candidate research flag at >= FUNDAMENTALS_FLAGS_FOR_CANDIDATE
# excess flags with a liquidity floor. Expensive can stay expensive; crowded
# shorts squeeze - flags feed the panel/foundry, never an entry bias.
FUNDAMENTALS_PE_EXTREME = 100.0
FUNDAMENTALS_FORWARD_PE_EXTREME = 80.0
FUNDAMENTALS_PS_EXTREME = 20.0
FUNDAMENTALS_PB_EXTREME = 15.0
FUNDAMENTALS_MARGIN_DEEP_NEGATIVE = -0.20
FUNDAMENTALS_FLAGS_FOR_CANDIDATE = 3
FUNDAMENTALS_MIN_MARKET_CAP = 1e9
FUNDAMENTALS_STALE_DAYS = 60


def load_macro_lanes() -> dict[str, Any]:
    if not MACRO_MANIFEST_PATH.exists():
        return {"macro_status": "blocked_missing_macro_manifest", "lanes": {}}
    try:
        manifest = json.loads(MACRO_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"macro_status": "blocked_macro_manifest_unparseable", "lanes": {}}
    if str(manifest.get("license_status", "")).lower() not in VALID_LICENSE_STATUSES:
        return {"macro_status": "blocked_macro_license_not_reviewed", "lanes": {}}
    if manifest.get("provider_terms_reviewed") is not True:
        return {"macro_status": "blocked_macro_terms_not_reviewed", "lanes": {}}
    hashes = {str(key).replace("\\", "/"): str(value) for key, value in manifest.get("file_hashes", {}).items()}
    lanes: dict[str, list[dict[str, str]]] = {}
    reasons: list[str] = []
    for relative, recorded in hashes.items():
        path = REPO_ROOT / relative
        name = path.name
        if name not in SCHEMAS:
            continue
        if not path.exists():
            reasons.append(f"pinned_file_missing:{relative}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != recorded:
            reasons.append(f"hash_mismatch:{relative}")
            continue
        reader = csv.DictReader(path.read_text(encoding="utf-8").splitlines())
        if tuple(reader.fieldnames or ()) != SCHEMAS[name]:
            reasons.append(f"schema_mismatch:{relative}")
            continue
        rows = list(reader)
        date_key, max_age_days = LANE_RECENCY_DAYS[name]
        raw_latest_date = max(
            (str(row.get(date_key, "")) for row in rows),
            default="",
        )
        try:
            latest_date = date.fromisoformat(raw_latest_date)
        except ValueError:
            reasons.append(
                f"latest_date_invalid:{relative}:{date_key}={raw_latest_date!r}"
            )
            continue
        age_days = (datetime.now(timezone.utc).date() - latest_date).days
        if age_days < 0 or age_days > max_age_days:
            reasons.append(
                f"stale_lane:{relative}:age_days={age_days}:max_age_days={max_age_days}"
            )
            continue
        lanes[name] = rows
    if not lanes:
        return {"macro_status": "blocked_no_valid_macro_lanes", "lanes": {}, "reason_codes": sorted(reasons)}
    return {"macro_status": "macro_lanes_validated", "lanes": lanes, "reason_codes": sorted(reasons)}


def interpolate_yield(curve_rows: list[dict[str, str]], tenor_years: float) -> float | None:
    """Linear interpolation on the LATEST curve date; None when unavailable."""
    by_date: dict[str, list[tuple[float, float]]] = {}
    for row in curve_rows:
        try:
            by_date.setdefault(row["date"], []).append((float(row["maturity_years"]), float(row["yield_pct"])))
        except (KeyError, ValueError):
            continue
    if not by_date:
        return None
    points = sorted(by_date[max(by_date)])
    if not points:
        return None
    if tenor_years <= points[0][0]:
        return points[0][1]
    if tenor_years >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= tenor_years <= x1:
            return y0 + (y1 - y0) * (tenor_years - x0) / (x1 - x0)
    return points[-1][1]


def vol_term_state(vol_rows: list[dict[str, str]]) -> dict[str, Any]:
    latest: dict[str, tuple[str, float]] = {}
    skew_series: list[float] = []
    for row in vol_rows:
        try:
            symbol, day, close = row["symbol"], row["date"], float(row["close"])
        except (KeyError, ValueError):
            continue
        if symbol == "SKEW":
            skew_series.append(close)
        if symbol not in latest or day > latest[symbol][0]:
            latest[symbol] = (day, close)
    state: dict[str, Any] = {name: latest.get(name, ("", 0.0))[1] for name in ("VIX9D", "VIX", "VIX3M", "VIX6M", "SKEW")}
    short_end, long_end = state.get("VIX9D", 0.0), state.get("VIX3M", 0.0)
    if short_end > 0 and long_end > 0:
        slope = (long_end - short_end) / short_end
        state["term_slope_9d_3m"] = round(slope, 6)
        state["term_structure_state"] = "backwardation_stress" if slope < -0.01 else ("contango_normal" if slope > 0.01 else "flat")
    else:
        state["term_slope_9d_3m"] = None
        state["term_structure_state"] = "insufficient_indices"
    if skew_series:
        window = skew_series[-252:]
        current = window[-1]
        state["skew_percentile_252d"] = round(sum(1 for value in window if value <= current) / len(window), 4)
    else:
        state["skew_percentile_252d"] = None
    return state


def short_flow_state(finra_rows: list[dict[str, str]]) -> dict[str, Any]:
    latest_date = max((row.get("date", "") for row in finra_rows), default="")
    ratios: dict[str, float] = {}
    for row in finra_rows:
        if row.get("date") != latest_date:
            continue
        try:
            total = float(row["total_volume"])
            if total > 0:
                ratios[row["symbol"]] = round(float(row["short_volume"]) / total, 4)
        except (KeyError, ValueError):
            continue
    return {
        "date": latest_date,
        "short_volume_ratio_by_symbol": dict(sorted(ratios.items())),
        "is_open_short_interest": False,
        "semantics": "daily_short_sale_flow_not_open_short_positions",
    }


def short_crowding_state(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Distill the latest actual open-short snapshot without borrow inference."""

    latest_by_symbol: dict[str, dict[str, str]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        observed = str(row.get("date", "")).strip()
        if not symbol or not observed:
            continue
        if (
            symbol not in latest_by_symbol
            or observed > str(latest_by_symbol[symbol].get("date", ""))
        ):
            latest_by_symbol[symbol] = row
    observations: dict[str, dict[str, Any]] = {}
    for symbol, row in sorted(latest_by_symbol.items()):
        try:
            observations[symbol] = {
                "as_of": row["date"],
                "shares_short": float(row["shares_short"]),
                "shares_short_prior_month": (
                    float(row["shares_short_prior_month"])
                    if row["shares_short_prior_month"]
                    else None
                ),
                "short_percent_float": float(row["short_percent_float"]),
                "days_to_cover": (
                    float(row["short_ratio"]) if row["short_ratio"] else None
                ),
                "float_shares": (
                    float(row["float_shares"]) if row["float_shares"] else None
                ),
                "shares_outstanding": (
                    float(row["shares_outstanding"])
                    if row["shares_outstanding"]
                    else None
                ),
                "source": row["source"],
            }
        except (KeyError, ValueError):
            continue
    return {
        "short_crowding_lane": (
            "actual_open_short_snapshots"
            if observations
            else "no_actual_open_short_snapshots"
        ),
        "symbol_count": len(observations),
        "by_symbol": observations,
        "daily_short_volume_substituted": False,
        "borrow_fee_inferred": False,
        "borrow_utilization_inferred": False,
    }


def margin_leverage_state(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Summarize aggregate customer margin leverage from FINRA Rule 4521(d)."""

    points: list[tuple[str, float, float]] = []
    for row in rows:
        try:
            free_credit = float(row["free_credit_cash_millions"]) + float(
                row["free_credit_margin_millions"]
            )
            points.append(
                (
                    row["month"],
                    float(row["debit_balances_millions"]),
                    free_credit,
                )
            )
        except (KeyError, ValueError):
            continue
    points.sort()
    if not points:
        return {"margin_leverage_lane": "no_finra_margin_rows"}
    month, debit, free_credit = points[-1]
    return {
        "margin_leverage_lane": "finra_rule_4521d_aggregate",
        "as_of_month": month,
        "margin_debit_millions": debit,
        "free_credit_millions": free_credit,
        "debit_to_free_credit_ratio": (
            round(debit / free_credit, 6) if free_credit > 0.0 else None
        ),
        "debit_growth_3m": (
            round(debit / points[-4][1] - 1.0, 6)
            if len(points) >= 4 and points[-4][1] > 0.0
            else None
        ),
        "debit_growth_12m": (
            round(debit / points[-13][1] - 1.0, 6)
            if len(points) >= 13 and points[-13][1] > 0.0
            else None
        ),
        "security_specific_leverage_inference_allowed": False,
    }


def positioning_state(cot_rows: list[dict[str, str]]) -> dict[str, Any]:
    series: list[tuple[str, float]] = []
    for row in cot_rows:
        try:
            series.append((row["report_date"], float(row["noncomm_net"])))
        except (KeyError, ValueError):
            continue
    series.sort()
    if len(series) < 12:
        return {"cot_state": "insufficient_reports", "reports": len(series)}
    nets = [value for _, value in series]
    window = nets[-52:]
    mean = sum(window) / len(window)
    deviation = (sum((value - mean) ** 2 for value in window) / max(len(window) - 1, 1)) ** 0.5 or 1e-9
    z_score = (nets[-1] - mean) / deviation
    return {
        "cot_state": "es_noncommercial_net",
        "latest_report_date": series[-1][0],
        "noncomm_net_latest": nets[-1],
        "noncomm_net_z_52w": round(z_score, 4),
        "reports": len(series),
    }


def attention_state(pageview_rows: list[dict[str, str]]) -> dict[str, Any]:
    """Crowd-attention proxy from open Wikimedia pageviews: latest z-score per
    symbol vs its trailing window. High z = crowded attention - a RESEARCH FLAG
    for the put-side pipeline, never a bias change (hype often keeps hyping;
    only the foundry/truth layer can earn it a role)."""
    series: dict[str, list[tuple[str, float]]] = {}
    for row in pageview_rows:
        try:
            series.setdefault(row["symbol"], []).append((row["date"], float(row["views"])))
        except (KeyError, ValueError):
            continue
    z_by_symbol: dict[str, float] = {}
    for symbol, points in series.items():
        points.sort()
        window = [views for _, views in points[-ATTENTION_Z_WINDOW:]]
        if len(window) < 20:
            continue
        mean = sum(window[:-1]) / len(window[:-1])
        deviation = (sum((value - mean) ** 2 for value in window[:-1]) / max(len(window) - 2, 1)) ** 0.5 or 1e-9
        z_by_symbol[symbol] = round((window[-1] - mean) / deviation, 4)
    crowded = sorted((symbol for symbol, z in z_by_symbol.items() if z >= ATTENTION_CROWDED_Z), key=lambda s: -z_by_symbol[s])
    return {
        "attention_z_by_symbol": dict(sorted(z_by_symbol.items())),
        "crowded_attention_candidates": crowded,
        "crowded_threshold_z": ATTENTION_CROWDED_Z,
        "note": "research_flag_for_put_side_pipeline_not_a_bias_change",
    }


def crypto_state(crypto_rows: list[dict[str, str]]) -> dict[str, Any]:
    """24/7 risk-appetite context: BTC/ETH momentum over 7d, plus the weekend
    move (Fri close -> latest) - the leading-indicator hypothesis, exposed as
    visibility and foundry input only."""
    series: dict[str, list[tuple[str, float]]] = {}
    for row in crypto_rows:
        try:
            series.setdefault(row["symbol"], []).append((row["date"], float(row["close"])))
        except (KeyError, ValueError):
            continue
    state: dict[str, Any] = {}
    for symbol, points in sorted(series.items()):
        points.sort()
        closes = [value for _, value in points]
        if len(closes) < 10:
            continue
        state[symbol] = {
            "latest_date": points[-1][0],
            "close": closes[-1],
            "momentum_7d": round(closes[-1] / closes[-8] - 1.0, 4) if closes[-8] > 0 else None,
            "momentum_1d": round(closes[-1] / closes[-2] - 1.0, 4) if closes[-2] > 0 else None,
        }
    return state or {"crypto_state": "insufficient_series"}


def liquidity_impulse_state(liquidity_rows: list[dict[str, str]]) -> dict[str, Any]:
    """Druckenmiller-style net liquidity: WALCL - RRPONTSYD - WTREGEN (all in
    millions on FRED), classified by the trailing ~4-week impulse. Visibility
    and foundry input only until the discipline earns it a sizing role."""
    by_series: dict[str, list[tuple[str, float]]] = {}
    for row in liquidity_rows:
        try:
            by_series.setdefault(row["series"], []).append((row["date"], float(row["value"])))
        except (KeyError, ValueError):
            continue
    if not all(series in by_series for series in ("WALCL", "RRPONTSYD", "WTREGEN")):
        return {"impulse_state": "insufficient_series", "series_present": sorted(by_series)}
    # forward-fill onto WALCL's weekly dates (RRP/TGA are daily, WALCL weekly)
    net: list[tuple[str, float]] = []
    for day, walcl in sorted(by_series["WALCL"]):
        drains = 0.0
        usable = True
        for series in ("RRPONTSYD", "WTREGEN"):
            candidates = [value for date_, value in by_series[series] if date_ <= day]
            if not candidates:
                usable = False
                break
            # RRPONTSYD is in billions on FRED; WALCL/WTREGEN in millions
            drains += candidates[-1] * (1000.0 if series == "RRPONTSYD" else 1.0)
        if usable:
            net.append((day, walcl - drains))
    if len(net) < 6:
        return {"impulse_state": "insufficient_history", "points": len(net)}
    latest_day, latest_value = net[-1]
    prior_value = net[-5][1]  # ~4 weeks earlier (weekly WALCL cadence)
    impulse_pct = (latest_value - prior_value) / abs(prior_value) if prior_value else 0.0
    state = "flooding" if impulse_pct > 0.005 else ("draining" if impulse_pct < -0.005 else "neutral")
    return {
        "impulse_state": state,
        "as_of": latest_day,
        "net_liquidity_musd": round(latest_value, 0),
        "impulse_4w_pct": round(impulse_pct, 5),
        "formula": "WALCL - RRPONTSYD*1000 - WTREGEN (FRED, millions)",
        "note": "visibility_and_foundry_input_only_no_sizing_role_until_earned",
    }


def congress_state(congress_rows: list[dict[str, str]]) -> dict[str, Any]:
    """STOCK Act disclosure summary for the universe: trailing-90d net
    buy-minus-sell counts per symbol. HONEST LIMITS baked into the label:
    disclosures lag up to 45 days, amounts are ranges, and members' motives
    are unknowable - this is an attention/positioning research flag, never a
    copy-trade and never a bias change until the foundry earns it one."""
    if not congress_rows:
        return {"congress_lane": "no_universe_transactions"}
    latest = max(row.get("transaction_date", "") for row in congress_rows)
    try:
        from datetime import date, timedelta

        cutoff = (date.fromisoformat(latest) - timedelta(days=90)).isoformat()
    except ValueError:
        return {"congress_lane": "unparseable_dates"}
    net: dict[str, int] = {}
    for row in congress_rows:
        if row.get("transaction_date", "") < cutoff:
            continue
        kind = str(row.get("type", "")).lower()
        delta = 1 if "purchase" in kind else (-1 if "sale" in kind else 0)
        if delta:
            symbol = str(row.get("symbol", ""))
            net[symbol] = net.get(symbol, 0) + delta
    return {
        "congress_lane": "stock_act_90d_window",
        "latest_transaction_date": latest,
        "net_buy_minus_sell_counts": dict(sorted(net.items())),
        "notable_buying": sorted((s for s, v in net.items() if v >= 3), key=lambda s: -net[s]),
        "notable_selling": sorted((s for s, v in net.items() if v <= -3), key=lambda s: net[s]),
        "honest_limits": "45d_disclosure_lag_range_amounts_unknown_motives_research_flag_only",
    }


def _fund_float(row: dict[str, str], key: str) -> float | None:
    raw = str(row.get(key, "")).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def fundamentals_flags(row: dict[str, str]) -> list[str]:
    """Valuation-excess / fundamental-rot flags for one symbol's latest row.
    Thresholds are documented heuristics (module constants), not evidence."""
    flags: list[str] = []
    trailing_pe = _fund_float(row, "trailing_pe")
    forward_pe = _fund_float(row, "forward_pe")
    margin = _fund_float(row, "profit_margin")
    if (trailing_pe is not None and trailing_pe > FUNDAMENTALS_PE_EXTREME) or (
        trailing_pe is None and margin is not None and margin < 0
    ):
        # a triple-digit P/E and "no P/E because there are no E" are the same
        # disease at different stages
        flags.append("pe_extreme_or_no_earnings")
    if (
        forward_pe is not None
        and forward_pe > FUNDAMENTALS_FORWARD_PE_EXTREME
    ):
        flags.append("forward_pe_extreme")
    price_to_sales = _fund_float(row, "price_to_sales")
    if price_to_sales is not None and price_to_sales > FUNDAMENTALS_PS_EXTREME:
        flags.append("price_to_sales_extreme")
    price_to_book = _fund_float(row, "price_to_book")
    if price_to_book is not None and price_to_book > FUNDAMENTALS_PB_EXTREME:
        flags.append("price_to_book_extreme")
    if margin is not None and margin < FUNDAMENTALS_MARGIN_DEEP_NEGATIVE:
        flags.append("deeply_unprofitable")
    fcf = _fund_float(row, "free_cashflow")
    if fcf is not None and fcf < 0:
        flags.append("negative_free_cashflow")
    observed_date = str(row.get("date", ""))
    first_trade_date = str(row.get("first_trade_date", ""))
    try:
        listing_age_days = (
            date.fromisoformat(observed_date)
            - date.fromisoformat(first_trade_date)
        ).days
    except ValueError:
        listing_age_days = -1
    if 0 <= listing_age_days <= 730:
        flags.append("recent_listing_under_two_years")
    return flags


def fundamentals_state(fund_rows: list[dict[str, str]]) -> dict[str, Any]:
    """Put-side valuation screen over tradable names + speculative watchlist
    (EV/quantum/AI/crypto themes). Output = short-CANDIDATE research flags:
    ridiculously rich multiples stacked on weak fundamentals. HONEST LIMITS:
    expensive can stay expensive, crowded shorts squeeze, and inside the
    envelope 'short' means LONG PUTS only - flags feed the panel and foundry,
    never an entry bias until evidence earns one."""
    if not fund_rows:
        return {"fundamentals_lane": "no_rows_staged"}
    latest_by_symbol: dict[str, dict[str, str]] = {}
    for row in fund_rows:
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        if symbol not in latest_by_symbol or str(row.get("date", "")) > str(latest_by_symbol[symbol].get("date", "")):
            latest_by_symbol[symbol] = row
    newest = max((str(row.get("date", "")) for row in latest_by_symbol.values()), default="")
    try:
        from datetime import date, timedelta

        stale_cutoff = (date.fromisoformat(newest) - timedelta(days=FUNDAMENTALS_STALE_DAYS)).isoformat()
    except ValueError:
        return {"fundamentals_lane": "unparseable_dates"}
    screened: dict[str, dict[str, Any]] = {}
    candidates: list[tuple[int, str]] = []
    for symbol, row in sorted(latest_by_symbol.items()):
        if str(row.get("date", "")) < stale_cutoff:
            continue
        flags = fundamentals_flags(row)
        market_cap = _fund_float(row, "market_cap") or 0.0
        entry = {
            "theme": row.get("theme", ""),
            "in_tradable_universe": str(row.get("in_universe", "0")) == "1",
            "as_of": row.get("date", ""),
            "market_cap": market_cap,
            "trailing_pe": _fund_float(row, "trailing_pe"),
            "forward_pe": _fund_float(row, "forward_pe"),
            "price_to_sales": _fund_float(row, "price_to_sales"),
            "profit_margin": _fund_float(row, "profit_margin"),
            "first_trade_date": str(row.get("first_trade_date", "")),
            "excess_flags": flags,
            "speculative_excess_score": len(flags),
        }
        screened[symbol] = entry
        if len(flags) >= FUNDAMENTALS_FLAGS_FOR_CANDIDATE and market_cap >= FUNDAMENTALS_MIN_MARKET_CAP:
            candidates.append((len(flags), symbol))
    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    candidate_symbols = [symbol for _, symbol in candidates]
    return {
        "fundamentals_lane": "valuation_quality_screen",
        "names_screened": len(screened),
        "as_of_newest": newest,
        "screen": screened,
        "short_candidate_flags": candidate_symbols,
        "short_candidates_tradable_now": [
            symbol for symbol in candidate_symbols if screened[symbol]["in_tradable_universe"]
        ],
        "short_candidates_watchlist_only": [
            symbol for symbol in candidate_symbols if not screened[symbol]["in_tradable_universe"]
        ],
        "candidate_rule": f">={FUNDAMENTALS_FLAGS_FOR_CANDIDATE}_excess_flags_and_market_cap>=1e9",
        "honest_limits": (
            "heuristic_screen_not_evidence_expensive_stays_expensive_squeeze_risk_"
            "puts_only_inside_envelope_no_bias_change_unearned"
        ),
    }


def run_macro_context_gate() -> dict[str, Any]:
    loaded = load_macro_lanes()
    if loaded["macro_status"] != "macro_lanes_validated":
        summary = {
            "artifact_type": "macro_context_summary",
            **{key: value for key, value in loaded.items() if key != "lanes"},
            "paper_only": True,
            "live_blocked": True,
        }
        write_json_atomic(MACRO_SUMMARY_PATH, summary)
        return summary
    lanes = loaded["lanes"]
    risk_free_30d = interpolate_yield(lanes.get("treasury_yield_curve.csv", []), 30 / 365)
    summary: dict[str, Any] = {
        "artifact_type": "macro_context_summary",
        "macro_status": "macro_context_computed",
        "lanes_validated": sorted(lanes),
        "reason_codes": loaded.get("reason_codes", []),
        "risk_free_rate_30d_pct": round(risk_free_30d, 4) if risk_free_30d is not None else None,
        "risk_free_source": "us_treasury_par_yield_curve" if risk_free_30d is not None else "unavailable",
        "vol_term_structure": vol_term_state(lanes.get("vol_term_structure.csv", [])),
        "short_flow": short_flow_state(lanes.get("finra_short_volume.csv", [])),
        "short_crowding": short_crowding_state(
            lanes.get("short_crowding.csv", [])
        ),
        "market_margin_leverage": margin_leverage_state(
            lanes.get("finra_margin_statistics.csv", [])
        ),
        "es_positioning": positioning_state(lanes.get("cftc_cot_es.csv", [])),
        "attention": attention_state(lanes.get("wikipedia_pageviews.csv", [])),
        "crypto": crypto_state(lanes.get("crypto_series.csv", [])),
        "liquidity_impulse": liquidity_impulse_state(lanes.get("fed_liquidity.csv", [])),
        "congress": congress_state(lanes.get("congress_trades.csv", [])),
        "fundamentals": fundamentals_state(lanes.get("fundamentals.csv", [])),
        "bias_policy": "visibility_and_foundry_input_only_no_entry_bias_until_evidence",
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(MACRO_SUMMARY_PATH, summary)
    return summary
