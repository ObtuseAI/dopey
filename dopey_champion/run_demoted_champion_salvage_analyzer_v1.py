"""CLI runner for demoted salvage analyzer."""
from __future__ import annotations

import json

from dopey_champion.demoted_champion_salvage_analyzer_v1 import run_demoted_champion_salvage_analyzer_v1


def main() -> int:
    summary = run_demoted_champion_salvage_analyzer_v1()
    print(json.dumps({
        "demoted_champion_salvage_status": summary["demoted_champion_salvage_status"],
        "salvage_candidate_count": summary["salvage_candidate_count"],
        "kill_confirmed_count": summary["kill_confirmed_count"],
        "summary_path": summary["artifact_paths"]["demoted_champion_salvage_analyzer_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
