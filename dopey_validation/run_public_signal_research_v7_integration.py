"""CLI entry point for V7 integration touch points validator."""
from __future__ import annotations

import json
import sys

from dopey_validation.public_signal_research_v7_integration import run_v7_integration_touch_points


def main() -> int:
    result = run_v7_integration_touch_points()
    print(
        json.dumps(
            {
                "integration_status": result["integration_status"],
                "check_count": result["check_count"],
                "passed_count": result["passed_count"],
                "failed_count": result["failed_count"],
                "failed_checks": result["failed_checks"],
                "summary_path": str(result.get("summary_path", "")),
                "proof_path": str(result.get("proof_path", "")),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["integration_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
