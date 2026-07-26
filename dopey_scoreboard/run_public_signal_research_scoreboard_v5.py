"""CLI for V5 public signal research scoreboard."""
from __future__ import annotations

import json

from dopey_scoreboard.public_signal_research_scoreboard_v5 import run_public_signal_research_scoreboard_v5


def main() -> int:
    scoreboard = run_public_signal_research_scoreboard_v5()
    print(
        json.dumps(
            {
                "scoreboard_v5_status": scoreboard["scoreboard_v5_status"],
                "v5_preflight_status": scoreboard["v5_preflight_status"],
                "v5_baseline_freeze_status": scoreboard["v5_baseline_freeze_status"],
                "v5_safe_append_status": scoreboard["v5_safe_append_status"],
                "v5_expensive_lane_status": scoreboard["v5_expensive_lane_status"],
                "v5_tournament_status": scoreboard["v5_tournament_status"],
                "v5_gate_status": scoreboard["v5_gate_status"],
                "v5_candidate_count": scoreboard["v5_candidate_count"],
                "v5_simulated_trade_count": scoreboard["v5_simulated_trade_count"],
                "v5_pf_above_110_count": scoreboard["v5_pf_above_110_count"],
                "v5_breakthrough_candidate_count": scoreboard["v5_breakthrough_candidate_count"],
                "v5_watchlist_count": scoreboard["v5_watchlist_count"],
                "v5_improved_vs_v4_count": scoreboard["v5_improved_vs_v4_count"],
                "v5_top_family": scoreboard["v5_top_family"],
                "v5_top_subfamily": scoreboard["v5_top_subfamily"],
                "v5_top_profit_factor": scoreboard["v5_top_profit_factor"],
                "v5_top_net_pnl": scoreboard["v5_top_net_pnl"],
                "v5_mutation_queue_count": scoreboard["v5_mutation_queue_count"],
                "v4_top_pf": scoreboard["v4_top_pf"],
                "uvxy_like_corruption_detected": scoreboard["uvxy_like_corruption_detected"],
                "future_leakage_detected": scoreboard["future_leakage_detected"],
                "live_gate_status": scoreboard["live_gate_status"],
                "live_trading_enabled": scoreboard["live_trading_enabled"],
                "thresholds_lowered": False,
                "public_data_only": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
