"""Evaluate queued autoresearch experiments against pinned historical partitions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .experiment_runner import run_deterministic_experiment_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-ledger", type=Path, required=True)
    parser.add_argument("--history-manifest", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--findings-output", type=Path, required=True)
    parser.add_argument("--evaluation-output-root", type=Path, required=True)
    arguments = parser.parse_args()
    output = run_deterministic_experiment_evaluation(
        arguments.experiment_ledger,
        arguments.history_manifest,
        arguments.history_root,
        arguments.findings_output,
        arguments.evaluation_output_root,
        datetime.now(timezone.utc),
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["evaluation_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
