"""V5 candidate density scheduler.

Plans the per-subfamily / per-mutation candidate generation counts.
Family share cap is 70% (any single family cannot exceed 70% of total).
Target = 40,000 candidates, min = 20,000, watchdog cap = 50,000.
"""
from __future__ import annotations


from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    DENSITY_SCHEDULE_V5_PATH,
    V5_CONTINUATION_SUBFAMILIES,
    V5_MAX_FAMILY_SHARE,
    V5_MIN_CANDIDATES,
    V5_TARGET_CANDIDATES,
    V5_VOLUME_SUBFAMILIES,
    WATCHDOG_CANDIDATE_CAP_V5,
    utc_now_iso,
)


__all__ = ["plan_v5_candidate_density"]


def plan_v5_candidate_density(
    target_candidates: int = V5_TARGET_CANDIDATES,
    min_candidates: int = V5_MIN_CANDIDATES,
    max_family_share: float = V5_MAX_FAMILY_SHARE,
    watchdog_cap: int = WATCHDOG_CANDIDATE_CAP_V5,
) -> dict[str, object]:
    """Plan V5 candidate density across the 8 V5 subfamilies."""
    subfamily_count = len(V5_CONTINUATION_SUBFAMILIES) + len(V5_VOLUME_SUBFAMILIES)
    per_subfamily_base = max(target_candidates // subfamily_count, 1)
    schedule: list[dict[str, object]] = []
    total = 0
    for sub in V5_CONTINUATION_SUBFAMILIES:
        c = per_subfamily_base
        total += c
        schedule.append(
            {
                "artifact_type": "v5_density_schedule_entry",
                "stable_subfamily_id": sub,
                "stable_family_id": "continuation",
                "target_candidate_count": c,
                "weight": 1.0 / subfamily_count,
                "max_family_share": max_family_share,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    for sub in V5_VOLUME_SUBFAMILIES:
        c = per_subfamily_base
        total += c
        schedule.append(
            {
                "artifact_type": "v5_density_schedule_entry",
                "stable_subfamily_id": sub,
                "stable_family_id": "volume",
                "target_candidate_count": c,
                "weight": 1.0 / subfamily_count,
                "max_family_share": max_family_share,
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
        "watchdog_cap": watchdog_cap,
        "subfamily_count": subfamily_count,
        "total_planned": total,
    }


def run_v5_density_scheduler() -> dict[str, object]:
    plan = plan_v5_candidate_density()
    write_jsonl_file(DENSITY_SCHEDULE_V5_PATH, [record_with_hash(s, "record_hash") for s in plan["schedule"]])
    return plan


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v5_density_scheduler(), indent=2, sort_keys=True, default=str))
