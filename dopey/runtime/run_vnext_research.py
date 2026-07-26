"""CLI for the one-symbol vNext vertical slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dopey.organisms.templates import OBJECTIVE_SPECIALISTS

from .vnext_research import VNextRunPaths, run_vnext_research


REPO_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed DOPEY vNext research for one symbol")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--objective-type", required=True, choices=tuple(sorted(OBJECTIVE_SPECIALISTS)))
    parser.add_argument("--event-time", required=True)
    parser.add_argument("--market-time", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    paths = VNextRunPaths(
        output_dir=arguments.output_dir,
        cross_asset_context=REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "cross_asset_regime.json",
        news_context=REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "news_intelligence.json",
        calibration_summary=REPO_ROOT / "artifacts" / "dopey" / "signal_calibration" / "signal_calibration_summary.json",
        cross_section_context=REPO_ROOT / "artifacts" / "dopey" / "vnext" / "cross_sectional_context.json",
        macro_manifest=REPO_ROOT / "dopey_data" / "real" / "manifests" / "macro_context_manifest.json",
        fundamental_file_reference="dopey_data/real/raw/macro_context/fundamentals.csv",
        options_manifest=REPO_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json",
        earnings_directory=REPO_ROOT / "dopey_data" / "real" / "raw" / "earnings_calendar",
    )
    summary = run_vnext_research(
        arguments.symbol,
        arguments.objective_type,
        arguments.event_time,
        arguments.market_time,
        paths,
    )
    print(json.dumps(summary, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
