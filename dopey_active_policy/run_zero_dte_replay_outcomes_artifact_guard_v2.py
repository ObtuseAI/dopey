"""CLI runner for zero_dte_replay_outcomes artifact guard V2."""
from __future__ import annotations

import json

from dopey_active_policy.zero_dte_replay_outcomes_artifact_guard_v2 import run_zero_dte_replay_outcomes_artifact_guard_v2


def main() -> int:
    summary = run_zero_dte_replay_outcomes_artifact_guard_v2()
    print(
        json.dumps(
            {
                "zero_dte_replay_outcomes_guard_status": summary["zero_dte_replay_outcomes_guard_status"],
                "artifact_non_empty": summary.get("artifact_non_empty", False),
                "summary_path": summary["artifact_paths"]["zero_dte_replay_outcomes_artifact_guard_v2_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
