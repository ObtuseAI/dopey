"""V5 mutation queue executor.

Executes the V4 mutation queue (read-only) and emits V5 execution records.
Each V4 mutation that is applicable to V5 produces a V5 execution record
with a candidate generation plan. The executor does NOT lower breakthrough
thresholds and does NOT enable live trading.
"""
from __future__ import annotations

import hashlib

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    MUTATION_EXEC_V5_FAILURES_PATH,
    MUTATION_EXEC_V5_RECORDS_PATH,
    MUTATION_EXEC_V5_SUMMARY_PATH,
    RESEARCH_V5_VERSION,
    V4_REPAIR_TARGETS_V5_PATH,
    is_forbidden_symbol,
    utc_now_iso,
)
from dopey_signal_research.v4_result_analyzer_v5 import _read_jsonl_with_source


__all__ = ["execute_v5_mutation_queue"]


# 22 mutation types (V5 spec)
MUTATION_TYPES_V5: tuple[str, ...] = (
    "pf_repair_above_110",
    "holdout_repair",
    "split_repair",
    "expectancy_repair",
    "drawdown_repair",
    "no_trade_filter_injection",
    "symbol_pruning",
    "sector_pruning",
    "subfamily_split",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "risk_filter_retune",
    "relative_strength_retune",
    "volatility_retune",
    "volume_retune",
    "stop_target_retune",
    "profitable_slice_reinforcement",
    "loss_driver_suppression",
    "hold_window_retune",
    "stress_specific_repair",
    "recent_market_reinforcement",
)


MUTATION_TYPE_TO_INTENDED_FIX: dict[str, str] = {
    "pf_repair_above_110": "tighten entries and exits; prune negative-expectancy slices; lift PF above 1.10",
    "holdout_repair": "tighten pre-entry filters; improve holdout survival",
    "split_repair": "stabilize cohort across splits; reduce single-window dependence",
    "expectancy_repair": "filter low-edge contexts; raise average expectancy",
    "drawdown_repair": "tighten stops; reduce concurrent exposure; cap single-symbol risk",
    "no_trade_filter_injection": "extend V4 no-trade rules into V5; preserve leakage guard",
    "symbol_pruning": "prune worst-attribution symbols while preserving gate coverage",
    "sector_pruning": "prune worst-attribution sectors while preserving coverage",
    "subfamily_split": "split volume family into demote/rescue branches",
    "dte_retune": "re-evaluate DTE 14 vs 21 windows",
    "moneyness_retune": "evaluate 1% vs 3% OTM with new slices",
    "exit_policy_retune": "evaluate stop/target asymmetry across slices",
    "risk_filter_retune": "re-tune risk filter thresholds from V4 slices",
    "relative_strength_retune": "re-evaluate RS thresholds; align with continuation subfamilies",
    "volatility_retune": "re-evaluate volatility thresholds",
    "volume_retune": "re-evaluate volume thresholds for V5 candidates",
    "stop_target_retune": "re-tune stop/target combinations",
    "profitable_slice_reinforcement": "reinforce top profitable slice; replicate dimensions",
    "loss_driver_suppression": "suppress loss-driver slice; reinforce profitable slice dimensions",
    "hold_window_retune": "evaluate hold_window=1d, 2d, 3d, 5d, 7d",
    "stress_specific_repair": "evaluate stress-specific axes; ensure survival under stress",
    "recent_market_reinforcement": "reinforce on recent market window; verify no leakage",
}


MUTATION_TYPE_TO_EVAL_AXIS: dict[str, str] = {
    "pf_repair_above_110": "profit_factor",
    "holdout_repair": "holdout_survival",
    "split_repair": "split_pass_rate",
    "expectancy_repair": "expectancy",
    "drawdown_repair": "max_drawdown",
    "no_trade_filter_injection": "no_trade_filter_quality",
    "symbol_pruning": "symbol_concentration",
    "sector_pruning": "sector_concentration",
    "subfamily_split": "family_separation",
    "dte_retune": "dte_holding_window",
    "moneyness_retune": "moneyness",
    "exit_policy_retune": "stop_target_asymmetry",
    "risk_filter_retune": "risk_filter_quality",
    "relative_strength_retune": "relative_strength",
    "volatility_retune": "volatility",
    "volume_retune": "volume",
    "stop_target_retune": "stop_target_combination",
    "profitable_slice_reinforcement": "net_pnl",
    "loss_driver_suppression": "net_pnl",
    "hold_window_retune": "hold_window",
    "stress_specific_repair": "stress_survival",
    "recent_market_reinforcement": "recent_window_performance",
}


def _make_mutation_id(idx: int) -> str:
    return f"mut-exec-v5-{idx:04d}-{hashlib.sha1(str(idx).encode()).hexdigest()[:6]}"


def _candidate_generation_plan(repair_target: dict[str, object]) -> int:
    """Deterministic plan count for a V5 mutation.

    PF/holdout/split/expectancy/drawdown repair gets 700 candidates.
    No-trade / pruning gets 400. Retune gets 500.
    """
    rtype = str(repair_target.get("repair_type", ""))
    if rtype in {
        "pf_repair_above_110",
        "holdout_repair",
        "split_repair",
        "expectancy_repair",
        "drawdown_repair",
        "profitable_slice_reinforcement",
        "loss_driver_suppression",
    }:
        return 700
    if rtype in {"no_trade_filter_injection", "symbol_pruning", "sector_pruning", "subfamily_split"}:
        return 400
    return 500


