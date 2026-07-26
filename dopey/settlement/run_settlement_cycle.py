"""CLI for truthful vNext forward settlement and calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .grading import SettlementPolicy
from .runtime import SettlementRunPaths, run_settlement_cycle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grade eligible DOPEY vNext forward predictions")
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--vnext-output-dir", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    output_dir = arguments.vnext_output_dir
    result = run_settlement_cycle(
        arguments.as_of_date,
        arguments.observed_at,
        SettlementRunPaths(
            prediction_ledger=output_dir / "forward_predictions.jsonl",
            settlement_memory=output_dir / "memory" / "settlements.jsonl",
            calibration_memory=output_dir / "memory" / "calibration.jsonl",
            calibration_summary=output_dir / "calibration_summary.json",
        ),
        SettlementPolicy(
            neutral_return_band=0.01,
            contested_margin=0.0025,
            maximum_price_gap_days=5,
            probability_floor=1e-12,
        ),
        10,
        30,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
