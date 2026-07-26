"""CLI runners for repair preflight and artifact guard."""
from __future__ import annotations

import json

from dopey_validation.public_champion_artifact_guard_v1 import run_public_champion_artifact_guard_v1
from dopey_validation.public_champion_repair_preflight_v1 import run_public_champion_repair_preflight_v1


def main() -> int:
    summary = run_public_champion_repair_preflight_v1()
    print(json.dumps({
        "public_champion_repair_preflight_status": summary["public_champion_repair_preflight_status"],
        "conditional_champion_count": summary["conditional_champion_count"],
        "demoted_champion_count": summary["demoted_champion_count"],
        "summary_path": summary["artifact_paths"]["public_champion_repair_preflight_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