def _is_applicable(repair_target: dict[str, object]) -> tuple[bool, str]:
    """Decide whether a repair target is applicable to V5 execution.

    V5 must not lower breakthrough thresholds. All repair targets that
    target the 1.10 PF floor are always applicable (they're meant to
    raise PF, not lower it).
    """
    rtype = str(repair_target.get("repair_type", ""))
    if not rtype:
        return False, "missing_repair_type"
    if rtype not in MUTATION_TYPE_TO_INTENDED_FIX:
        return False, "unknown_mutation_type"
    stable_subfamily = str(repair_target.get("stable_subfamily_id", ""))
    if stable_subfamily and any(is_forbidden_symbol(s) for s in stable_subfamily.split("|")):
        return False, "forbidden_symbol_in_subfamily"
    return True, "applicable"


def _execution_record(
    idx: int,
    repair_target: dict[str, object],
    applicable: bool,
    skip_reason: str,
) -> dict[str, object]:
    rtype = str(repair_target.get("repair_type", ""))
    rec = {
        "artifact_type": "research_mutation_execution_record_v5",
        "mutation_id": _make_mutation_id(idx),
        "mutation_type": rtype,
        "source_v4_repair_target_id": str(repair_target.get("repair_target_id", "")),
        "source_type": str(repair_target.get("source_type", "")),
        "parent_family_id": str(repair_target.get("stable_family_id", "")),
        "parent_subfamily_id": str(repair_target.get("stable_subfamily_id", "")),
        "parent_cohort_id": str(repair_target.get("stable_subfamily_id", "")).split("|", 1)[0] if repair_target.get("stable_subfamily_id") else "",
        "intended_fix": MUTATION_TYPE_TO_INTENDED_FIX.get(rtype, str(repair_target.get("intended_fix", ""))),
        "expected_evaluation_axis": MUTATION_TYPE_TO_EVAL_AXIS.get(rtype, str(repair_target.get("expected_evaluation_axis", ""))),
        "candidate_generation_plan_count": _candidate_generation_plan(repair_target) if applicable else 0,
        "applicable": applicable,
        "skipped_reason": "" if applicable else skip_reason,
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def execute_v5_mutation_queue() -> dict[str, object]:
    """Execute V4 repair targets as V5 mutations and emit records.

    Reads V4 repair targets produced by the V4 result analyzer (Workstream D).
    If those are missing, falls back to the V4 mutation queue (read-only).
    """
    repair_targets: list[dict[str, object]] = []
    if V4_REPAIR_TARGETS_V5_PATH.exists():
        for line in V4_REPAIR_TARGETS_V5_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = _parse_repair_line(line)
                if rec:
                    repair_targets.append(rec)
            except Exception:  # noqa: BLE001
                continue

    # The repair-target file uses repair_type + source_type + stable_subfamily_id + intended_fix
    if not repair_targets:
        # Fallback: build repair targets from V4 mutation queue
        v4_queue, _ = _read_jsonl_with_source("research_mutation_queue_v4.jsonl")
        for r in v4_queue:
            if not isinstance(r, dict):
                continue
            repair_targets.append(
                {
                    "repair_type": str(r.get("mutation_type", "")),
                    "source_type": str(r.get("source_type", "")),
                    "stable_family_id": str(r.get("stable_family_id", "")),
                    "stable_subfamily_id": str(r.get("stable_subfamily_id", "")),
                    "intended_fix": "",
                    "expected_evaluation_axis": "",
                }
            )

    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    mutation_type_counts: dict[str, int] = {}
    for idx, target in enumerate(repair_targets):
        applicable, skip_reason = _is_applicable(target)
        rec = _execution_record(idx, target, applicable, skip_reason)
        records.append(rec)
        rtype = str(rec["mutation_type"])
        mutation_type_counts[rtype] = mutation_type_counts.get(rtype, 0) + 1
        if not applicable:
            failures.append(rec)

    write_jsonl_file(MUTATION_EXEC_V5_RECORDS_PATH, records)
    write_jsonl_file(MUTATION_EXEC_V5_FAILURES_PATH, failures)

    summary = {
        "artifact_type": "research_mutation_queue_executor_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "research_mutation_queue_executor_v5_status": "research_mutation_queue_executed_v5",
        "input_v4_mutation_count": len(repair_targets),
        "executed_mutation_count": sum(1 for r in records if r["applicable"]),
        "expanded_mutation_count": len(records),
        "failed_mutation_count": len(failures),
        "mutation_type_counts": mutation_type_counts,
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(
        MUTATION_EXEC_V5_SUMMARY_PATH.parent / "research_mutation_queue_executor_v5_summary.jsonl",
        [summary],
    )
    # Also write the canonical summary JSON
    from dopey_autonomy.public_champion_common import write_summary_with_hash

    write_summary_with_hash(MUTATION_EXEC_V5_SUMMARY_PATH, summary)
    return summary


def _parse_repair_line(line: str) -> dict[str, object] | None:
    import json as _json

    try:
        rec = _json.loads(line)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(rec, dict):
        return None
    return {
        "repair_type": str(rec.get("repair_type", rec.get("mutation_type", ""))),
        "source_type": str(rec.get("source_type", "")),
        "stable_family_id": str(rec.get("stable_family_id", rec.get("parent_family_id", ""))),
        "stable_subfamily_id": str(rec.get("stable_subfamily_id", rec.get("parent_subfamily_id", ""))),
        "intended_fix": str(rec.get("intended_fix", "")),
        "expected_evaluation_axis": str(rec.get("expected_evaluation_axis", "")),
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(execute_v5_mutation_queue(), indent=2, sort_keys=True, default=str))
