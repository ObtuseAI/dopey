"""Network-free CLI for both tails of option-ROI discovery.

Finds the biggest option winners and losers across staged chain snapshots,
uses losers as failure evidence, and forward-engineers testable hypotheses
from winner mechanisms without treating either tail as a trade signal.

    python -m dopey.strategy_engineering.run_option_roi_discovery \
        --chains-root dopey_data/real/raw/options_chains
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .option_roi_discovery import discover_option_roi_strategies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Option-ROI discovery (paper research; no edge claimed).")
    parser.add_argument("--chains-root", default="dopey_data/real/raw/options_chains")
    parser.add_argument("--winner-quantile", type=float, default=0.80)
    parser.add_argument("--minimum-support", type=int, default=8)
    parser.add_argument("--minimum-absolute-effect", type=float, default=0.10)
    parser.add_argument("--maximum-hypotheses", type=int, default=12)
    parser.add_argument("--forward-candidate-budget", type=int, default=8)
    parser.add_argument("--top-winner-report", type=int, default=25)
    parser.add_argument("--top-loser-report", type=int, default=25)
    args = parser.parse_args(argv)

    report = discover_option_roi_strategies(
        Path(args.chains_root),
        winner_quantile=args.winner_quantile,
        minimum_support=args.minimum_support,
        minimum_absolute_effect=args.minimum_absolute_effect,
        maximum_hypotheses=args.maximum_hypotheses,
        forward_candidate_budget=args.forward_candidate_budget,
        top_winner_report=args.top_winner_report,
        top_loser_report=args.top_loser_report,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
