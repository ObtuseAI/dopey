"""CLI runner for zero_dte replay outcomes artifact repair."""
from __future__ import annotations

import json

from dopey_active_policy.zero_dte_replay_outcomes_artifact_repair_v1 import run_zero_dte_replay_outcomes_artifact_repair_v1


def main() -> int:
    summary = run_zero_dte_replay_outcomes_artifact_repair_v1()
    print(
        json.dumps(
            {
                "zero_dte_replay_outcomes_repair_status": summary["zero_dte_replay_outcomes_repair_status"],
                "empty_artifact_detected": summary.get("empty_artifact_detected", False),
                "summary_path": summary["artifact_paths"]["zero_dte_replay_outcomes_artifact_repair_v1_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
