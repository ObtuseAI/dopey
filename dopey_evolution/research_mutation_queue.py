"""Build the next research mutation queue."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def build_research_mutation_queue(promotions: list[dict], eliminations: list[dict]) -> list[dict]:
    records: list[dict] = []
    for promotion in promotions:
        record = {
            "artifact_type": "research_mutation_queue",
            "strategy_family": promotion["strategy_family"],
            "mutation_intent": "compound_winner_with_slippage_stress",
            "priority": "high" if promotion["promotion_level"] == "paper_champion" else "medium",
            "source": "winner_promotion",
            "paper_only": True,
            "live_blocked": True,
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
    for elimination in eliminations:
        record = {
            "artifact_type": "research_mutation_queue",
            "strategy_family": elimination["strategy_family"],
            "mutation_intent": "kill_or_inverse_research_only",
            "priority": "low",
            "source": "loser_elimination",
            "paper_only": True,
            "live_blocked": True,
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
    return records

