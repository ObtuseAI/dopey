"""CLI runner for failed champion family quarantine V1."""
from __future__ import annotations

import json

from .failed_champion_family_quarantine_v1 import run_failed_champion_family_quarantine_v1


def main() -> int:
    summary = run_failed_champion_family_quarantine_v1()
    print(json.dumps({
        "failed_family_quarantine_status": summary["failed_family_quarantine_status"],
        "quarantined_family_count": summary["quarantined_family_count"],
        "negative_control_count": summary["negative_control_count"],
        "summary_path": summary["artifact_paths"]["failed_champion_family_quarantine_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
