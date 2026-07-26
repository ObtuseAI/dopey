"""CLI runner for conditional champion signal retune."""
from __future__ import annotations

import json

from dopey_signal_engine.conditional_champion_signal_retune_v1 import run_conditional_champion_signal_retune_v1


def main() -> int:
    summary = run_conditional_champion_signal_retune_v1()
    print(json.dumps({
        "conditional_champion_signal_retune_status": summary["conditional_champion_signal_retune_status"],
        "retune_candidate_count": summary["retune_candidate_count"],
        "summary_path": summary["artifact_paths"]["conditional_champion_signal_retune_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
