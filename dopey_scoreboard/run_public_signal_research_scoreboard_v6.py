"""CLI for V6 public signal research scoreboard."""
from __future__ import annotations

import json

from dopey_scoreboard.public_signal_research_scoreboard_v6 import run_public_signal_research_scoreboard_v6


def main() -> int:
    scoreboard = run_public_signal_research_scoreboard_v6()
    print(
        json.dumps(
            {
                "scoreboard_v6_status": scoreboard["scoreboard_v6_status"],
                "v6_preflight_status": scoreboard["v6_preflight_status"],
                "v6_tournament_status": scoreboard["v6_tournament_status"],
                "v6_gate_status": scoreboard["v6_gate_status"],
                "v6_candidate_count": scoreboard["v6_candidate_count"],
                "v6_simulated_trade_count": scoreboard["v6_simulated_trade_count"],
                "v6_pf_above_110_count": scoreboard["v6_pf_above_110_count"],
                "v6_breakthrough_candidate_count": scoreboard["v6_breakthrough_candidate_count"],
                "v6_watchlist_count": scoreboard["v6_watchlist_count"],
                "v6_improved_vs_v5_count": scoreboard["v6_improved_vs_v5_count"],
                "v6_top_family": scoreboard["v6_top_family"],
                "v6_top_subfamily": scoreboard["v6_top_subfamily"],
                "v6_top_profit_factor": scoreboard["v6_top_profit_factor"],
                "v6_top_net_pnl": scoreboard["v6_top_net_pnl"],
                "v6_mutation_queue_count": scoreboard["v6_mutation_queue_count"],
                "v5_top_pf": scoreboard["v5_top_pf"],
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
