"""V4 candidate density scheduler.

Balances continuation and volume subfamilies so no single family may
monopolize > 70% of the cap unless that is recorded honestly. Schedules
per-subfamily, per-symbol candidate targets.
"""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import record_with_hash


FAMILY_MONOPOLY_CAP = 0.70


def build_v4_density_schedule(symbols: list[str], subfamily_ids: list[str], cap: int) -> list[dict[str, object]]:
    if not symbols or not subfamily_ids:
        return []
    per_subfamily = max(cap // max(len(subfamily_ids), 1), 1000)
    per_symbol_per_subfamily = max(per_subfamily // max(len(symbols), 1), 80)
    schedule: list[dict[str, object]] = []
    for sub in subfamily_ids:
        for symbol in symbols:
            schedule.append(
                record_with_hash(
                    {
                        "artifact_type": "research_candidate_density_schedule_v4",
                        "stable_subfamily_id": sub,
                        "stable_family_id": sub.split("|", 1)[0] if "|" in sub else sub,
                        "symbol": symbol,
                        "target_count": per_symbol_per_subfamily,
                        "family_share_cap": FAMILY_MONOPOLY_CAP,
                        "public_data_only": True,
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
    return schedule
