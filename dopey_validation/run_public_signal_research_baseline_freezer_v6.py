"""CLI for V5 baseline freezer (V6 snapshot)."""
from __future__ import annotations

import json

from dopey_validation.public_signal_research_baseline_freezer_v6 import run_public_signal_research_baseline_freezer_v6


def main() -> int:
    summary = run_public_signal_research_baseline_freezer_v6()
    print(
        json.dumps(
            {
                "baseline_freeze_status": summary["baseline_freeze_status"],
                "copied_count": summary["copied_count"],
                "skipped_count": summary["skipped_count"],
                "total_bytes": summary["total_bytes"],
                "baseline_root": summary["baseline_root"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
