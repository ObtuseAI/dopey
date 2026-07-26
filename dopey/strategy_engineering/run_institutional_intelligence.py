"""CLI for the source-backed institutional intelligence cycle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .institutional_runtime import run_institutional_intelligence_cycle
from .schema import CouncilObservation, ResearchGap, ThesisEscrow


def _object_array(value: object, field: str, input_path: Path) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(record, dict) for record in value
    ):
        raise TypeError(
            "institutional intelligence input field must be an object array: "
            f"path={input_path}, field={field}"
        )
    return cast(list[dict[str, Any]], value)


def _observations_by_candidate(
    value: object,
    input_path: Path,
) -> dict[str, tuple[CouncilObservation, ...]]:
    if not isinstance(value, dict):
        raise TypeError(
            "institutional intelligence observations must be an object: "
            f"path={input_path}"
        )
    observations: dict[str, tuple[CouncilObservation, ...]] = {}
    for candidate_id, records in value.items():
        if not isinstance(candidate_id, str):
            raise TypeError(
                "institutional intelligence observation key must be text: "
                f"path={input_path}, key_type={type(candidate_id).__name__}"
            )
        observations[candidate_id] = tuple(
            cast(CouncilObservation, record)
            for record in _object_array(
                records,
                f"observations_by_candidate.{candidate_id}",
                input_path,
            )
        )
    return observations


def _load_cycle_input(
    input_path: Path,
) -> tuple[
    tuple[ThesisEscrow, ...],
    dict[str, tuple[CouncilObservation, ...]],
    tuple[ResearchGap, ...],
]:
    raw: object = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(
            f"institutional intelligence input must be an object: path={input_path}"
        )
    theses = tuple(
        cast(ThesisEscrow, record)
        for record in _object_array(raw.get("theses"), "theses", input_path)
    )
    observations = _observations_by_candidate(
        raw.get("observations_by_candidate"),
        input_path,
    )
    gaps = tuple(
        cast(ResearchGap, record)
        for record in _object_array(raw.get("gaps"), "gaps", input_path)
    )
    return theses, observations, gaps


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a research-only institutional doctrine and gap-priority artifact."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--research-budget-units", type=int, required=True)
    parser.add_argument("--issued-at", type=str, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    issued_at = datetime.fromisoformat(args.issued_at.replace("Z", "+00:00"))
    theses, observations, gaps = _load_cycle_input(args.input)
    result = run_institutional_intelligence_cycle(
        theses,
        observations,
        gaps,
        args.output_root,
        args.research_budget_units,
        issued_at,
    )
    summary = {
        "cycle_status": result["cycle_status"],
        "cycle_hash": result["cycle_hash"],
        "source_count": result["source_count"],
        "doctrine_count": result["doctrine_count"],
        "gap_count": result["gap_portfolio"]["gap_count"],
        "allocated_budget_units": result["gap_portfolio"]["allocated_budget_units"],
        "latest_cycle_path": str(args.output_root / "latest_cycle.json"),
        "latest_gap_portfolio_path": str(
            args.output_root / "latest_gap_portfolio.json"
        ),
        "positive_promotion_allowed": result["positive_promotion_allowed"],
        "order_construction_allowed": result["order_construction_allowed"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
