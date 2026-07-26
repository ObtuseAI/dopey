"""CLI for V7 public signal research scoreboard."""
from __future__ import annotations

import json

from dopey_scoreboard.public_signal_research_scoreboard_v7 import run_public_signal_research_scoreboard_v7


def main() -> int:
    scoreboard = run_public_signal_research_scoreboard_v7()
    print(
        json.dumps(
            {
                "scoreboard_v7_status": scoreboard["scoreboard_v7_status"],
                "v7_preflight_status": scoreboard["v7_preflight_status"],
                "v7_baseline_freeze_status": scoreboard["v7_baseline_freeze_status"],
                "v7_no_trade_audit_status": scoreboard["v7_no_trade_audit_status"],
                "v7_trade_active_edge_status": scoreboard["v7_trade_active_edge_status"],
                "v6_watchlist_diagnosis_v7_status": scoreboard["v6_watchlist_diagnosis_v7_status"],
                "v7_trade_active_repair_policy_status": scoreboard["v7_trade_active_repair_policy_status"],
                "v7_mutation_exec_status": scoreboard["v7_mutation_exec_status"],
                "v7_candidate_generator_status": scoreboard["v7_candidate_generator_status"],
                "v7_scorer_status": scoreboard["v7_scorer_status"],
                "v7_simulator_status": scoreboard["v7_simulator_status"],
                "v7_tournament_status": scoreboard["v7_tournament_status"],
                "v7_gate_status": scoreboard["v7_gate_status"],
                "v7_mutation_queue_status": scoreboard["v7_mutation_queue_status"],
                "v7_candidate_count": scoreboard["v7_candidate_count"],
                "v7_simulated_trade_count": scoreboard["v7_simulated_trade_count"],
                "v7_pf_above_110_count": scoreboard["v7_pf_above_110_count"],
                "v7_trade_active_pf_above_110_count": scoreboard["v7_trade_active_pf_above_110_count"],
                "v7_breakthrough_candidate_count": scoreboard["v7_breakthrough_candidate_count"],
                "v7_watchlist_count": scoreboard["v7_watchlist_count"],
                "v7_improved_vs_v6_count": scoreboard["v7_improved_vs_v6_count"],
                "v7_mutation_queue_count": scoreboard["v7_mutation_queue_count"],
                "v6_watchlist_count": scoreboard["v6_watchlist_count"],
                "v6_pf_above_110_count": scoreboard["v6_pf_above_110_count"],
                "no_trade_ratio": scoreboard["no_trade_ratio"],
                "trade_active_ratio": scoreboard["trade_active_ratio"],
                "no_trade_only_breakthroughs_blocked": scoreboard["no_trade_only_breakthroughs_blocked"],
                "future_leakage_detected": scoreboard["future_leakage_detected"],
                "uvxy_like_corruption_detected": scoreboard["uvxy_like_corruption_detected"],
                "live_gate_status": scoreboard["live_gate_status"],
                "live_trading_enabled": scoreboard["live_trading_enabled"],
                "thresholds_lowered": scoreboard["thresholds_lowered"],
                "public_data_only": scoreboard["public_data_only"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
