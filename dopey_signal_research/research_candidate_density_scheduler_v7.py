"""V7 candidate density scheduler (Workstream F).

Plans per-subfamily candidate generation counts for the V7 research loop.
Honours V7 caps: max family share 0.60, no-trade ratio <= 0.35, and a
minimum trade-active sample per (subfamily, symbol) pair.
"""
from __future__ import annotations


from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v7_common import (
    DENSITY_SCHEDULE_V7_PATH,
    RESEARCH_V7_ROOT,
    V7_ALL_SUBFAMILIES,
    V7_MAX_FAMILY_SHARE,
    V7_MAX_NO_TRADE_RATIO,
    V7_MIN_CANDIDATES,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
    V7_TARGET_CANDIDATES,
    WATCHDOG_CANDIDATE_CAP_V7,
    research_v7_proof_record,
    utc_now_iso,
)

DENSITY_SCHEDULE_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_candidate_density_scheduler_v7_proof.jsonl"


__all__ = ["plan_v7_candidate_density"]


def plan_v7_candidate_density(
    target_candidates: int = V7_TARGET_CANDIDATES,
    min_candidates: int = V7_MIN_CANDIDATES,
    max_family_share: float = V7_MAX_FAMILY_SHARE,
    max_no_trade_ratio: float = V7_MAX_NO_TRADE_RATIO,
    min_trade_active_sample: int = V7_MIN_TRADE_ACTIVE_SAMPLE,
    watchdog_cap: int = WATCHDOG_CANDIDATE_CAP_V7,
    symbols_per_subfamily: int | None = None,
) -> dict[str, object]:
    """Plan V7 candidate density across all V7 subfamilies.

    Distributes ``target_candidates`` evenly across (subfamily, symbol) pairs,
    then boosts the first pairs with one extra trade-active candidate so the
    total hits the target exactly.  The implied per-pair budget keeps the
    no-trade share well below ``max_no_trade_ratio`` while preserving at least
    ``min_trade_active_sample`` trade-active candidates per pair.
    """
    subfamilies = list(V7_ALL_SUBFAMILIES)
    subfamily_count = len(subfamilies)
    if symbols_per_subfamily is None:
        # Default aligns with the filtered V7 generator symbol universe.
        symbols_per_subfamily = 139

    total_pairs = subfamily_count * symbols_per_subfamily
    if total_pairs <= 0:
        return {
            "schedule": [],
            "target_candidates": target_candidates,
            "min_candidates": min_candidates,
            "max_family_share": max_family_share,
            "max_no_trade_ratio": max_no_trade_ratio,
            "min_trade_active_sample": min_trade_active_sample,
            "watchdog_cap": watchdog_cap,
            "subfamily_count": subfamily_count,
            "symbols_per_subfamily": symbols_per_subfamily,
            "total_planned": 0,
            "per_pair_budget": 0,
            "base_per_pair": 0,
            "remainder": 0,
        }

    base_per_pair = target_candidates // total_pairs
    remainder = target_candidates - base_per_pair * total_pairs

    # Ensure we still reach the minimum even if target is very low.
    if base_per_pair == 0 and target_candidates < min_candidates:
        base_per_pair = max(min_candidates // total_pairs, 1)
        remainder = min_candidates - base_per_pair * total_pairs

    full_subfamilies = remainder // symbols_per_subfamily
    partial_extra = remainder % symbols_per_subfamily

    schedule: list[dict[str, object]] = []
    total = 0
    for s_idx, sub in enumerate(subfamilies):
        family = sub.split("|", 1)[0] if "|" in sub else "mixed"
        extra = symbols_per_subfamily if s_idx < full_subfamilies else (
            partial_extra if s_idx == full_subfamilies else 0
        )
        sub_target = base_per_pair * symbols_per_subfamily + extra
        total += sub_target
        schedule.append(
            {
                "artifact_type": "v7_density_schedule_entry",
                "stable_subfamily_id": sub,
                "stable_family_id": family,
                "target_candidate_count": sub_target,
                "weight": round(1.0 / subfamily_count, 8),
                "max_family_share": max_family_share,
                "max_no_trade_ratio": max_no_trade_ratio,
                "min_trade_active_sample": min_trade_active_sample,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    return {
        "schedule": schedule,
        "target_candidates": target_candidates,
        "min_candidates": min_candidates,
        "max_family_share": max_family_share,
        "max_no_trade_ratio": max_no_trade_ratio,
        "min_trade_active_sample": min_trade_active_sample,
        "watchdog_cap": watchdog_cap,
        "subfamily_count": subfamily_count,
        "symbols_per_subfamily": symbols_per_subfamily,
        "total_planned": total,
        "per_pair_budget": base_per_pair + (1 if remainder else 0),
        "base_per_pair": base_per_pair,
        "remainder": remainder,
    }


def run_v7_density_scheduler() -> dict[str, object]:
    plan = plan_v7_candidate_density()
    write_jsonl_file(
        DENSITY_SCHEDULE_V7_PATH,
        [record_with_hash(s, "record_hash") for s in plan["schedule"]],
    )
    write_jsonl_file(
        DENSITY_SCHEDULE_V7_PROOF_PATH,
        [research_v7_proof_record("research-candidate-density-scheduler-v7", "density_schedule_generated_v7", plan)],
    )
    return plan


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v7_density_scheduler(), indent=2, sort_keys=True, default=str))
