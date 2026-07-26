"""CLI entrypoint for the real-history honest backtester lane."""
from __future__ import annotations

import json

from .real_history_honest_backtester import run_real_history_honest_backtester


def main() -> int:
    result = run_real_history_honest_backtester()
    print(
        json.dumps(
            {
                "backtest_status": result["backtest_status"],
                "history_dataset_status": result["history_dataset_status"],
                "real_history_used": result["real_history_used"],
                "trade_intent_count": result.get("trade_intent_count", 0),
                "trade_record_count": result.get("trade_record_count", 0),
                "total_path_pnl_model_units": result.get("total_path_pnl_model_units", 0.0),
                "max_drawdown_model_units": result.get("max_drawdown_model_units", 0.0),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
