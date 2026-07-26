"""CLI runner for public signal research scoreboard V4."""
from __future__ import annotations

import json

from dopey_scoreboard.public_signal_research_scoreboard_v4 import run_public_signal_research_scoreboard_v4


def main() -> int:
    summary = run_public_signal_research_scoreboard_v4()
    print(
        json.dumps(
            {
                "scoreboard_status": summary["scoreboard_status"],
                "v4_top_profit_factor": summary.get("v4_top_profit_factor", 0.0),
                "summary_path": summary["artifact_paths"]["public_signal_research_scoreboard_v4"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
