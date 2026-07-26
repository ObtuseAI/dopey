"""Research candidate density scheduler V1."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import sector_for_symbol


def build_density_schedule(symbols: list[str], family_count: int, candidate_cap: int) -> list[dict[str, object]]:
    sectors = Counter(sector_for_symbol(symbol) for symbol in symbols)
    per_symbol = max(candidate_cap // max(len(symbols), 1), 50)
    per_family = max(candidate_cap // max(family_count, 1), 100)
    schedule: list[dict[str, object]] = []
    for symbol in symbols:
        schedule.append({
            "artifact_type": "research_candidate_density_schedule_v1",
            "scope": "symbol",
            "scope_id": symbol,
            "target_count": per_symbol,
        })
    for sector, _count in sectors.items():
        schedule.append({
            "artifact_type": "research_candidate_density_schedule_v1",
            "scope": "sector",
            "scope_id": sector,
            "target_count": max(candidate_cap // max(len(sectors), 1), 200),
        })
    schedule.append({
        "artifact_type": "research_candidate_density_schedule_v1",
        "scope": "family",
        "scope_id": "all",
        "target_count": per_family,
    })
    return schedule
