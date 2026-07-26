"""CLI runner for public champion scoreboard V3."""
from __future__ import annotations

import json

from .public_champion_scoreboard_v3 import run_public_champion_scoreboard_v3


def main() -> int:
    summary = run_public_champion_scoreboard_v3()
    print(json.dumps({
        "scoreboard_status": summary["scoreboard_status"],
        "total_public_paper_pnl": summary["total_public_paper_pnl"],
        "trade_count": summary["trade_count"],
        "summary_path": summary["artifact_paths"]["public_champion_scoreboard_v3"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
