"""V7 mutation queue executor.

Reads the immutable V6 mutation queue (50 records, read-only) and emits V7
execution records. Each execution record maps the V6 mutation type to a V7
canonical mutation type, preserves parent family/subfamily linkage, and carries
a candidate-generation plan count. V7 never lowers the breakthrough profit-factor
floor, never enables live trading, and blocks no-trade-only breakthroughs.
"""
from __future__ import annotations

import hashlib

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    MIN_BREAKTHROUGH_PF,
    MUTATION_EXEC_V7_FAILURES_PATH,
    MUTATION_EXEC_V7_PROOF_PATH,
    MUTATION_EXEC_V7_RECORDS_PATH,
    MUTATION_EXEC_V7_SUMMARY_PATH,
    RESEARCH_V7_VERSION,
    is_forbidden_symbol,
    load_v6_mutation_queue_records,
    research_v7_proof_record,
    utc_now_iso,
)
from dopey_signal_research.research_mutation_expansion_loop_v7 import run_v7_mutation_expansion_loop


__all__ = ["execute_v7_mutation_queue", "run_research_mutation_queue_executor_v7"]


# V7 canonical mutation types. The list intentionally includes
# trade_active_activation and no_trade_ratio_reduction to convert no-trade-
# dominant watchlist candidates into honest trade-active breakthroughs.
MUTATION_TYPES_V7: tuple[str, ...] = (
    "trade_active_activation",
    "no_trade_ratio_reduction",
    "long_call_activation",
    "long_put_activation",
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
    "feature_threshold_retune",
    "regime_filter_retune",
    "recent_market_reinforcement",
    "sample_expansion",
    "family_subfamily_split",
    "watchlist_candidate_isolation",
    "pf_preserving_holdout_repair",
    "public_data_reinforcement",
    "fixture_zero_guard",
)


V6_TO_V7_MUTATION_TYPE: dict[str, str] = {
    "pf_repair_above_110": "pf_preserving_holdout_repair",
    "holdout_repair": "holdout_survival_repair",
    "split_repair": "split_pass_repair",
    "expectancy_repair": "expectancy_repair",
    "drawdown_repair": "drawdown_repair",
    "no_trade_filter_injection": "no_trade_ratio_reduction",
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
    "v5_blocker_repair": "trade_active_activation",
    "public_lake_reinforcement": "public_data_reinforcement",
    "fixture_zero_guard": "fixture_zero_guard",
}


MUTATION_TYPE_TO_INTENDED_FIX: dict[str, str] = {
    "trade_active_activation": "Convert no-trade-dominant candidate into executable long-call/long-put triggers without future leakage",
    "no_trade_ratio_reduction": "Reduce no-trade ratio below the V7 maximum while preserving signal quality",
    "long_call_activation": "Add honest long-call entry triggers using only pre-entry information",
    "long_put_activation": "Add honest long-put entry triggers using only pre-entry information",
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
    "feature_threshold_retune": "Re-tune pre-entry feature thresholds using prior historical bins",
    "regime_filter_retune": "Re-tune regime filters using historical regime labels only",
    "recent_market_reinforcement": "Reinforce on recent market window; verify no leakage",
    "sample_expansion": "Expand sample by replicating profitable pre-entry slices",
    "family_subfamily_split": "Split family into demote/rescue branches by historical behavior",
    "watchlist_candidate_isolation": "Isolate watchlist candidates from shared feature leakage",
    "pf_preserving_holdout_repair": "Repair holdout survival while keeping PF above 1.10",
    "public_data_reinforcement": "Reinforce signal on additional public data sources without leakage",
    "fixture_zero_guard": "Maintain zero SIM/TEST/FIXTURE/SYNTH champion exposure",
}


MUTATION_TYPE_TO_EVAL_AXIS: dict[str, str] = {
    "trade_active_activation": "trade_active_ratio",
    "no_trade_ratio_reduction": "no_trade_ratio",
    "long_call_activation": "long_call_sample_count",
    "long_put_activation": "long_put_sample_count",
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
    "feature_threshold_retune": "feature_threshold_quality",
    "regime_filter_retune": "regime_filter_quality",
    "recent_market_reinforcement": "recent_window_performance",
    "sample_expansion": "sample_count",
    "family_subfamily_split": "family_separation",
    "watchlist_candidate_isolation": "cross_contamination_risk",
    "pf_preserving_holdout_repair": "pf_holdout_tradeoff",
    "public_data_reinforcement": "public_data_coverage",
    "fixture_zero_guard": "fixture_champion_count",
}


