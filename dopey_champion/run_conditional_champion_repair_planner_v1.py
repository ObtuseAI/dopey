"""CLI runner for conditional champion repair planner."""
from __future__ import annotations

import json

from dopey_champion.conditional_champion_repair_planner_v1 import run_conditional_champion_repair_planner_v1


def main() -> int:
    summary = run_conditional_champion_repair_planner_v1()
    print(json.dumps({
        "conditional_champion_repair_planner_status": summary["conditional_champion_repair_planner_status"],
        "repair_plan_count": summary["repair_plan_count"],
        "summary_path": summary["artifact_paths"]["conditional_champion_repair_planner_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
