"""CLI for V7 profit/holdout/split scorer."""
from __future__ import annotations

import json

from dopey_signal_research.profit_holdout_split_scorer_v7 import run_profit_holdout_split_scorer_v7


def main() -> int:
    summary = run_profit_holdout_split_scorer_v7()
    print(
        json.dumps(
            {
                "profit_holdout_split_scorer_v7_status": summary["profit_holdout_split_scorer_v7_status"],
                "candidate_count": summary["candidate_count"],
                "prioritized_candidate_count": summary["prioritized_candidate_count"],
                "breakthrough_repair_candidate_count": summary["breakthrough_repair_candidate_count"],
                "holdout_repair_candidate_count": summary["holdout_repair_candidate_count"],
                "split_repair_candidate_count": summary["split_repair_candidate_count"],
                "trade_active_repair_candidate_count": summary["trade_active_repair_candidate_count"],
                "trade_active_candidate_count": summary["trade_active_candidate_count"],
                "no_trade_candidate_count": summary["no_trade_candidate_count"],
                "no_trade_only_breakthrough_blocked_count": summary["no_trade_only_breakthrough_blocked_count"],
                "no_trade_ratio": summary["no_trade_ratio"],
                "no_trade_ratio_below_cap": summary["no_trade_ratio_below_cap"],
                "score_axis_count": summary["score_axis_count"],
                "v7_min_breakthrough_pf": summary["v7_min_breakthrough_pf"],
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