def _candidate_generation_plan_count(mutation_type: str) -> int:
    if mutation_type in {
        "trade_active_activation",
        "no_trade_ratio_reduction",
        "long_call_activation",
        "long_put_activation",
    }:
        return 800
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
    if mutation_type == "fixture_zero_guard":
        return 100
    return 500


def _make_execution_id(idx: int, source_id: str) -> str:
    digest = hashlib.sha1(f"{idx}:{source_id}".encode()).hexdigest()[:6]
    return f"mut-exec-v7-{idx:04d}-{digest}"


def _is_applicable(v6_type: str, subfamily_id: str) -> tuple[bool, str]:
    if not v6_type:
        return False, "missing_v6_mutation_type"
    if v6_type not in V6_TO_V7_MUTATION_TYPE:
        return False, "unknown_v6_mutation_type"
    if subfamily_id and any(is_forbidden_symbol(s) for s in subfamily_id.split("|") if s):
        return False, "forbidden_symbol_in_subfamily"
    return True, ""


def _execution_record(
    idx: int,
    v6_record: dict[str, object],
) -> dict[str, object]:
    v6_type = str(v6_record.get("mutation_type", ""))
    source_id = str(v6_record.get("mutation_id", f"v6-{idx:04d}"))
    subfamily_id = str(
        v6_record.get("stable_subfamily_id", v6_record.get("parent_subfamily_id", ""))
    )
    family_id = str(v6_record.get("stable_family_id", v6_record.get("parent_family_id", "")))
    cohort_id = str(v6_record.get("parent_cohort_id", ""))
    applicable, skip_reason = _is_applicable(v6_type, subfamily_id)
    mutation_type = V6_TO_V7_MUTATION_TYPE.get(v6_type, v6_type)

    rec = {
        "artifact_type": "research_mutation_execution_record_v7",
        "mutation_id": _make_execution_id(idx, source_id),
        "mutation_type": mutation_type,
        "source_v6_mutation_id": source_id,
        "source_v6_mutation_type": v6_type,
        "source_type": str(v6_record.get("source_type", "")),
        "parent_family_id": family_id,
        "parent_subfamily_id": subfamily_id,
        "parent_cohort_id": cohort_id,
        "intended_fix": MUTATION_TYPE_TO_INTENDED_FIX.get(mutation_type, f"V7 execution for {mutation_type}"),
        "expected_evaluation_axis": MUTATION_TYPE_TO_EVAL_AXIS.get(mutation_type, mutation_type),
        "candidate_generation_plan_count": _candidate_generation_plan_count(mutation_type) if applicable else 0,
        "applicable": applicable,
        "skipped_reason": skip_reason,
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "blocks_no_trade_only_breakthrough": True,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def execute_v7_mutation_queue() -> dict[str, object]:
    v6_queue = load_v6_mutation_queue_records()
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    mutation_type_counts: dict[str, int] = {}

    for idx, v6_record in enumerate(v6_queue):
        if not isinstance(v6_record, dict):
            continue
        rec = _execution_record(idx, v6_record)
        records.append(rec)
        mtype = str(rec["mutation_type"])
        mutation_type_counts[mtype] = mutation_type_counts.get(mtype, 0) + 1
        if not rec["applicable"]:
            failures.append(rec)

    write_jsonl_file(MUTATION_EXEC_V7_RECORDS_PATH, records)
    write_jsonl_file(MUTATION_EXEC_V7_FAILURES_PATH, failures)

    expansion_summary = run_v7_mutation_expansion_loop()
    expanded_count = expansion_summary.get("v7_expansion_mutation_count", 0)

    status = "research_mutation_queue_executed_v7"
    summary = {
        "artifact_type": "research_mutation_queue_executor_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "research_mutation_queue_executor_v7_status": status,
        "input_v6_mutation_count": len(v6_queue),
        "executed_mutation_count": sum(1 for r in records if r["applicable"]),
        "expanded_mutation_count": expanded_count,
        "failed_mutation_count": len(failures),
        "mutation_type_counts": mutation_type_counts,
        "v7_expansion_mutation_type_counts": expansion_summary.get("v7_expansion_mutation_type_counts", {}),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "blocks_no_trade_only_breakthrough": True,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(MUTATION_EXEC_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        MUTATION_EXEC_V7_PROOF_PATH,
        [research_v7_proof_record("research-mutation-queue-executor-v7", status, summary)],
    )
    return summary


run_research_mutation_queue_executor_v7 = execute_v7_mutation_queue


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(execute_v7_mutation_queue(), indent=2, sort_keys=True, default=str))
