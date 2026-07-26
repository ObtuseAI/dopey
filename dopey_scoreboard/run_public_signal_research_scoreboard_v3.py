"""CLI runner for public signal research scoreboard V3."""
from __future__ import annotations

import json

from dopey_scoreboard.public_signal_research_scoreboard_v3 import run_public_signal_research_scoreboard_v3


def main() -> int:
    summary = run_public_signal_research_scoreboard_v3()
    print(
        json.dumps(
            {
                "scoreboard_status": summary["scoreboard_status"],
                "v3_top_profit_factor": summary.get("v3_top_profit_factor", 0.0),
                "summary_path": summary["artifact_paths"]["public_signal_research_scoreboard_v3"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
