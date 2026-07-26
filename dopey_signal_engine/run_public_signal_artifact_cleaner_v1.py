"""CLI runner for public signal artifact cleaner V1."""
from __future__ import annotations

import json

from dopey_signal_engine.public_signal_artifact_cleaner_v1 import run_public_signal_artifact_cleaner_v1


def main() -> int:
    summary = run_public_signal_artifact_cleaner_v1()
    print(json.dumps({
        "signal_artifact_cleaner_status": summary["signal_artifact_cleaner_status"],
        "input_signal_count": summary["input_signal_count"],
        "removed_test_signal_count": summary["removed_test_signal_count"],
        "output_signal_count": summary["output_signal_count"],
        "simv2_rows_remaining": summary["simv2_rows_remaining"],
        "decision_artifacts_clean": summary["decision_artifacts_clean"],
        "summary_path": summary["artifact_paths"]["public_signal_artifact_cleaner_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
