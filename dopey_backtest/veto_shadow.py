"""Veto Shadow Ledger: measure the opportunity cost of opinion vetoes.

Every cycle, the entry pipeline rejects candidates for two very different
kinds of reasons. CAPACITY reasons (caps, symbol already open, illiquid
contract) mean the trade could not honestly be taken or priced. OPINION
reasons (entry-context bias, adversarial verdict) mean the system judged the
moment hostile. The user-facing question "how much are the vetoes costing
us?" is answerable only for opinion vetoes - and this lane answers it with
evidence instead of fear: each opinion-vetoed candidate that had a priceable,
liquidity-clean contract is opened as a PHANTOM position with the identical
fill math, marked with the identical marking function, and closed by the
identical exit policy (all injected from the forward walk, never reimplemented
here). Outcomes accrue per veto class.

Honesty invariants:
  - Phantom outcomes live in their own artifact files; the forward ledger,
    integrity builder, and release gate never see them.
  - Every phantom close is re-stamped phantom_veto_shadow_outcome and
    included_in_forward_performance_statistics=False - it can never be
    mistaken for a validated forward outcome.
  - A veto class that shows positive phantom expectancy is a RETEST signal
    for the reclamation bench, never an automatic loosening.
  - Capacity saturation is reported, never silently truncated.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from dopey_research_pipeline.artifact_io import write_json_atomic

REPO_ROOT = Path(__file__).resolve().parent.parent
FORWARD_WALK_DIR = REPO_ROOT / "artifacts" / "dopey" / "forward_walk"
SHADOW_LEDGER_PATH = FORWARD_WALK_DIR / "veto_shadow_ledger.json"
SHADOW_CLOSED_PATH = FORWARD_WALK_DIR / "veto_shadow_closed.jsonl"
SHADOW_SUMMARY_PATH = FORWARD_WALK_DIR / "veto_shadow_summary.json"

SHADOW_POLICY_VERSION = "dopey-veto-shadow-v1"
MAX_SHADOW_OPEN_POSITIONS = 40
MAX_SHADOW_OPENS_PER_RUN = 12
SHADOW_CENSOR_AFTER_MISSED_MARKS = 3
PHANTOM_OUTCOME_CLASS = "phantom_veto_shadow_outcome"
CATASTROPHIC_RETURN = -0.90

# Opinion veto classes eligible for shadowing. Prefix-matched so specific
# context veto reasons (e.g. vrp_rich_premium_expensive) and adversarial flag
# bundles qualify without enumerating every code here.
OPINION_REASON_PREFIXES: tuple[str, ...] = (
    "entry_context_unfavorable",
    "adversarial_entry_verdict",
    "vrp_",
    "dealer_",
    "crowded_",
    "fusion_bias_",
    "vol_surface_",
    "vix_term_",
    "congress_",
    "speculative_excess_",
    "earnings_blackout",
    "geopolitical_",
)


def is_opinion_veto(reason_codes: tuple[str, ...] | list[str]) -> bool:
    """True when EVERY reason is an opinion; any capacity/liquidity code disqualifies."""
    codes = [str(code) for code in reason_codes]
    if not codes:
        return False
    return all(code.startswith(OPINION_REASON_PREFIXES) for code in codes)


def load_shadow_ledger() -> dict[str, Any]:
    if SHADOW_LEDGER_PATH.exists():
        parsed = json.loads(SHADOW_LEDGER_PATH.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            parsed.setdefault("open_positions", [])
            parsed.setdefault("closed_trades", [])
            parsed.setdefault("censored_count", 0)
            parsed.setdefault("position_counter", 0)
            parsed.setdefault("last_marking_date", "")
            parsed.setdefault("last_open_date", "")
            return parsed
    return {
        "artifact_type": "veto_shadow_ledger",
        "shadow_policy_version": SHADOW_POLICY_VERSION,
        "open_positions": [],
        "closed_trades": [],
        "censored_count": 0,
        "position_counter": 0,
        "last_marking_date": "",
        "last_open_date": "",
    }


def _phantom_flags() -> dict[str, Any]:
    return {
        "phantom": True,
        "outcome_integrity_class": PHANTOM_OUTCOME_CLASS,
        "included_in_forward_performance_statistics": False,
        "included_in_promotion_gate": False,
        "never_a_gate_input": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def open_shadow_positions(
    shadow_candidates: list[tuple[dict[str, Any], tuple[str, ...]]],
    rows_by_symbol: dict[str, list[dict[str, Any]]],
    snapshot_date: str,
    select_contract: Callable[..., tuple[dict[str, Any] | None, tuple[str, ...]]],
    commission_premium_units: float,
) -> dict[str, Any]:
    """Open phantoms for opinion-vetoed candidates with a priceable contract.

    select_contract is the forward walk's own entry-contract selector, so a
    phantom holds exactly the contract the real entry would have held.
    """
    if not shadow_candidates:
        return {"shadow_opened": 0, "shadow_skipped_capacity": 0}
    ledger = load_shadow_ledger()
    if ledger["last_open_date"] == snapshot_date:
        return {"shadow_opened": 0, "shadow_skipped_capacity": 0, "idempotent_skip": True}
    used_signal_ids = {str(p.get("signal_id", "")) for p in ledger["open_positions"]}
    used_signal_ids |= {str(t.get("signal_id", "")) for t in ledger["closed_trades"]}
    opened = 0
    skipped_capacity = 0
    for record, reason_codes in shadow_candidates:
        if not is_opinion_veto(reason_codes):
            continue
        signal_id = str(record.get("signal_id", ""))
        if signal_id in used_signal_ids:
            continue
        if opened >= MAX_SHADOW_OPENS_PER_RUN or len(ledger["open_positions"]) >= MAX_SHADOW_OPEN_POSITIONS:
            skipped_capacity += 1
            continue
        symbol = str(record["symbol"])
        strategy = str(record["candidate_strategy"])
        side = "call" if strategy == "long_call" else "put"
        atm, _selection_reasons = select_contract(rows_by_symbol, symbol, side)
        if atm is None:
            continue  # unpriceable: opportunity cost is not measurable, honestly
        ask = float(atm["ask"])
        entry_fill = round(ask + commission_premium_units, 6)
        ledger["position_counter"] = int(ledger["position_counter"]) + 1
        ledger["open_positions"].append(
            {
                "position_id": f"vs-{symbol}-{strategy}-{snapshot_date}-{int(ledger['position_counter']):05d}",
                "symbol": symbol,
                "candidate_strategy": strategy,
                "option_type": side,
                "signal_id": signal_id,
                "signal_family": str(record.get("source_signal_family", "")),
                "signal_date": str(record.get("signal_date", "")),
                "entry_date": snapshot_date,
                "expiry": str(atm["expiry"]),
                "strike": float(atm["strike"]),
                "entry_bid": float(atm["bid"]),
                "entry_ask": ask,
                "entry_fill": entry_fill,
                "entry_spot": float(atm["underlying_spot"]),
                "entry_iv": float(atm["implied_vol"]),
                "veto_reason_codes": [str(code) for code in reason_codes],
                "primary_veto_class": str(reason_codes[0]),
                "marking_sessions": 0,
                "observation_sessions": 0,
                "missed_marks": 0,
                "shadow_policy_version": SHADOW_POLICY_VERSION,
                **_phantom_flags(),
            }
        )
        used_signal_ids.add(signal_id)
        opened += 1
    ledger["last_open_date"] = snapshot_date
    _persist(ledger)
    return {"shadow_opened": opened, "shadow_skipped_capacity": skipped_capacity}


def mark_shadow_positions(
    rows_by_contract: dict[tuple[str, str, str, float], dict[str, Any]],
    snapshot_date: str,
    mark_position: Callable[..., tuple[dict[str, Any] | None, dict[str, Any] | None]],
) -> dict[str, Any]:
    """Mark phantoms with the forward walk's own marking/exit function."""
    ledger = load_shadow_ledger()
    if ledger["last_marking_date"] == snapshot_date or not ledger["open_positions"]:
        ledger["last_marking_date"] = snapshot_date
        _persist(ledger)
        return _summarize(ledger)
    still_open: list[dict[str, Any]] = []
    for position in ledger["open_positions"]:
        key = (position["symbol"], position["expiry"], position["option_type"], float(position["strike"]))
        row = rows_by_contract.get(key)
        if row is None:
            position = dict(position)
            position["missed_marks"] = int(position.get("missed_marks", 0)) + 1
            if (
                position["missed_marks"] >= SHADOW_CENSOR_AFTER_MISSED_MARKS
                or snapshot_date >= str(position["expiry"])
            ):
                ledger["censored_count"] = int(ledger["censored_count"]) + 1
            else:
                still_open.append(position)
            continue
        marked, closed = mark_position(position, row, snapshot_date)
        if closed is not None:
            closed = {**closed, **_phantom_flags()}
            closed["artifact_type"] = "veto_shadow_closed_trade"
            closed["outcome_integrity_reason_codes"] = ["phantom_veto_shadow_close"]
            ledger["closed_trades"].append(closed)
            continue
        still_open.append(marked)
    ledger["open_positions"] = still_open
    ledger["last_marking_date"] = snapshot_date
    _persist(ledger)
    return _summarize(ledger)


