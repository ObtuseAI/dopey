"""V6 mutation queue executor.

Reads the V5 mutation queue (132 records, read-only) and emits V6 execution
records. Each execution record maps the V5 mutation type to a V6 canonical
mutation type, preserves parent family/subfamily linkage, and carries a
candidate-generation plan count without lowering thresholds or enabling live
trading.
"""
from __future__ import annotations

import hashlib

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v6_common import (
    MIN_BREAKTHROUGH_PF,
    MUTATION_EXEC_V6_FAILURES_PATH,
    MUTATION_EXEC_V6_PROOF_PATH,
    MUTATION_EXEC_V6_RECORDS_PATH,
    MUTATION_EXEC_V6_SUMMARY_PATH,
    RESEARCH_V6_VERSION,
    is_forbidden_symbol,
    load_v5_mutation_queue_records,
    research_v6_proof_record,
    utc_now_iso,
)
from dopey_signal_research.research_mutation_expansion_loop_v6 import run_v6_mutation_expansion_loop


__all__ = ["execute_v6_mutation_queue", "run_research_mutation_queue_executor_v6"]


# 24 V6 canonical mutation types
MUTATION_TYPES_V6: tuple[str, ...] = (
    "holdout_survival_repair",
    "split_pass_repair",
    "concentration_repair",
    "drawdown_repair",
    "expectancy_repair",
    "stress_survival_repair",
    "outlier_dependence_repair",
    "symbol_broadening",
    "sector_broadening",
    "symbol_pruning",
    "sector_pruning",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "hold_window_retune",
    "stop_target_retune",
    "no_trade_filter_injection",
    "feature_threshold_retune",
    "regime_filter_retune",
    "recent_market_reinforcement",
    "sample_expansion",
    "family_subfamily_split",
    "watchlist_candidate_isolation",
    "pf_preserving_holdout_repair",
)


V5_TO_V6_MUTATION_TYPE: dict[str, str] = {
    "pf_repair_above_110": "pf_preserving_holdout_repair",
    "holdout_repair": "holdout_survival_repair",
    "split_repair": "split_pass_repair",
    "expectancy_repair": "expectancy_repair",
    "drawdown_repair": "drawdown_repair",
    "no_trade_filter_injection": "no_trade_filter_injection",
    "symbol_pruning": "symbol_pruning",
    "sector_pruning": "sector_pruning",
    "subfamily_split": "family_subfamily_split",
    "dte_retune": "dte_retune",
    "moneyness_retune": "moneyness_retune",
    "exit_policy_retune": "exit_policy_retune",
    "risk_filter_retune": "feature_threshold_retune",
    "relative_strength_retune": "feature_threshold_retune",
    "volatility_retune": "feature_threshold_retune",
    "volume_retune": "feature_threshold_retune",
    "stop_target_retune": "stop_target_retune",
    "profitable_slice_reinforcement": "sample_expansion",
    "loss_driver_suppression": "outlier_dependence_repair",
    "hold_window_retune": "hold_window_retune",
    "stress_specific_repair": "stress_survival_repair",
    "recent_market_reinforcement": "recent_market_reinforcement",
}


MUTATION_TYPE_TO_INTENDED_FIX: dict[str, str] = {
    "holdout_survival_repair": "Tighten pre-entry filters to improve holdout survival without future leakage",
    "split_pass_repair": "Stabilize cohort across time-based splits; reduce single-window dependence",
    "concentration_repair": "Reduce top-symbol and top-sector concentration",
    "drawdown_repair": "Tighten stops and reduce per-trade risk",
    "expectancy_repair": "Filter low-expectancy contexts using pre-entry edge estimates",
    "stress_survival_repair": "Add stress-period filters from historical regime proxies",
    "outlier_dependence_repair": "Cap dependence on extreme trades via robust statistics",
    "symbol_broadening": "Broaden eligible symbol universe while preserving coverage",
    "sector_broadening": "Broaden eligible sector coverage while preserving coverage",
    "symbol_pruning": "Prune worst-attribution symbols while preserving gate coverage",
    "sector_pruning": "Prune worst-attribution sectors while preserving gate coverage",
    "dte_retune": "Re-evaluate DTE windows using only pre-entry term structure",
    "moneyness_retune": "Re-evaluate moneyness strikes using pre-entry spot and historical skew",
    "exit_policy_retune": "Re-evaluate stop/target asymmetry with pre-entry statistics",
    "hold_window_retune": "Evaluate hold windows 1/2/3/5/7 days using prior holding-period stats",
    "stop_target_retune": "Re-tune stop/target combinations using historical ranges",
    "no_trade_filter_injection": "Extend no-trade rules without holdout-outcome leakage",
    "feature_threshold_retune": "Re-tune pre-entry feature thresholds using prior historical bins",
    "regime_filter_retune": "Re-tune regime filters using historical regime labels only",
    "recent_market_reinforcement": "Reinforce on recent market window; verify no leakage",
    "sample_expansion": "Expand sample by replicating profitable pre-entry slices",
    "family_subfamily_split": "Split family into demote/rescue branches by historical behavior",
    "watchlist_candidate_isolation": "Isolate watchlist candidates from shared feature leakage",
    "pf_preserving_holdout_repair": "Repair holdout survival while keeping PF above 1.10",
}


