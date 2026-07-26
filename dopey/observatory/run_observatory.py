"""CLI for the canonical local DOPEY observatory artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_observatory_artifact, write_observatory_artifact


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the portable DOPEY sovereign research observatory")
    parser.add_argument("--vnext-output-dir", required=True, type=Path)
    parser.add_argument("--readiness-path", required=True, type=Path)
    parser.add_argument("--evolution-status-path", required=True, type=Path)
    parser.add_argument("--settlement-cycle-path", required=True, type=Path)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    artifact = build_observatory_artifact(
        arguments.vnext_output_dir,
        arguments.readiness_path,
        arguments.evolution_status_path,
        arguments.settlement_cycle_path,
        arguments.generated_at,
        REPOSITORY_ROOT,
    )
    write_observatory_artifact(arguments.output, artifact)
    print(json.dumps({
        "output": str(arguments.output),
        "surface": artifact["surface"],
        "snapshot_status": artifact["snapshot"]["status"],
        "dataset_count": len(artifact["snapshot"]["datasets"]),
        "paper_only": True,
        "live_blocked": True,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
