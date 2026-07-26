"""CLI runner for public champion hardening scoreboard V1."""
from __future__ import annotations

import json

from dopey_scoreboard.public_champion_hardening_scoreboard_v1 import run_public_champion_hardening_scoreboard_v1


def main() -> int:
    summary = run_public_champion_hardening_scoreboard_v1()
    print(json.dumps({
        "scoreboard_status": summary["scoreboard_status"],
        "hardened_champion_names": summary["hardened_champion_names"],
        "conditional_champion_names": summary["conditional_champion_names"],
        "demoted_champion_names": summary["demoted_champion_names"],
        "summary_path": summary["artifact_paths"]["public_champion_hardening_scoreboard_v1"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