MUTATION_TYPE_TO_EVAL_AXIS: dict[str, str] = {
    "holdout_survival_repair": "holdout_survival",
    "split_pass_repair": "split_pass_rate",
    "concentration_repair": "symbol_sector_concentration",
    "drawdown_repair": "max_drawdown",
    "expectancy_repair": "expectancy",
    "stress_survival_repair": "stress_survival",
    "outlier_dependence_repair": "outlier_dependence",
    "symbol_broadening": "symbol_coverage",
    "sector_broadening": "sector_coverage",
    "symbol_pruning": "symbol_concentration",
    "sector_pruning": "sector_concentration",
    "dte_retune": "dte_holding_window",
    "moneyness_retune": "moneyness",
    "exit_policy_retune": "stop_target_asymmetry",
    "hold_window_retune": "hold_window",
    "stop_target_retune": "stop_target_combination",
    "no_trade_filter_injection": "no_trade_filter_quality",
    "feature_threshold_retune": "feature_threshold_quality",
    "regime_filter_retune": "regime_filter_quality",
    "recent_market_reinforcement": "recent_window_performance",
    "sample_expansion": "sample_count",
    "family_subfamily_split": "family_separation",
    "watchlist_candidate_isolation": "cross_contamination_risk",
    "pf_preserving_holdout_repair": "pf_holdout_tradeoff",
}


def _candidate_generation_plan_count(mutation_type: str) -> int:
    if mutation_type in {
        "holdout_survival_repair",
        "split_pass_repair",
        "concentration_repair",
        "drawdown_repair",
        "expectancy_repair",
        "stress_survival_repair",
        "outlier_dependence_repair",
        "pf_preserving_holdout_repair",
    }:
        return 700
    if mutation_type in {
        "symbol_pruning",
        "sector_pruning",
        "symbol_broadening",
        "sector_broadening",
        "watchlist_candidate_isolation",
        "family_subfamily_split",
    }:
        return 400
    if mutation_type == "sample_expansion":
        return 600
    return 500


def _make_execution_id(idx: int, source_id: str) -> str:
    digest = hashlib.sha1(f"{idx}:{source_id}".encode()).hexdigest()[:6]
    return f"mut-exec-v6-{idx:04d}-{digest}"


def _is_applicable(v5_type: str, subfamily_id: str) -> tuple[bool, str]:
    if not v5_type:
        return False, "missing_v5_mutation_type"
    if v5_type not in V5_TO_V6_MUTATION_TYPE:
        return False, "unknown_v5_mutation_type"
    if subfamily_id and any(is_forbidden_symbol(s) for s in subfamily_id.split("|") if s):
        return False, "forbidden_symbol_in_subfamily"
    return True, ""


def _execution_record(
    idx: int,
    v5_record: dict[str, object],
) -> dict[str, object]:
    v5_type = str(v5_record.get("mutation_type", ""))
    source_id = str(v5_record.get("mutation_id", f"v5-{idx:04d}"))
    subfamily_id = str(v5_record.get("stable_subfamily_id", v5_record.get("parent_subfamily_id", "")))
    family_id = str(v5_record.get("stable_family_id", v5_record.get("parent_family_id", "")))
    cohort_id = str(v5_record.get("parent_cohort_id", ""))
    applicable, skip_reason = _is_applicable(v5_type, subfamily_id)
    mutation_type = V5_TO_V6_MUTATION_TYPE.get(v5_type, v5_type)

    rec = {
        "artifact_type": "research_mutation_execution_record_v6",
        "mutation_id": _make_execution_id(idx, source_id),
        "mutation_type": mutation_type,
        "source_v5_mutation_id": source_id,
        "source_v5_mutation_type": v5_type,
        "source_type": str(v5_record.get("source_type", "")),
        "parent_family_id": family_id,
        "parent_subfamily_id": subfamily_id,
        "parent_cohort_id": cohort_id,
        "intended_fix": MUTATION_TYPE_TO_INTENDED_FIX.get(mutation_type, f"V6 execution for {mutation_type}"),
        "expected_evaluation_axis": MUTATION_TYPE_TO_EVAL_AXIS.get(mutation_type, mutation_type),
        "candidate_generation_plan_count": _candidate_generation_plan_count(mutation_type) if applicable else 0,
        "applicable": applicable,
        "skipped_reason": skip_reason,
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def execute_v6_mutation_queue() -> dict[str, object]:
    v5_queue = load_v5_mutation_queue_records()
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    mutation_type_counts: dict[str, int] = {}

    for idx, v5_record in enumerate(v5_queue):
        if not isinstance(v5_record, dict):
            continue
        rec = _execution_record(idx, v5_record)
        records.append(rec)
        mtype = str(rec["mutation_type"])
        mutation_type_counts[mtype] = mutation_type_counts.get(mtype, 0) + 1
        if not rec["applicable"]:
            failures.append(rec)

    write_jsonl_file(MUTATION_EXEC_V6_RECORDS_PATH, records)
    write_jsonl_file(MUTATION_EXEC_V6_FAILURES_PATH, failures)

    expansion_summary = run_v6_mutation_expansion_loop()
    expanded_count = expansion_summary.get("v6_expansion_mutation_count", 0)

    status = "research_mutation_queue_executed_v6"
    summary = {
        "artifact_type": "research_mutation_queue_executor_v6_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "research_mutation_queue_executor_v6_status": status,
        "input_v5_mutation_count": len(v5_queue),
        "executed_mutation_count": sum(1 for r in records if r["applicable"]),
        "expanded_mutation_count": expanded_count,
        "failed_mutation_count": len(failures),
        "mutation_type_counts": mutation_type_counts,
        "v6_expansion_mutation_type_counts": expansion_summary.get("v6_expansion_mutation_type_counts", {}),
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(MUTATION_EXEC_V6_SUMMARY_PATH, summary)
    write_jsonl_file(
        MUTATION_EXEC_V6_PROOF_PATH,
        [research_v6_proof_record("research-mutation-queue-executor-v6", status, summary)],
    )
    return summary


run_research_mutation_queue_executor_v6 = execute_v6_mutation_queue


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(execute_v6_mutation_queue(), indent=2, sort_keys=True, default=str))
