"""CLI for the pre-vNext baseline evidence snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path

from .baseline import build_baseline_report, collect_artifact_schema_counts, write_baseline_report


REPO_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze the current DOPEY v4 evidence baseline")
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    report = build_baseline_report(
        REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "action_readiness_gate.json",
        REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "signal_calibration" / "signal_calibration_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "research_supervisor" / "resilient_research_supervisor_summary.json",
        tuple(
            path
            for path in (REPO_ROOT / "tests").glob("test_*.py")
            if path.name != "test_vnext_sovereign_research.py"
        ),
        collect_artifact_schema_counts(REPO_ROOT / "artifacts" / "dopey"),
        arguments.captured_at,
        arguments.source_revision,
    )
    write_baseline_report(arguments.output, report)


if __name__ == "__main__":
    main()
