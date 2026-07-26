"""CLI for V5 mutation queue."""
from __future__ import annotations

import json

from dopey_signal_research.research_mutation_queue_v5 import run_research_mutation_queue_v5


def main() -> int:
    summary = run_research_mutation_queue_v5()
    print(
        json.dumps(
            {
                "research_mutation_queue_v5_status": summary["research_mutation_queue_v5_status"],
                "source_breakthrough_count": summary["source_breakthrough_count"],
                "source_watchlist_count": summary["source_watchlist_count"],
                "source_near_breakthrough_count": summary["source_near_breakthrough_count"],
                "mutation_queue_count": summary["mutation_queue_count"],
                "mutation_type_counts": summary["mutation_type_counts"],
                "no_mutations_reason": summary["no_mutations_reason"],
                "v5_min_breakthrough_pf": 1.10,
                "thresholds_lowered": False,
                "public_data_only": True,
                "live_trading_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
