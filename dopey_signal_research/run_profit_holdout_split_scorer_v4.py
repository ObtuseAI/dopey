"""CLI runner for V4 profit/holdout/split scorer."""
from __future__ import annotations

import json

from dopey_signal_research.profit_holdout_split_scorer_v4 import run_profit_holdout_split_scorer_v4


def main() -> int:
    summary = run_profit_holdout_split_scorer_v4()
    print(
        json.dumps(
            {
                "profit_holdout_split_scorer_status": summary["profit_holdout_split_scorer_status"],
                "candidate_count": summary["candidate_count"],
                "prioritized_candidate_count": summary["prioritized_candidate_count"],
                "summary_path": summary["artifact_paths"]["profit_holdout_split_scorer_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
