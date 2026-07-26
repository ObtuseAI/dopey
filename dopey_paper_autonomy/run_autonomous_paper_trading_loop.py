"""CLI runner for autonomous paper-only trading loop."""
from __future__ import annotations

import json

from .autonomous_paper_trading_loop import run_autonomous_paper_trading_loop


def main() -> int:
    result = run_autonomous_paper_trading_loop()
    print(json.dumps({
        "paper_loop_status": result["paper_loop_status"],
        "paper_intent_count": result["paper_intent_count"],
        "paper_position_count": result["paper_position_count"],
        "summary_path": result["artifact_paths"]["autonomous_paper_trading_loop_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

