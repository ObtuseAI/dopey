"""CLI runner for open options data autonomy plan."""
from __future__ import annotations

import json

from .open_options_data_autonomy_plan import run_open_options_data_autonomy_plan


def main() -> int:
    result = run_open_options_data_autonomy_plan()
    print(json.dumps({
        "options_data_status": result["options_data_status"],
        "quote_priced_backtest_allowed": result["quote_priced_backtest_allowed"],
        "model_priced_research_allowed": result["model_priced_research_allowed"],
        "summary_path": result["artifact_paths"]["open_options_data_autonomy_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

