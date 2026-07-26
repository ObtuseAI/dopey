"""CLI runner for public walk-forward tournament V3."""
from __future__ import annotations

import json

from .public_walk_forward_tournament_v3 import run_public_walk_forward_tournament_v3


def main() -> int:
    summary = run_public_walk_forward_tournament_v3()
    print(json.dumps({
        "public_walk_forward_status": summary["public_walk_forward_status"],
        "trade_count": summary["trade_count"],
        "strategy_count": summary["strategy_count"],
        "top_strategy": summary["top_strategy"],
        "summary_path": summary["artifact_paths"]["public_walk_forward_tournament_v3_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
