"""CLI runner for watchlist mutation planner V2."""
from __future__ import annotations

import json

from .watchlist_mutation_planner_v2 import run_watchlist_mutation_planner_v2


def main() -> int:
    summary = run_watchlist_mutation_planner_v2()
    print(json.dumps({
        "watchlist_mutation_status": summary["watchlist_mutation_status"],
        "mutation_queue_count": summary["mutation_queue_count"],
        "summary_path": summary["artifact_paths"]["watchlist_mutation_planner_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
