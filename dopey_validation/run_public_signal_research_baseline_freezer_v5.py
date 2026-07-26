"""CLI for V4 baseline freezer."""
from __future__ import annotations

import json

from dopey_validation.public_signal_research_baseline_freezer_v5 import run_public_signal_research_baseline_freezer_v5


def main() -> int:
    summary = run_public_signal_research_baseline_freezer_v5()
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
