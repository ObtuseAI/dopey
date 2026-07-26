"""CLI for V6 profit/holdout/split scorer."""
from __future__ import annotations

import json

from dopey_signal_research.profit_holdout_split_scorer_v6 import run_profit_holdout_split_scorer_v6


def main() -> int:
    summary = run_profit_holdout_split_scorer_v6()
    print(
        json.dumps(
            {
                "profit_holdout_split_scorer_v6_status": summary["profit_holdout_split_scorer_v6_status"],
                "candidate_count": summary["candidate_count"],
                "prioritized_candidate_count": summary["prioritized_candidate_count"],
                "breakthrough_repair_candidate_count": summary["breakthrough_repair_candidate_count"],
                "holdout_repair_candidate_count": summary["holdout_repair_candidate_count"],
                "split_repair_candidate_count": summary["split_repair_candidate_count"],
                "score_axis_count": summary["score_axis_count"],
                "v6_min_breakthrough_pf": 1.10,
                "thresholds_lowered": False,
                "public_data_only": True,
                "live_trading_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
