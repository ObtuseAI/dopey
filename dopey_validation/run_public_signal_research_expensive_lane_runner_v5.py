"""CLI for V5 expensive lane runner."""
from __future__ import annotations

import json

from dopey_validation.public_signal_research_expensive_lane_runner_v5 import (
    run_public_signal_research_expensive_lane_runner_v5,
)


def main() -> int:
    summary = run_public_signal_research_expensive_lane_runner_v5()
    print(
        json.dumps(
            {
                "expensive_lane_runner_status": summary["expensive_lane_runner_status"],
                "offline_evidence_replay_audit_status": summary["offline_evidence_replay_audit_status"],
                "artifact_compaction_export_verifier_status": summary["artifact_compaction_export_verifier_status"],
                "timeout_count": summary["timeout_count"],
                "lane_count": summary["lane_count"],
                "timeout_recorded_as_pass": summary["timeout_recorded_as_pass"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
