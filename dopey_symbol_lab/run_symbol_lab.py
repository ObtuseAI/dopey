"""Command-line entrypoint for the governed per-symbol research laboratory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .lab import build_symbol_lab_state, run_symbol_lab_batch


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the paper-only DOPEY symbol intelligence lab")
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--all", action="store_true", dest="all_symbols")
    parser.add_argument("--strategy", choices=("auto", "trend", "momentum", "breakout", "mean_reversion", "volatility", "bullish_scenario", "bearish_scenario"), default="auto")
    parser.add_argument("--scenario-price", type=float)
    parser.add_argument("--days-forward", type=int, default=14)
    parser.add_argument("--iv-shift", type=float, default=0.0)
    return parser.parse_args()


def _batch_console_summary(batch: dict[str, object]) -> dict[str, object]:
    results = batch.get("results")
    if not isinstance(results, list):
        raise TypeError("symbol-lab batch results must be a list")
    projector_status_counts: dict[str, int] = {}
    ranked_expression_count = 0
    current_signal_symbol_count = 0
    for result in results:
        if not isinstance(result, dict):
            raise TypeError("symbol-lab batch result rows must be objects")
        status = str(result.get("option_projector_status"))
        projector_status_counts[status] = projector_status_counts.get(status, 0) + 1
        if result.get("best_expression_id") is not None:
            ranked_expression_count += 1
        active_strategy_ids = result.get("active_strategy_ids")
        if isinstance(active_strategy_ids, list) and len(active_strategy_ids) > 0:
            current_signal_symbol_count += 1
    return {
        "artifact_type": batch.get("artifact_type"),
        "schema_version": batch.get("schema_version"),
        "batch_status": batch.get("batch_status"),
        "batch_hash": batch.get("batch_hash"),
        "requested_symbol_count": batch.get("requested_symbol_count"),
        "completed_symbol_count": batch.get("completed_symbol_count"),
        "failed_symbol_count": batch.get("failed_symbol_count"),
        "current_signal_symbol_count": current_signal_symbol_count,
        "ranked_option_expression_symbol_count": ranked_expression_count,
        "option_projector_status_counts": dict(sorted(projector_status_counts.items())),
        "paper_only": batch.get("paper_only"),
        "live_blocked": batch.get("live_blocked"),
        "profitability_claim_allowed": batch.get("profitability_claim_allowed"),
        "promotion_allowed": batch.get("promotion_allowed"),
        "full_artifact": "artifacts/dopey/symbol_lab/latest_batch_summary.json",
    }


def main() -> int:
    arguments = _arguments()
    symbols = [] if arguments.symbols is None else [str(symbol).upper() for symbol in arguments.symbols]
    if arguments.all_symbols:
        result = run_symbol_lab_batch(REPOSITORY_ROOT, symbols)
        console_result = _batch_console_summary(result)
    elif len(symbols) == 1:
        result = build_symbol_lab_state(
            REPOSITORY_ROOT,
            symbols[0],
            str(arguments.strategy),
            arguments.scenario_price,
            int(arguments.days_forward),
            float(arguments.iv_shift),
        )
        console_result = result
    else:
        raise ValueError("provide exactly one --symbol for an interactive result, or use --all")
    print(json.dumps(console_result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
