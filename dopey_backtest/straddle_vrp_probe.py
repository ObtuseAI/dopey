"""Baseline long-straddle VRP probe - a control, not a candidate strategy.

The variance-risk-premium literature says option BUYERS pay a premium: long
volatility bleeds on average because implied usually exceeds subsequent
realized. DOPEY's whole book is long premium (buy-to-open calls/puts), so the
honest baseline question is: what does a systematic, direction-NEUTRAL long
straddle cost? This probe answers that and nothing else.

Design and guardrails:
- ENVELOPE-SAFE: a straddle is long call + long put at one ATM strike; BOTH
  legs are buy-to-open. No short option leg ever - the same rule the whole
  system enforces.
- ONE STRUCTURE = ONE OUTCOME. A straddle is two legs but a single position:
  it counts once for concentration and settles to a single win/loss. Its
  ledger is entirely SEPARATE from the directional forward walk, so a
  straddle outcome can NEVER inflate the 100-validated-close promotion gate.
  This lane is explicitly a baseline measurement, not a promotable cohort.
- Direction bucket is NEUTRAL by construction.
- Combined-premium exit: stop/target/time are applied to call_bid+put_bid,
  not per leg (you exit the structure, not half of it).
- Real quotes only: legs are priced from the staged chain snapshot; a missing
  leg quote defers the exit and, after enough misses, censors the structure
  with no win/loss - never a fabricated fill.

It measures premium bleed; it claims no edge, and promotion_allowed is False.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from dopey_options.chain_snapshot_loader import load_latest_chain_snapshot
from dopey_options.liquidity_engine import (
    FORWARD_ENTRY_MAX_RELATIVE_SPREAD,
    FORWARD_ENTRY_MIN_OPEN_INTEREST,
    FORWARD_ENTRY_MIN_VOLUME,
    forward_entry_liquidity_rejection_reasons,
    quote_relative_spread,
)
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBE_DIR = REPO_ROOT / "artifacts" / "dopey" / "forward_walk"
LEDGER_PATH = PROBE_DIR / "straddle_vrp_probe_ledger.json"
SUMMARY_PATH = PROBE_DIR / "straddle_vrp_probe_summary.json"

PROBE_VERSION = "dopey-straddle-vrp-probe-v1"
COMMISSION_PREMIUM_UNITS = 0.0065  # per leg, matches the directional walk
TARGET_ENTRY_DTE = 30
ENTRY_DTE_BAND = (21, 45)
MAX_OPEN_STRUCTURES = 3
MAX_NEW_STRUCTURES_PER_RUN = 2
COMBINED_STOP_PCT = -0.50
COMBINED_TARGET_PCT = 1.00
MAX_MARKING_SESSIONS = 5
FORCE_CLOSE_DTE = 5
MISSING_QUOTE_CENSOR_AFTER = 3


def _empty_ledger() -> dict[str, Any]:
    return {
        "artifact_type": "straddle_vrp_probe_ledger",
        "open_structures": [],
        "closed_structures": [],
        "structure_counter": 0,
        "last_marking_date": "",
    }


def _load_ledger() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return _empty_ledger()
    try:
        parsed = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_ledger()
    if not isinstance(parsed, dict):
        return _empty_ledger()
    parsed.setdefault("open_structures", [])
    parsed.setdefault("closed_structures", [])
    parsed.setdefault("structure_counter", 0)
    parsed.setdefault("last_marking_date", "")
    return parsed


def _leg_ok(row: dict[str, Any]) -> bool:
    return not forward_entry_liquidity_rejection_reasons(
        float(row["bid"]), float(row["ask"]), int(row["volume"]), int(row["open_interest"])
    )


def atm_straddle_legs(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Pick the ~30-DTE ATM strike where BOTH legs are liquid; return (call,put)."""
    if not rows:
        return None
    spot = float(rows[0]["underlying_spot"])
    if spot <= 0:
        return None
    by_key: dict[tuple[str, float], dict[str, dict[str, Any]]] = {}
    for row in rows:
        dte = int(row["dte_calendar"])
        if not ENTRY_DTE_BAND[0] <= dte <= ENTRY_DTE_BAND[1]:
            continue
        key = (str(row["expiry"]), float(row["strike"]))
        by_key.setdefault(key, {})[str(row["option_type"])] = row
    complete = [
        (expiry, strike, pair["call"], pair["put"])
        for (expiry, strike), pair in by_key.items()
        if "call" in pair and "put" in pair
    ]
    if not complete:
        return None
    expiry, strike, call_row, put_row = min(
        complete,
        key=lambda item: (
            abs(int(item[2]["dte_calendar"]) - TARGET_ENTRY_DTE),
            abs(item[1] - spot),
            item[1],
            item[0],
        ),
    )
    if not (_leg_ok(call_row) and _leg_ok(put_row)):
        return None
    return call_row, put_row


