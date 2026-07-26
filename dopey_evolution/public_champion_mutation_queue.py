"""Mutation queue builder for public champion evolution."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import record_with_hash, safe_float


def build_public_champion_mutation_queue(
    leaderboard: list[dict[str, object]],
    gate_results: list[dict[str, object]],
    generation: int,
) -> list[dict[str, object]]:
    watchlist = {str(record.get("strategy_id", "")) for record in gate_results if str(record.get("promotion_level", "")) in {"public_watchlist", "public_paper_champion"}}
    seeds = [row for row in leaderboard[:8] if safe_float(row.get("net_pnl")) > 0.0 or str(row.get("strategy_id", "")) in watchlist]
    mutations: list[dict[str, object]] = []
    for seed_index, row in enumerate(seeds):
        for variant_index, mutation_type in enumerate(["tighten_invalidation", "extend_hold_window", "raise_confidence_threshold"]):
            record = {
                "artifact_type": "public_champion_mutation_queue",
                "generation": generation,
                "mutation_id": f"public-mut-gen{generation}-{seed_index + 1}-{variant_index + 1}",
                "parent_strategy_id": row.get("strategy_id", ""),
                "setup_family": row.get("setup_family", ""),
                "mutation_type": mutation_type,
                "priority": "high" if row.get("strategy_id", "") in watchlist else "medium",
                "parent_net_pnl": row.get("net_pnl", 0.0),
                "parent_profit_factor": row.get("profit_factor", 0.0),
                "fixture_allowed": False,
                "live_trading_enabled": False,
            }
            mutations.append(record_with_hash(record, "record_hash"))
    return mutations

