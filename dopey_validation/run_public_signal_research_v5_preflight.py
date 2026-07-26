"""CLI for V5 preflight."""
from __future__ import annotations

import json

from dopey_validation.public_signal_research_v5_preflight import run_public_signal_research_v5_preflight


def main() -> int:
    summary = run_public_signal_research_v5_preflight()
    print(
        json.dumps(
            {
                "public_signal_research_v5_preflight_status": summary["public_signal_research_v5_preflight_status"],
                "check_count": summary["check_count"],
                "passed_count": summary["passed_count"],
                "failed_count": summary["failed_count"],
                "v4_summary_status": summary["v4_summary_status"],
                "min_breakthrough_pf": summary["min_breakthrough_pf"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
