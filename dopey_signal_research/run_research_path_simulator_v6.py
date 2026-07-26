"""CLI for V6 path simulator."""
from __future__ import annotations

import json

from dopey_signal_research.research_path_simulator_v6 import run_research_path_simulator_v6


def main() -> int:
    summary = run_research_path_simulator_v6()
    print(
        json.dumps(
            {
                "research_path_simulator_v6_status": summary["research_path_simulator_v6_status"],
                "input_candidate_count": summary["input_candidate_count"],
                "simulated_trade_count": summary["simulated_trade_count"],
                "long_call_count": summary["long_call_count"],
                "long_put_count": summary["long_put_count"],
                "no_trade_count": summary["no_trade_count"],
                "profitable_trade_count": summary["profitable_trade_count"],
                "losing_trade_count": summary["losing_trade_count"],
                "total_pnl": summary["total_pnl"],
                "average_pnl": summary["average_pnl"],
                "largest_symbol_pnl_contribution": summary["largest_symbol_pnl_contribution"],
                "corrupted_symbol_count": summary["corrupted_symbol_count"],
                "uvxy_like_corruption_detected": summary["uvxy_like_corruption_detected"],
                "future_ohlcv_used": summary["future_ohlcv_used"],
                "model_priced": summary["model_priced"],
                "quote_priced": summary["quote_priced"],
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
