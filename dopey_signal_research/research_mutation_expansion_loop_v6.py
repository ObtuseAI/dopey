"""V6 mutation expansion loop.

Builds V6-specific expansion mutations from the V5 gate rejection diagnosis.
Each expansion record links back to a blocker_id from the blocker matrix and
adds V6-only mutation types that were not necessarily present in the V5 queue.
"""
from __future__ import annotations

import hashlib

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v6_common import (
    MIN_BREAKTHROUGH_PF,
    MUTATION_EXEC_V6_EXPANSION_PATH,
    V5_BREAKTHROUGH_BLOCKER_MATRIX_V6_PATH,
    read_jsonl_file,
    utc_now_iso,
)


__all__ = ["run_v6_mutation_expansion_loop"]


V6_ONLY_MUTATION_TYPES: tuple[tuple[str, str, str], ...] = (
    ("concentration_repair", "concentration_exceeds_max", "Reduce top-symbol / top-sector concentration"),
    ("symbol_broadening", "symbol_coverage_below_min", "Broaden eligible symbol universe"),
    ("sector_broadening", "sector_coverage_below_min", "Broaden eligible sector coverage"),
    ("feature_threshold_retune", "feature_threshold_misalignment", "Re-tune pre-entry feature thresholds"),
    ("regime_filter_retune", "regime_filter_misalignment", "Re-tune regime classification filters"),
    ("watchlist_candidate_isolation", "watchlist_cross_contamination", "Isolate watchlist candidates from shared leakage"),
    ("pf_preserving_holdout_repair", "pf_holdout_tradeoff", "Repair holdout survival while preserving PF"),
)


MUTATION_TYPE_TO_EVAL_AXIS: dict[str, str] = {
    "concentration_repair": "symbol_sector_concentration",
    "symbol_broadening": "symbol_coverage",
    "sector_broadening": "sector_coverage",
    "feature_threshold_retune": "feature_threshold_quality",
    "regime_filter_retune": "regime_filter_quality",
    "watchlist_candidate_isolation": "cross_contamination_risk",
    "pf_preserving_holdout_repair": "pf_holdout_tradeoff",
}


def _expansion_id(idx: int) -> str:
    return f"mut-exp-v6-{idx:04d}-{hashlib.sha1(str(idx).encode()).hexdigest()[:6]}"


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
        "artifact_type": "research_mutation_expansion_record_v6",
        "mutation_id": _expansion_id(idx),
        "mutation_type": mutation_type,
        "source_type": "v6_expansion",
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
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def run_v6_mutation_expansion_loop() -> dict[str, object]:
    blocker_records = read_jsonl_file(V5_BREAKTHROUGH_BLOCKER_MATRIX_V6_PATH)

    expansion_records: list[dict[str, object]] = []
    idx = 0

    # One expansion per blocker in the matrix
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
        intended_fix = f"V6 expansion for {mutation_type} triggered by {blocker_type}"
        expansion_records.append(_expansion_record(idx, mutation_type, blocker_id, diagnosis_id, subfamily_id, intended_fix))
        idx += 1

    # Add V6-only expansion seeds
    for v6_type, blocker_axis, fix_template in V6_ONLY_MUTATION_TYPES:
        subfamily_id = ""
        blocker_id = f"blocker-v6-seed-{blocker_axis}"
        diagnosis_id = ""
        intended_fix = f"V6 expansion seed: {fix_template}"
        expansion_records.append(_expansion_record(idx, v6_type, blocker_id, diagnosis_id, subfamily_id, intended_fix))
        idx += 1

    write_jsonl_file(MUTATION_EXEC_V6_EXPANSION_PATH, expansion_records)
    type_counts: dict[str, int] = {}
    for r in expansion_records:
        mtype = str(r["mutation_type"])
        type_counts[mtype] = type_counts.get(mtype, 0) + 1

    return {
        "v6_expansion_mutation_count": len(expansion_records),
        "v6_expansion_mutation_type_counts": type_counts,
        "v6_expansion_path": str(MUTATION_EXEC_V6_EXPANSION_PATH),
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
    }
