"""CLI runner for retune tournament."""
from __future__ import annotations

import json

from dopey_tournament.conditional_champion_retune_tournament_v1 import run_conditional_champion_retune_tournament_v1


def main() -> int:
    summary = run_conditional_champion_retune_tournament_v1()
    print(json.dumps({
        "conditional_champion_retune_tournament_status": summary["conditional_champion_retune_tournament_status"],
        "retuned_trade_count": summary["retuned_trade_count"],
        "improved_candidate_count": summary["improved_candidate_count"],
        "summary_path": summary["artifact_paths"]["conditional_champion_retune_tournament_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
