"""V5 mutation expansion loop.

Adds V5-specific expansion mutations on top of the V4-derived V5 mutations
executed by `research_mutation_queue_executor_v5.py`. Expansion mutations
cover the remaining axes in the 22-type taxonomy that were not surfaced
as V4 repair targets.
"""
from __future__ import annotations

import hashlib

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    MUTATION_EXEC_V5_EXPANSION_PATH,
    utc_now_iso,
)


__all__ = ["run_v5_mutation_expansion_loop"]


# V5 expansion mutations: one per type, covering axes that may not have
# been surfaced by V4 repair targets but are still part of the 22-type V5
# taxonomy. Each expansion mutation gets a target subfamily drawn from
# the 8 V5 subfamilies, with a deterministic seed.
V5_EXPANSION_SEEDS: tuple[tuple[str, str], ...] = (
    # (mutation_type, stable_subfamily_id)
    ("pf_repair_above_110", "continuation|pullback|high_volume"),
    ("pf_repair_above_110", "continuation|pullback|relative_strength"),
    ("holdout_repair", "continuation|trend_pause|volume_confirmed"),
    ("holdout_repair", "continuation|post_compression_followthrough"),
    ("split_repair", "volume|dry_up_breakout"),
    ("split_repair", "volume|dry_up_reclaim"),
    ("expectancy_repair", "volume|climax_reversal_filter"),
    ("expectancy_repair", "volume|range_compression_expansion"),
    ("drawdown_repair", "continuation|pullback|high_volume"),
    ("drawdown_repair", "volume|dry_up_breakout"),
    ("no_trade_filter_injection", ""),
    ("symbol_pruning", ""),
    ("sector_pruning", ""),
    ("subfamily_split", "volume|dry_up_breakout"),
    ("dte_retune", ""),
    ("moneyness_retune", ""),
    ("exit_policy_retune", ""),
    ("risk_filter_retune", ""),
    ("relative_strength_retune", "continuation|pullback|relative_strength"),
    ("volatility_retune", ""),
    ("volume_retune", "volume|dry_up_breakout"),
    ("stop_target_retune", ""),
    ("profitable_slice_reinforcement", "continuation|pullback|high_volume"),
    ("loss_driver_suppression", "volume|climax_reversal_filter"),
    ("hold_window_retune", ""),
    ("stress_specific_repair", ""),
    ("recent_market_reinforcement", ""),
)


def _expansion_id(idx: int) -> str:
    return f"mut-exp-v5-{idx:04d}-{hashlib.sha1(str(idx).encode()).hexdigest()[:6]}"


def _expansion_record(idx: int, mutation_type: str, subfamily_id: str) -> dict[str, object]:
    rec = {
        "artifact_type": "research_mutation_expansion_record_v5",
        "mutation_id": _expansion_id(idx),
        "mutation_type": mutation_type,
        "source_type": "v5_expansion",
        "parent_family_id": subfamily_id,
        "parent_subfamily_id": subfamily_id,
        "parent_cohort_id": subfamily_id.split("|", 1)[0] if subfamily_id else "",
        "intended_fix": f"V5 expansion seed for {mutation_type}",
        "expected_evaluation_axis": mutation_type.replace("_", "_"),
        "candidate_generation_plan_count": 300,
        "applicable": True,
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def run_v5_mutation_expansion_loop() -> dict[str, object]:
    records = [_expansion_record(idx, mt, sf) for idx, (mt, sf) in enumerate(V5_EXPANSION_SEEDS)]
    write_jsonl_file(MUTATION_EXEC_V5_EXPANSION_PATH, records)
    type_counts: dict[str, int] = {}
    for r in records:
        type_counts[r["mutation_type"]] = type_counts.get(r["mutation_type"], 0) + 1
    return {
        "v5_expansion_mutation_count": len(records),
        "v5_expansion_mutation_type_counts": type_counts,
        "v5_expansion_path": str(MUTATION_EXEC_V5_EXPANSION_PATH),
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v5_mutation_expansion_loop(), indent=2, sort_keys=True, default=str))
