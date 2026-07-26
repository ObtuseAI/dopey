"""CLI runner for research path simulator V3."""
from __future__ import annotations

import json

from dopey_signal_research.research_path_simulator_v3 import run_research_path_simulator_v3


def main() -> int:
    summary = run_research_path_simulator_v3()
    print(
        json.dumps(
            {
                "research_path_simulator_v3_status": summary["research_path_simulator_v3_status"],
                "simulated_trade_count": summary["simulated_trade_count"],
                "summary_path": summary["artifact_paths"]["research_path_simulator_v3_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
