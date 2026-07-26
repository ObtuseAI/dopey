"""CLI runner for retune path simulator."""
from __future__ import annotations

import json

from dopey_options_engine.conditional_champion_retune_path_simulator_v1 import run_conditional_champion_retune_path_simulator_v1


def main() -> int:
    summary = run_conditional_champion_retune_path_simulator_v1()
    print(json.dumps({
        "conditional_champion_retune_path_status": summary["conditional_champion_retune_path_status"],
        "simulated_trade_count": summary["simulated_trade_count"],
        "summary_path": summary["artifact_paths"]["conditional_champion_retune_path_simulator_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
