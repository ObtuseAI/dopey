"""CLI runner for research path simulator V2."""
from __future__ import annotations

import json

from .research_path_simulator_v2 import run_research_path_simulator_v2


def main() -> int:
    summary = run_research_path_simulator_v2()
    print(json.dumps({
        "research_path_simulator_v2_status": summary["research_path_simulator_v2_status"],
        "simulated_trade_count": summary["simulated_trade_count"],
        "summary_path": summary["artifact_paths"]["research_path_simulator_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
