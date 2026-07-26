"""CLI runner for model-priced path simulator V3."""
from __future__ import annotations

import json

from .model_priced_path_simulator_v3 import run_model_priced_path_simulator_v3


def main() -> int:
    summary = run_model_priced_path_simulator_v3()
    print(json.dumps({
        "model_priced_path_simulator_status": summary["model_priced_path_simulator_status"],
        "simulated_trade_count": summary["simulated_trade_count"],
        "total_pnl": summary["total_pnl"],
        "summary_path": summary["artifact_paths"]["model_priced_path_simulator_v3_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
