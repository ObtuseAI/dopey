"""CLI for the allowlisted autonomous strategy-research lane."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime import run_autoresearch_cycle, write_blocked_autoresearch_cycle
from .schema import ResearchFinding


def _load_findings(path: Path) -> tuple[ResearchFinding, ...]:
    if not path.exists():
        return ()
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"autoresearch findings must be a JSON array: path={path}")
    findings: list[ResearchFinding] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise ValueError(f"autoresearch finding must be an object: path={path}, index={index}")
        findings.append(
            {
                "finding_id": str(record["finding_id"]),
                "finding_type": str(record["finding_type"]),
                "lineage_id": str(record["lineage_id"]),
                "target_gene": str(record["target_gene"]),
                "direction": str(record["direction"]),
                "evidence_id": str(record["evidence_id"]),
            }
        )
    return tuple(findings)


def _next_generation(output_root: Path) -> int:
    latest = output_root / "latest_cycle.json"
    if not latest.exists():
        return 1
    value: Any = json.loads(latest.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"autoresearch latest cycle must be an object: path={latest}")
    generation = int(value.get("generation", 0))
    if generation < 0:
        raise ValueError(f"autoresearch latest generation is invalid: path={latest}, generation={generation}")
    return generation + 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue bounded autonomous strategy research")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--candidate-budget", type=int, required=True)
    arguments = parser.parse_args()
    generation = _next_generation(arguments.output_root)
    findings = _load_findings(arguments.findings)
    issued_at = datetime.now(timezone.utc)
    if not findings:
        output = write_blocked_autoresearch_cycle(
            arguments.output_root,
            arguments.findings,
            generation,
            issued_at,
        )
        print(json.dumps(output, sort_keys=True))
        return 0
    output = run_autoresearch_cycle(
        arguments.output_root,
        findings,
        arguments.candidate_budget,
        generation,
        issued_at,
    )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
