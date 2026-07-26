"""Near-champion repair loop V2.

Consumes sample-repair and walk-forward-repair plans from the champion gate V2
and generates focused next-candidate mutation instructions.
"""
from __future__ import annotations

from dopey_autonomy.public_champion_common import record_with_hash, safe_float

from dopey_signal_engine.near_champion_signal_expander_v4 import (
    EXIT_ALTERNATES,
    INVALIDATION_FACTORS,
    MONEYNESS_ADJACENCY,
    parse_seed,
)


def build_near_champion_repair_queue_v2(repair_plans: list[dict[str, object]]) -> list[dict[str, object]]:
    queue: list[dict[str, object]] = []
    for plan in repair_plans:
        label = str(plan.get("near_champion_label", ""))
        cohort_id = str(plan.get("cohort_id", ""))
        setup_family = cohort_id.split("|")[0] if "|" in cohort_id else cohort_id
        if label.startswith("sample_count"):
            queue.extend(_sample_repair_mutations(plan, setup_family))
        elif label.startswith("walk_forward"):
            queue.extend(_split_repair_mutations(plan, setup_family))
    return queue


def _sample_repair_mutations(plan: dict[str, object], setup_family: str) -> list[dict[str, object]]:
    mutations: list[dict[str, object]] = []
    axes = ["more_dates", "sector_peers", "adjacent_dte", "adjacent_moneyness", "tighter_invalidation", "wider_invalidation"]
    for index, axis in enumerate(axes):
        mutations.append(record_with_hash({
            "artifact_type": "near_champion_repair_queue_v2",
            "repair_type": "sample_count_insufficient",
            "cohort_level": plan.get("cohort_level", ""),
            "cohort_id": plan.get("cohort_id", ""),
            "setup_family": setup_family,
            "repair_axis": axis,
            "target_sample_count": plan.get("target_sample_count", 30),
            "current_sample_count": plan.get("current_sample_count", 0),
            "estimated_new_candidates_needed": plan.get("estimated_new_candidates_needed", 30),
            "priority": "high",
            "fixture_allowed": False,
            "live_trading_enabled": False,
        }, "record_hash"))
    return mutations


def _split_repair_mutations(plan: dict[str, object], setup_family: str) -> list[dict[str, object]]:
    mutations: list[dict[str, object]] = []
    for inv_factor in INVALIDATION_FACTORS:
        for exit_policy in EXIT_ALTERNATES[:3]:
            mutations.append(record_with_hash({
                "artifact_type": "near_champion_repair_queue_v2",
                "repair_type": "walk_forward_fragile",
                "cohort_level": plan.get("cohort_level", ""),
                "cohort_id": plan.get("cohort_id", ""),
                "setup_family": setup_family,
                "repair_axis": "widen_invalidation_alternate_exits",
                "invalidation_factor": round(inv_factor, 4),
                "exit_policy": exit_policy,
                "target_split_pass_rate": plan.get("target_split_pass_rate", 0.60),
                "current_split_pass_rate": plan.get("current_split_pass_rate", 0.0),
                "priority": "medium",
                "fixture_allowed": False,
                "live_trading_enabled": False,
            }, "record_hash"))
    return mutations


def near_champion_repair_seed_count(repair_plans: list[dict[str, object]]) -> dict[str, object]:
    sample_count = sum(1 for p in repair_plans if str(p.get("near_champion_label", "")).startswith("sample_count"))
    split_count = sum(1 for p in repair_plans if str(p.get("near_champion_label", "")).startswith("walk_forward"))
    return {"sample_repair_seed_count": sample_count, "split_repair_seed_count": split_count}
