"""OPERATOR TOOL - build the situational scorecard (the championship call sheet).

Synthesizes the Trade Memory Graph, cross-lane convergence, option-cost model,
and current regime into a situation-indexed call sheet. The highest-conviction
calls are AVOID (eliminate the negative plays); there is no TRADE call at L0.
Measure-only.

Usage:  .venv\\Scripts\\python operator_tools\\operator_situational_scorecard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey.strategy_engineering.situational_scorecard import run_situational_scorecard  # noqa: E402


def main() -> int:
    card = run_situational_scorecard()
    print(
        json.dumps(
            {
                "headline": card["headline"],
                "current_market_situation": card["current_market_situation"],
                "avoid_list": card["avoid_list"],
                "monitor_candidates": card["monitor_candidates"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
