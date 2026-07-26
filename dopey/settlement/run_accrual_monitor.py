"""CLI for the readiness-neutral vNext forward-evidence accrual monitor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .accrual import run_forward_accrual_monitor
from .grading import SettlementPolicy


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect DOPEY vNext forward-evidence accrual")
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--vnext-output-dir", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    output_dir = arguments.vnext_output_dir
    result = run_forward_accrual_monitor(
        output_dir / "forward_predictions.jsonl",
        output_dir / "memory" / "settlements.jsonl",
        arguments.as_of_date,
        output_dir / "forward_accrual_monitor.json",
        SettlementPolicy(
            neutral_return_band=0.01,
            contested_margin=0.0025,
            maximum_price_gap_days=5,
            probability_floor=1e-12,
        ),
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
