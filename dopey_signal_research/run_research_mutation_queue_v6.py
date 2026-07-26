"""CLI for V6 research mutation queue."""
from __future__ import annotations

import json

from dopey_signal_research.research_mutation_queue_v6 import run_research_mutation_queue_v6


def main() -> int:
    summary = run_research_mutation_queue_v6()
    print(
        json.dumps(
            {
                "research_mutation_queue_v6_status": summary["research_mutation_queue_v6_status"],
                "source_breakthrough_count": summary["source_breakthrough_count"],
                "source_watchlist_count": summary["source_watchlist_count"],
                "source_near_breakthrough_count": summary["source_near_breakthrough_count"],
                "mutation_queue_count": summary["mutation_queue_count"],
                "mutation_type_counts": summary["mutation_type_counts"],
                "no_mutations_reason": summary["no_mutations_reason"],
                "v6_min_breakthrough_pf": summary["v6_min_breakthrough_pf"],
                "thresholds_lowered": summary["thresholds_lowered"],
                "public_data_only": summary["public_data_only"],
                "live_trading_enabled": summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
