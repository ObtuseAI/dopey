"""Research candidate density scheduler V2."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import sector_for_symbol


def build_v2_density_schedule(symbols: list[str], seeds: list[dict[str, object]], cap: int) -> list[dict[str, object]]:
    sectors = Counter(sector_for_symbol(symbol) for symbol in symbols)
    per_symbol = max(cap // max(len(symbols), 1), 100)
    per_seed = max(cap // max(len(seeds), 1), 5000)
    schedule: list[dict[str, object]] = []
    for symbol in symbols:
        schedule.append({"artifact_type": "research_candidate_density_schedule_v2", "scope": "symbol", "scope_id": symbol, "target_count": per_symbol})
    for sector in sectors:
        schedule.append({"artifact_type": "research_candidate_density_schedule_v2", "scope": "sector", "scope_id": sector, "target_count": max(cap // max(len(sectors), 1), 300)})
    for seed in seeds:
        schedule.append({"artifact_type": "research_candidate_density_schedule_v2", "scope": "watchlist_seed", "scope_id": seed.get("watchlist_seed_id", ""), "target_count": per_seed})
    return schedule
