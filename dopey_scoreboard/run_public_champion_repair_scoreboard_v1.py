"""CLI runner for repair scoreboard."""
from __future__ import annotations

import json

from dopey_scoreboard.public_champion_repair_scoreboard_v1 import run_public_champion_repair_scoreboard_v1


def main() -> int:
    summary = run_public_champion_repair_scoreboard_v1()
    print(json.dumps({
        "scoreboard_status": summary["scoreboard_status"],
        "retuned_hardened_names": summary["retuned_hardened_names"],
        "summary_path": summary["artifact_paths"]["public_champion_repair_scoreboard_v1"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
