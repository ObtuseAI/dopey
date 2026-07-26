"""CLI runner for public signal deepening loop V2."""
from __future__ import annotations

import json

from .public_signal_deepening_loop_v2 import run_public_signal_deepening_loop_v2


def main() -> int:
    summary = run_public_signal_deepening_loop_v2()
    print(json.dumps({
        "public_signal_deepening_status": summary["public_signal_deepening_status"],
        "generation_count": summary["generation_count"],
        "champion_found": summary["champion_found"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "near_champion_count": summary["near_champion_count"],
        "mutations_generated": summary["mutations_generated"],
        "repair_queue_count": summary["repair_queue_count"],
        "kill_queue_count": summary["kill_queue_count"],
        "killed_cohort_summary": summary["killed_cohort_summary"],
        "summary_path": summary["artifact_paths"]["public_signal_deepening_loop_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
