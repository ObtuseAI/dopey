"""CLI runner for V4 research path simulator."""
from __future__ import annotations

import json

from dopey_signal_research.research_path_simulator_v4 import run_research_path_simulator_v4


def main() -> int:
    summary = run_research_path_simulator_v4()
    print(
        json.dumps(
            {
                "research_path_simulator_v4_status": summary["research_path_simulator_v4_status"],
                "simulated_trade_count": summary["simulated_trade_count"],
                "total_pnl": summary["total_pnl"],
                "summary_path": summary["artifact_paths"]["research_path_simulator_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
