"""Candidate density scheduler V3 — balanced family allocation."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v3_common import STABLE_FAMILY_CONTINUATION, STABLE_FAMILY_VOLUME
from dopey_autonomy.public_champion_common import record_with_hash


def build_v3_density_schedule(symbols: list[str], cap: int) -> list[dict[str, object]]:
    per_symbol = max(cap // max(len(symbols), 1), 200)
    family_cap = cap // 2
    schedule: list[dict[str, object]] = []
    for family_id, family_cap_n in (
        (STABLE_FAMILY_CONTINUATION, family_cap),
        (STABLE_FAMILY_VOLUME, cap - family_cap),
    ):
        per_family_symbol = max(family_cap_n // max(len(symbols), 1), 100)
        for symbol in symbols:
            schedule.append(
                record_with_hash(
                    {
                        "artifact_type": "research_candidate_density_schedule_v3",
                        "stable_family_template_id": family_id,
                        "symbol": symbol,
                        "target_count": min(per_family_symbol, per_symbol),
                        "family_share_cap": 0.70,
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
    return schedule
