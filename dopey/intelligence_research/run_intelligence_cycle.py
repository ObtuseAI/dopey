"""CLI for the DOPEY experimental-domain intelligence research cycle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dopey_adapter import build_dopey_knowledge_state
from .runtime import run_intelligence_research_cycle


def _next_generation(output_root: Path) -> int:
    latest = output_root / "latest_cycle.json"
    if not latest.exists():
        return 1
    raw: Any = json.loads(latest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"intelligence research latest cycle must be an object: path={latest}")
    generation = int(raw.get("generation", 0) or 0)
    if generation < 0:
        raise ValueError(f"intelligence research generation is invalid: generation={generation}")
    return generation + 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Research better methods of discovery using DOPEY as one domain")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--schedule-state", type=Path, required=True)
    parser.add_argument("--autoresearch", type=Path, required=True)
    parser.add_argument("--promotion-cycle", type=Path, required=True)
    parser.add_argument("--llm-research", type=Path, required=True)
    parser.add_argument("--question-budget", type=int, required=True)
    parser.add_argument("--hypothesis-budget", type=int, required=True)
    parser.add_argument("--cognitive-level", type=int, required=True)
    arguments = parser.parse_args()
    issued_at = datetime.now(timezone.utc)
    state = build_dopey_knowledge_state(
        arguments.readiness,
        arguments.schedule_state,
        arguments.autoresearch,
        arguments.promotion_cycle,
        arguments.llm_research,
        issued_at,
    )
    output = run_intelligence_research_cycle(
        state,
        arguments.output_root,
        arguments.question_budget,
        arguments.hypothesis_budget,
        arguments.cognitive_level,
        _next_generation(arguments.output_root),
        issued_at,
    )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