def _summarize(ledger: dict[str, Any]) -> dict[str, Any]:
    closed = ledger["closed_trades"]
    per_class: dict[str, dict[str, Any]] = {}
    for trade in closed:
        bucket = per_class.setdefault(
            str(trade.get("primary_veto_class", "unknown")),
            {"n": 0, "wins": 0, "sum_path_pnl": 0.0, "sum_trade_return": 0.0, "catastrophic": 0},
        )
        bucket["n"] += 1
        pnl = float(trade.get("path_pnl", 0.0))
        ret = float(trade.get("trade_return", 0.0))
        bucket["sum_path_pnl"] += pnl
        bucket["sum_trade_return"] += ret
        if pnl > 0:
            bucket["wins"] += 1
        if ret <= CATASTROPHIC_RETURN:
            bucket["catastrophic"] += 1
    for stats in per_class.values():
        n = stats["n"]
        stats["win_rate"] = round(stats["wins"] / n, 4)
        stats["mean_trade_return"] = round(stats["sum_trade_return"] / n, 6)
        stats["mean_path_pnl"] = round(stats["sum_path_pnl"] / n, 6)
        stats["catastrophic_loss_share"] = round(stats["catastrophic"] / n, 4)
        stats["sum_path_pnl"] = round(stats["sum_path_pnl"], 6)
        del stats["sum_trade_return"]
    summary = {
        "artifact_type": "veto_shadow_summary",
        "shadow_policy_version": SHADOW_POLICY_VERSION,
        "open_phantom_count": len(ledger["open_positions"]),
        "closed_phantom_count": len(closed),
        "censored_phantom_count": int(ledger["censored_count"]),
        "per_veto_class": per_class,
        "reading": (
            "positive mean phantom returns in a veto class = that veto is leaving money "
            "on the table (a retest signal); negative = the veto is earning its keep"
        ),
        "never_a_gate_input": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(SHADOW_SUMMARY_PATH, summary)
    return summary


def _persist(ledger: dict[str, Any]) -> None:
    write_json_atomic(SHADOW_LEDGER_PATH, ledger, keep_backup=True)
    lines = [json.dumps(t, sort_keys=True, ensure_ascii=False) for t in ledger["closed_trades"]]
    SHADOW_CLOSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHADOW_CLOSED_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
