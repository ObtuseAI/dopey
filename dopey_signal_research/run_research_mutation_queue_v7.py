"""CLI entry point for V7 research mutation queue."""
from __future__ import annotations

import json

from dopey_signal_research.research_mutation_queue_v7 import run_research_mutation_queue_v7


def main() -> int:
    summary = run_research_mutation_queue_v7()
    print(
        json.dumps(
            {
                "research_mutation_queue_v7_status": summary["research_mutation_queue_v7_status"],
                "source_breakthrough_count": summary["source_breakthrough_count"],
                "source_watchlist_count": summary["source_watchlist_count"],
                "source_near_breakthrough_count": summary["source_near_breakthrough_count"],
                "mutation_queue_count": summary["mutation_queue_count"],
                "v7_min_breakthrough_pf": summary["v7_min_breakthrough_pf"],
                "v7_max_no_trade_ratio": summary["v7_max_no_trade_ratio"],
                "thresholds_lowered": summary["thresholds_lowered"],
                "public_data_only": summary["public_data_only"],
                "live_trading_enabled": summary["live_trading_enabled"],
                "blocks_no_trade_only_breakthrough": summary["blocks_no_trade_only_breakthrough"],
                "no_trade_only_breakthroughs_blocked": summary["no_trade_only_breakthroughs_blocked"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
