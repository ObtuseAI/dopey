"""CLI runner for artifact guard V1."""
from __future__ import annotations

import json

from dopey_validation.public_champion_artifact_guard_v1 import run_public_champion_artifact_guard_v1


def main() -> int:
    summary = run_public_champion_artifact_guard_v1()
    print(json.dumps({
        "artifact_guard_status": summary["artifact_guard_status"],
        "shrinkage_detected": summary["shrinkage_detected"],
        "restored_artifact_count": summary["restored_artifact_count"],
        "summary_path": summary["artifact_paths"]["public_champion_artifact_guard_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
