"""CLI for V7 research breakthrough gate."""
from __future__ import annotations

import json

from dopey_signal_research.research_breakthrough_gate_v7 import run_research_breakthrough_gate_v7


def main() -> int:
    summary = run_research_breakthrough_gate_v7()
    print(
        json.dumps(
            {
                "research_breakthrough_gate_v7_status": summary["research_breakthrough_gate_v7_status"],
                "candidate_count": summary["candidate_count"],
                "breakthrough_candidate_count": summary["breakthrough_candidate_count"],
                "watchlist_count": summary["watchlist_count"],
                "improved_watchlist_count": summary["improved_watchlist_count"],
                "rejection_count": summary["rejection_count"],
                "pf_above_threshold_count": summary["pf_above_threshold_count"],
                "trade_active_breakthrough_count": summary["trade_active_breakthrough_count"],
                "blocked_no_trade_only_count": summary["blocked_no_trade_only_count"],
                "paper_champion_candidate_locked_count": summary["paper_champion_candidate_locked_count"],
                "v7_min_breakthrough_pf": summary["v7_min_breakthrough_pf"],
                "v7_max_no_trade_ratio": summary["v7_max_no_trade_ratio"],
                "v7_min_trade_active_sample": summary["v7_min_trade_active_sample"],
                "thresholds_lowered": summary["thresholds_lowered"],
                "public_data_only": summary["public_data_only"],
                "live_trading_enabled": summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
