"""CLI runner for model-priced path simulator V4."""
from __future__ import annotations

import json

from .model_priced_path_simulator_v4 import run_model_priced_path_simulator_v4


def main() -> int:
    summary = run_model_priced_path_simulator_v4()
    print(json.dumps({
        "model_priced_path_simulator_status": summary["model_priced_path_simulator_status"],
        "simulated_trade_count": summary["simulated_trade_count"],
        "long_call_count": summary["long_call_count"],
        "long_put_count": summary["long_put_count"],
        "no_trade_count": summary["no_trade_count"],
        "total_pnl": summary["total_pnl"],
        "profit_factor": summary["profit_factor"],
        "max_drawdown": summary["max_drawdown"],
        "fixture_trade_count": summary["fixture_trade_count"],
        "short_option_count": summary["short_option_count"],
        "spread_structure_count": summary["spread_structure_count"],
        "public_data_only": summary["public_data_only"],
        "summary_path": summary["artifact_paths"]["model_priced_path_simulator_v4_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
