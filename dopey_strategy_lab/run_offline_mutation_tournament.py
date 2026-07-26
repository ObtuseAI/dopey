"""CLI entrypoint for the deterministic offline mutation tournament."""
from __future__ import annotations

import json

from .evolution_tournament import run_offline_mutation_tournament


def main() -> int:
    result = run_offline_mutation_tournament()
    concise = {
        "tournament_status": result["tournament_status"],
        "parent_champion_strategy_id": result["parent_champion_strategy_id"],
        "best_mutated_strategy_id": result["best_mutated_strategy_id"],
        "parent_vs_mutation_comparison": result["parent_vs_mutation_comparison"],
        "promotion_decisions": result["promotion_decisions"],
        "mutation_registry_path": result["mutation_registry_path"],
        "proof_record_path": result["proof_record_path"],
        "safety_state": result["safety_state"],
        "reproducibility_hash": result["reproducibility_hash"],
    }
    print(json.dumps(concise, indent=2))
    return 0 if result["tournament_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
