"""CLI for the bounded autonomous strategy-engineering cycle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dopey.settlement.ledger import load_prediction_ledger
from dopey.memory.ledger import MemoryKind, load_memory_records

from .runtime import run_strategy_engineering_cycle


def _load_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_prediction_ledger(path)


def _load_optional_settlement_memory(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_memory_records(path, MemoryKind.SETTLEMENT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run governed reverse and forward strategy engineering")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--settlements", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--candidate-budget", type=int, required=True)
    parser.add_argument("--minimum-reverse-support", type=int, required=True)
    arguments = parser.parse_args()
    output = run_strategy_engineering_cycle(
        _load_optional_jsonl(arguments.predictions),
        _load_optional_settlement_memory(arguments.settlements),
        arguments.output_root,
        arguments.candidate_budget,
        arguments.minimum_reverse_support,
        datetime.now(timezone.utc),
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
