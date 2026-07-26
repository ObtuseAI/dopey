"""CLI runner for public signal deepening scoreboard V4."""
from __future__ import annotations

import json

from .public_signal_deepening_scoreboard_v4 import run_public_signal_deepening_scoreboard_v4


def main() -> int:
    summary = run_public_signal_deepening_scoreboard_v4()
    print(json.dumps({
        "scoreboard_status": summary["scoreboard_status"],
        "total_public_paper_pnl": summary["total_public_paper_pnl"],
        "trade_count": summary["trade_count"],
        "active_champions": summary["active_champions"],
        "near_champion_count": summary["near_champion_count"],
        "killed_cohort_count": summary["killed_cohort_count"],
        "next_mutation_queue_count": summary["next_mutation_queue_count"],
        "public_data_only": summary["public_data_only"],
        "fixture_trade_count": summary["fixture_trade_count"],
        "scoreboard_path": summary["artifact_paths"]["public_signal_deepening_scoreboard_v4"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
