"""Generate the compact DOPEY mutation genealogy explorer artifact."""
from __future__ import annotations

import json
from pathlib import Path

from .mutation_genealogy import build_mutation_genealogy


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    result = build_mutation_genealogy(
        REPOSITORY_ROOT / "artifacts" / "dopey" / "mutations" / "mutation_registry.jsonl",
        REPOSITORY_ROOT / "artifacts" / "dopey" / "runs" / "latest_dossier.json",
        REPOSITORY_ROOT / "artifacts" / "dopey" / "evolution" / "mutation_genealogy.json",
    )
    print(json.dumps({
        "explorer_status": result["explorer_status"],
        "node_count": result["node_count"],
        "edge_count": result["edge_count"],
        "mutation_pareto_frontier_ids": result["mutation_pareto_frontier_ids"],
        "paper_only": result["paper_only"],
        "live_blocked": result["live_blocked"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
