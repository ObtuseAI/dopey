"""CLI for V5 mutation queue executor + V5 expansion loop."""
from __future__ import annotations

import json

from dopey_signal_research.research_mutation_expansion_loop_v5 import run_v5_mutation_expansion_loop
from dopey_signal_research.research_mutation_queue_executor_v5 import execute_v5_mutation_queue


def main() -> int:
    exec_summary = execute_v5_mutation_queue()
    exp_summary = run_v5_mutation_expansion_loop()
    print(
        json.dumps(
            {
                "research_mutation_queue_executor_v5_status": exec_summary["research_mutation_queue_executor_v5_status"],
                "input_v4_mutation_count": exec_summary["input_v4_mutation_count"],
                "executed_mutation_count": exec_summary["executed_mutation_count"],
                "expanded_mutation_count": exec_summary["expanded_mutation_count"],
                "failed_mutation_count": exec_summary["failed_mutation_count"],
                "mutation_type_counts": exec_summary["mutation_type_counts"],
                "v5_expansion_mutation_count": exp_summary["v5_expansion_mutation_count"],
                "v5_min_breakthrough_pf": 1.10,
                "thresholds_lowered": False,
                "live_trading_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
