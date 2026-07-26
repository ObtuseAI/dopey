"""CLI runner for stable family template repair V3."""
from __future__ import annotations

import json

from dopey_signal_research.stable_family_template_repair_v3 import run_stable_family_template_repair_v3


def main() -> int:
    summary = run_stable_family_template_repair_v3()
    print(
        json.dumps(
            {
                "stable_family_template_repair_status": summary["stable_family_template_repair_status"],
                "template_count": summary["template_count"],
                "summary_path": summary["artifact_paths"]["stable_family_template_repair_v3_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
