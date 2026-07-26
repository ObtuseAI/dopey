"""CLI for the complete paper-only vNext operating bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dopey.organisms.templates import OBJECTIVE_SPECIALISTS

from .operational_bundle import run_operational_bundle


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the governed DOPEY vNext operational bundle")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--objective-type", required=True, choices=tuple(sorted(OBJECTIVE_SPECIALISTS)))
    parser.add_argument("--event-time", required=True)
    parser.add_argument("--market-time", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    result = run_operational_bundle(
        arguments.symbol,
        arguments.objective_type,
        arguments.event_time,
        arguments.market_time,
        arguments.as_of_date,
        arguments.observed_at,
        arguments.output_dir,
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "artifacts" / "dopey" / "equity_swing" / "cross_asset_regime.json",
        REPOSITORY_ROOT / "artifacts" / "dopey" / "equity_swing" / "news_intelligence.json",
        REPOSITORY_ROOT / "artifacts" / "dopey" / "signal_calibration" / "signal_calibration_summary.json",
        REPOSITORY_ROOT / "artifacts" / "dopey" / "acceleration" / "readiness_acceleration_plan.json",
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
