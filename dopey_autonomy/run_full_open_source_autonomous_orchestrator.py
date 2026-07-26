"""CLI runner for full open-source autonomous orchestrator."""
from __future__ import annotations

import json

from .full_open_source_autonomous_orchestrator import run_full_open_source_autonomous_orchestrator


def main() -> int:
    result = run_full_open_source_autonomous_orchestrator()
    print(json.dumps({
        "autonomy_status": result["autonomy_status"],
        "valid_real_dataset": result["valid_real_dataset"],
        "options_data_status": result["options_data_status"],
        "paper_trading_loop_status": result["paper_trading_loop_status"],
        "summary_path": result["artifact_paths"]["full_open_source_autonomous_orchestrator_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