def _leg_record(row: dict[str, Any], option_type: str) -> dict[str, Any]:
    ask = float(row["ask"])
    return {
        "option_type": option_type,
        "strike": float(row["strike"]),
        "entry_bid": float(row["bid"]),
        "entry_ask": ask,
        "entry_fill": round(ask + COMMISSION_PREMIUM_UNITS, 6),
        "entry_iv": float(row["implied_vol"]),
        "entry_volume": int(row["volume"]),
        "entry_open_interest": int(row["open_interest"]),
        "entry_relative_spread": round(quote_relative_spread(float(row["bid"]), ask), 6),
        "last_mark_bid": float(row["bid"]),
    }


def _open_structures(
    ledger: dict[str, Any],
    rows_by_symbol: dict[str, list[dict[str, Any]]],
    snapshot_date: str,
) -> list[dict[str, Any]]:
    open_symbols = {str(s["symbol"]) for s in ledger["open_structures"]}
    capacity = MAX_OPEN_STRUCTURES - len(ledger["open_structures"])
    if capacity <= 0:
        return []
    # rank eligible symbols by combined ATM leg liquidity (deterministic)
    eligible: list[tuple[float, str, dict[str, Any], dict[str, Any]]] = []
    for symbol, rows in sorted(rows_by_symbol.items()):
        if symbol in open_symbols:
            continue
        legs = atm_straddle_legs(rows)
        if legs is None:
            continue
        call_row, put_row = legs
        liquidity = min(
            int(call_row["open_interest"]) + int(call_row["volume"]),
            int(put_row["open_interest"]) + int(put_row["volume"]),
        )
        eligible.append((float(liquidity), symbol, call_row, put_row))
    eligible.sort(key=lambda item: (-item[0], item[1]))
    opened: list[dict[str, Any]] = []
    for _liquidity, symbol, call_row, put_row in eligible[: min(capacity, MAX_NEW_STRUCTURES_PER_RUN)]:
        call_leg = _leg_record(call_row, "call")
        put_leg = _leg_record(put_row, "put")
        combined_entry_fill = round(call_leg["entry_fill"] + put_leg["entry_fill"], 6)
        if combined_entry_fill <= 0:
            continue
        ledger["structure_counter"] = int(ledger.get("structure_counter", 0)) + 1
        opened.append(
            {
                "structure_id": f"vrp-{symbol}-{snapshot_date}-{int(ledger['structure_counter']):04d}",
                "symbol": symbol,
                "structure_type": "long_straddle",
                "direction_bucket": "neutral",
                "expiry": str(call_row["expiry"]),
                "strike": float(call_row["strike"]),
                "entry_spot": float(call_row["underlying_spot"]),
                "entry_date": snapshot_date,
                "call_leg": call_leg,
                "put_leg": put_leg,
                "combined_entry_fill": combined_entry_fill,
                "combined_last_mark_bid": round(call_leg["last_mark_bid"] + put_leg["last_mark_bid"], 6),
                "marking_sessions": 0,
                "missed_marks": 0,
                "last_mark_date": snapshot_date,
                "both_legs_buy_to_open": True,
                "no_short_option_leg": True,
                "evidence_class": "baseline_vrp_probe_not_a_candidate",
                "ex_ante": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return opened


def _combined_bid(structure: dict[str, Any], row_index: dict[tuple, dict[str, Any]]) -> float | None:
    total = 0.0
    for leg_key in ("call_leg", "put_leg"):
        leg = structure[leg_key]
        key = (
            structure["symbol"],
            structure["expiry"],
            leg["option_type"],
            float(structure["strike"]),
        )
        row = row_index.get(key)
        if row is None:
            return None
        total += float(row["bid"])
    return round(total, 6)


def _dte(expiry: str, as_of: str) -> int:
    try:
        return (date.fromisoformat(expiry) - date.fromisoformat(as_of)).days
    except ValueError:
        return 0


def _exit_reason(structure: dict[str, Any], combined_bid: float, snapshot_date: str) -> str | None:
    entry = float(structure["combined_entry_fill"])
    if entry <= 0:
        return None
    ret = (combined_bid - 2 * COMMISSION_PREMIUM_UNITS) / entry - 1.0
    if ret <= COMBINED_STOP_PCT:
        return "combined_premium_stop"
    if ret >= COMBINED_TARGET_PCT:
        return "combined_premium_target"
    if int(structure["marking_sessions"]) >= MAX_MARKING_SESSIONS:
        return "time_stop"
    if _dte(str(structure["expiry"]), snapshot_date) <= FORCE_CLOSE_DTE:
        return "force_close_near_expiry"
    return None


def _settle(structure: dict[str, Any], combined_exit: float, snapshot_date: str, reason: str) -> dict[str, Any]:
    entry = float(structure["combined_entry_fill"])
    exit_fill = round(max(combined_exit - 2 * COMMISSION_PREMIUM_UNITS, 0.0), 6)
    combined_return = exit_fill / entry - 1.0 if entry > 0 else 0.0
    net_pnl = round(exit_fill - entry, 6)
    return {
        **structure,
        "exit_date": snapshot_date,
        "exit_reason": reason,
        "combined_exit_fill": exit_fill,
        "combined_return": round(combined_return, 6),
        "combined_net_pnl_premium_units": net_pnl,
        "win_loss_marker": "win" if net_pnl > 0 else "loss",
        "outcome_class": "validated_straddle_outcome",
        "counts_as_outcomes": 1,
        "included_in_promotion_gate": False,
    }


def run_straddle_vrp_probe() -> dict[str, Any]:
    snapshot = load_latest_chain_snapshot()
    ledger = _load_ledger()
    if snapshot["chain_snapshot_status"] != "real_chain_snapshot_validated":
        return _write_summary(snapshot["chain_snapshot_status"], ledger, 0, 0, 0)
    snapshot_date = str(snapshot["snapshot_date"])
    rows = snapshot["rows"]
    row_index = {
        (r["symbol"], r["expiry"], r["option_type"], float(r["strike"])): r for r in rows
    }
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_symbol.setdefault(str(row["symbol"]), []).append(row)

    newly_closed = 0
    newly_censored = 0
    if ledger["last_marking_date"] != snapshot_date:
        surviving: list[dict[str, Any]] = []
        for structure in ledger["open_structures"]:
            combined_bid = _combined_bid(structure, row_index)
            if combined_bid is None:
                structure["missed_marks"] = int(structure.get("missed_marks", 0)) + 1
                if structure["missed_marks"] >= MISSING_QUOTE_CENSOR_AFTER:
                    ledger["closed_structures"].append(
                        {
                            **structure,
                            "exit_date": snapshot_date,
                            "exit_reason": "censored_missing_quote_continuity",
                            "outcome_class": "censored_missing_quote_continuity",
                            "counts_as_outcomes": 0,
                            "included_in_promotion_gate": False,
                        }
                    )
                    newly_censored += 1
                else:
                    surviving.append(structure)
                continue
            structure["marking_sessions"] = int(structure["marking_sessions"]) + 1
            structure["missed_marks"] = 0
            structure["combined_last_mark_bid"] = combined_bid
            structure["last_mark_date"] = snapshot_date
            reason = _exit_reason(structure, combined_bid, snapshot_date)
            if reason is not None:
                ledger["closed_structures"].append(_settle(structure, combined_bid, snapshot_date, reason))
                newly_closed += 1
            else:
                surviving.append(structure)
        ledger["open_structures"] = surviving

    opened = _open_structures(ledger, rows_by_symbol, snapshot_date)
    ledger["open_structures"].extend(opened)
    ledger["last_marking_date"] = snapshot_date
    write_json_atomic(LEDGER_PATH, ledger)
    return _write_summary("straddle_vrp_probe_marked", ledger, len(opened), newly_closed, newly_censored)


def _write_summary(
    status: str,
    ledger: dict[str, Any],
    newly_opened: int,
    newly_closed: int,
    newly_censored: int,
) -> dict[str, Any]:
    validated = [
        s for s in ledger["closed_structures"] if s.get("outcome_class") == "validated_straddle_outcome"
    ]
    net = round(sum(float(s["combined_net_pnl_premium_units"]) for s in validated), 6)
    wins = sum(1 for s in validated if s["win_loss_marker"] == "win")
    summary = {
        "artifact_type": "straddle_vrp_probe_summary",
        "probe_version": PROBE_VERSION,
        "probe_status": status,
        "evidence_class": "baseline_vrp_probe_measures_long_premium_cost",
        "baseline_not_candidate": True,
        "included_in_promotion_gate": False,
        "strategy_promotion_allowed": False,
        "one_structure_equals_one_outcome": True,
        "separate_ledger_from_directional_forward_walk": True,
        "open_structure_count": len(ledger["open_structures"]),
        "validated_closed_structure_count": len(validated),
        "validated_win_count": wins,
        "validated_loss_count": len(validated) - wins,
        "validated_net_combined_pnl_premium_units": net,
        "validated_mean_combined_return": (
            round(sum(float(s["combined_return"]) for s in validated) / len(validated), 6)
            if validated
            else None
        ),
        "censored_structure_count": sum(
            1 for s in ledger["closed_structures"] if s.get("outcome_class") == "censored_missing_quote_continuity"
        ),
        "newly_opened_count": newly_opened,
        "newly_closed_count": newly_closed,
        "newly_censored_count": newly_censored,
        "max_open_structures": MAX_OPEN_STRUCTURES,
        "entry_policy": (
            f"ATM ~{TARGET_ENTRY_DTE}DTE straddle (both legs buy-to-open); "
            f"OI>={FORWARD_ENTRY_MIN_OPEN_INTEREST}; volume>={FORWARD_ENTRY_MIN_VOLUME}; "
            f"relative spread<={FORWARD_ENTRY_MAX_RELATIVE_SPREAD:.0%} per leg; "
            f"top-liquidity rotation, <={MAX_OPEN_STRUCTURES} open"
        ),
        "exit_policy": (
            f"combined premium stop {COMBINED_STOP_PCT:+.0%} / target {COMBINED_TARGET_PCT:+.0%} / "
            f"time {MAX_MARKING_SESSIONS} sessions / force-close dte<={FORCE_CLOSE_DTE}"
        ),
        "last_marking_date": ledger["last_marking_date"],
        "not_profitability_claim": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(SUMMARY_PATH, summary)
    return summary


def main() -> int:
    summary = run_straddle_vrp_probe()
    print(
        json.dumps(
            {
                "probe_status": summary["probe_status"],
                "open_structures": summary["open_structure_count"],
                "validated_closed": summary["validated_closed_structure_count"],
                "net_combined_pnl": summary["validated_net_combined_pnl_premium_units"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
