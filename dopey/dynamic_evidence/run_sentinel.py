"""CLI for the scheduled Dynamic Evidence Sentinel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import run_dynamic_evidence_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DOPEY's paper-only Dynamic Evidence Sentinel")
    parser.add_argument("--calibration-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-settlements", type=int, required=True)
    parser.add_argument("--target-error-rate", type=float, required=True)
    parser.add_argument("--maximum-recent-error-rate", type=float, required=True)
    parser.add_argument("--conformal-learning-rate", type=float, required=True)
    parser.add_argument("--conformal-window", type=int, required=True)
    parser.add_argument("--recent-error-window", type=int, required=True)
    parser.add_argument("--alpha-floor", type=float, required=True)
    parser.add_argument("--alpha-ceiling", type=float, required=True)
    parser.add_argument("--reference-window", type=int, required=True)
    parser.add_argument("--recent-drift-window", type=int, required=True)
    parser.add_argument("--drift-alpha", type=float, required=True)
    parser.add_argument("--null-accuracy", type=float, required=True)
    parser.add_argument("--betting-fraction", type=float, required=True)
    parser.add_argument("--family-alpha", type=float, required=True)
    arguments = parser.parse_args()
    value = json.loads(arguments.calibration_summary.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(
            "dynamic evidence calibration summary must be an object: "
            f"path={arguments.calibration_summary}"
        )
    artifact = run_dynamic_evidence_cycle(
        value,
        arguments.output,
        arguments.minimum_settlements,
        arguments.target_error_rate,
        arguments.maximum_recent_error_rate,
        arguments.conformal_learning_rate,
        arguments.conformal_window,
        arguments.recent_error_window,
        arguments.alpha_floor,
        arguments.alpha_ceiling,
        arguments.reference_window,
        arguments.recent_drift_window,
        arguments.drift_alpha,
        arguments.null_accuracy,
        arguments.betting_fraction,
        arguments.family_alpha,
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
