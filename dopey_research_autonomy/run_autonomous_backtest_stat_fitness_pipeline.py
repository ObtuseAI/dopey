"""CLI runner for autonomous backtest/stat/fitness pipeline."""
from __future__ import annotations

import json

from .autonomous_backtest_stat_fitness_pipeline import run_autonomous_backtest_stat_fitness_pipeline


def main() -> int:
    result = run_autonomous_backtest_stat_fitness_pipeline()
    print(json.dumps({
        "pipeline_status": result["pipeline_status"],
        "data_tier": result["data_tier"],
        "research_promotion_status": result["research_promotion_status"],
        "summary_path": result["artifact_paths"]["autonomous_backtest_stat_fitness_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

