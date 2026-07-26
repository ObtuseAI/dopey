"""CLI for V6 mutation queue executor + expansion loop."""
from __future__ import annotations

import json

from dopey_signal_research.research_mutation_queue_executor_v6 import execute_v6_mutation_queue


def main() -> int:
    exec_summary = execute_v6_mutation_queue()
    print(
        json.dumps(
            {
                "research_mutation_queue_executor_v6_status": exec_summary["research_mutation_queue_executor_v6_status"],
                "input_v5_mutation_count": exec_summary["input_v5_mutation_count"],
                "executed_mutation_count": exec_summary["executed_mutation_count"],
                "expanded_mutation_count": exec_summary["expanded_mutation_count"],
                "failed_mutation_count": exec_summary["failed_mutation_count"],
                "mutation_type_counts": exec_summary["mutation_type_counts"],
                "v6_min_breakthrough_pf": exec_summary["v6_min_breakthrough_pf"],
                "thresholds_lowered": exec_summary["thresholds_lowered"],
                "live_trading_enabled": exec_summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
