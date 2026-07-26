"""V7 mutation expansion loop.

Builds V7-specific expansion mutations from the V6 trade-active blocker matrix.
Each expansion record links back to a blocker_id from the V6 blocker matrix and
adds V7-only canonical mutation types that were not necessarily present in the
V6 queue, especially trade-active activation and no-trade ratio reduction.
"""
from __future__ import annotations

import hashlib

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v6_common import (
    V5_BREAKTHROUGH_BLOCKER_MATRIX_V6_PATH,
    read_jsonl_file,
)
from dopey_autonomy.signal_research_v7_common import (
    MIN_BREAKTHROUGH_PF,
    MUTATION_EXEC_V7_EXPANSION_PATH,
    RESEARCH_V7_VERSION,
    research_v7_proof_record,
    utc_now_iso,
)


__all__ = ["run_v7_mutation_expansion_loop"]


# V7-only expansion mutation types beyond the V6 canonical set.
V7_ONLY_MUTATION_TYPES: tuple[tuple[str, str, str], ...] = (
    ("trade_active_activation", "no_trade_dominance", "Convert no-trade-dominant watchlist into executable long-call/long-put triggers"),
    ("no_trade_ratio_reduction", "no_trade_ratio_above_max", "Reduce no-trade ratio below the V7 maximum while preserving signal quality"),
    ("long_call_activation", "long_call_trigger_missing", "Add honest long-call entry triggers using only pre-entry information"),
    ("long_put_activation", "long_put_trigger_missing", "Add honest long-put entry triggers using only pre-entry information"),
    ("concentration_repair", "concentration_exceeds_max", "Reduce top-symbol / top-sector concentration"),
    ("symbol_broadening", "symbol_coverage_below_min", "Broaden eligible symbol universe"),
    ("sector_broadening", "sector_coverage_below_min", "Broaden eligible sector coverage"),
    ("feature_threshold_retune", "feature_threshold_misalignment", "Re-tune pre-entry feature thresholds"),
    ("regime_filter_retune", "regime_filter_misalignment", "Re-tune regime classification filters"),
    ("watchlist_candidate_isolation", "watchlist_cross_contamination", "Isolate watchlist candidates from shared feature leakage"),
    ("pf_preserving_holdout_repair", "pf_holdout_tradeoff", "Repair holdout survival while preserving PF above 1.10"),
)


MUTATION_TYPE_TO_EVAL_AXIS: dict[str, str] = {
    "trade_active_activation": "trade_active_ratio",
    "no_trade_ratio_reduction": "no_trade_ratio",
    "long_call_activation": "long_call_sample_count",
    "long_put_activation": "long_put_sample_count",
    "concentration_repair": "symbol_sector_concentration",
    "symbol_broadening": "symbol_coverage",
    "sector_broadening": "sector_coverage",
    "feature_threshold_retune": "feature_threshold_quality",
    "regime_filter_retune": "regime_filter_quality",
    "watchlist_candidate_isolation": "cross_contamination_risk",
    "pf_preserving_holdout_repair": "pf_holdout_tradeoff",
}


def _expansion_id(idx: int) -> str:
    return f"mut-exp-v7-{idx:04d}-{hashlib.sha1(str(idx).encode()).hexdigest()[:6]}"


def _blocker_to_mutation_type(blocker_type: str) -> str | None:
    mapping = {
        "drawdown_exceeds_max": "drawdown_repair",
        "holdout_survival_failed": "holdout_survival_repair",
        "split_pass_rate_below_threshold": "split_pass_repair",
        "expectancy_below_threshold": "expectancy_repair",
        "stress_survival_failed": "stress_survival_repair",
        "outlier_dependence_high": "outlier_dependence_repair",
        "concentration_exceeds_max": "concentration_repair",
        "symbol_coverage_below_min": "symbol_broadening",
        "sector_coverage_below_min": "sector_broadening",
    }
    return mapping.get(blocker_type)


def _expansion_record(
    idx: int,
    mutation_type: str,
    blocker_id: str,
    diagnosis_id: str,
    subfamily_id: str,
    intended_fix: str,
) -> dict[str, object]:
    rec = {
        "artifact_type": "research_mutation_expansion_record_v7",
        "mutation_id": _expansion_id(idx),
        "mutation_type": mutation_type,
        "source_type": "v7_expansion",
        "source_blocker_id": blocker_id,
        "source_diagnosis_id": diagnosis_id,
        "parent_family_id": subfamily_id.split("|", 1)[0] if subfamily_id else "",
        "parent_subfamily_id": subfamily_id,
        "parent_cohort_id": subfamily_id.split("|", 1)[0] if subfamily_id else "",
        "intended_fix": intended_fix,
        "expected_evaluation_axis": MUTATION_TYPE_TO_EVAL_AXIS.get(mutation_type, mutation_type),
        "candidate_generation_plan_count": 300,
        "applicable": True,
        "skipped_reason": "",
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "blocks_no_trade_only_breakthrough": True,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def run_v7_mutation_expansion_loop() -> dict[str, object]:
    blocker_records = read_jsonl_file(V5_BREAKTHROUGH_BLOCKER_MATRIX_V6_PATH)

    expansion_records: list[dict[str, object]] = []
    idx = 0

    # One V7 expansion per V6 blocker in the matrix.
    for blocker in blocker_records:
        if not isinstance(blocker, dict):
            continue
        blocker_id = str(blocker.get("blocker_id", ""))
        diagnosis_id = str(blocker.get("diagnosis_id", ""))
        blocker_type = str(blocker.get("blocker_type", ""))
        subfamily_id = str(blocker.get("stable_subfamily_id", ""))
        mutation_type = _blocker_to_mutation_type(blocker_type)
        if not mutation_type:
            continue
        intended_fix = f"V7 expansion for {mutation_type} triggered by {blocker_type}"
        expansion_records.append(
            _expansion_record(idx, mutation_type, blocker_id, diagnosis_id, subfamily_id, intended_fix)
        )
        idx += 1

    # Add V7-only expansion seeds (trade-active activation, no-trade reduction, etc.).
    for v7_type, blocker_axis, fix_template in V7_ONLY_MUTATION_TYPES:
        subfamily_id = ""
        blocker_id = f"blocker-v7-seed-{blocker_axis}"
        diagnosis_id = ""
        intended_fix = f"V7 expansion seed: {fix_template}"
        expansion_records.append(
            _expansion_record(idx, v7_type, blocker_id, diagnosis_id, subfamily_id, intended_fix)
        )
        idx += 1

    write_jsonl_file(MUTATION_EXEC_V7_EXPANSION_PATH, expansion_records)
    type_counts: dict[str, int] = {}
    for r in expansion_records:
        mtype = str(r["mutation_type"])
        type_counts[mtype] = type_counts.get(mtype, 0) + 1

    summary = {
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "v7_expansion_mutation_count": len(expansion_records),
        "v7_expansion_mutation_type_counts": type_counts,
        "v7_expansion_path": str(MUTATION_EXEC_V7_EXPANSION_PATH),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "blocks_no_trade_only_breakthrough": True,
    }

    proof_path = MUTATION_EXEC_V7_EXPANSION_PATH.parent / (MUTATION_EXEC_V7_EXPANSION_PATH.stem + "_proof.jsonl")
    write_jsonl_file(
        proof_path,
        [research_v7_proof_record("research-mutation-expansion-loop-v7", "v7_expansion_complete", summary)],
    )
    summary["v7_expansion_proof_path"] = str(proof_path)
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v7_mutation_expansion_loop(), indent=2, sort_keys=True, default=str))
