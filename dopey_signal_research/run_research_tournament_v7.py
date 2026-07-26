"""CLI for V7 research tournament."""
from __future__ import annotations

import json

from dopey_signal_research.research_tournament_v7 import run_research_tournament_v7


def main() -> int:
    summary = run_research_tournament_v7()
    print(
        json.dumps(
            {
                "research_tournament_v7_status": summary["research_tournament_v7_status"],
                "trade_count": summary["trade_count"],
                "family_count": summary["family_count"],
                "subfamily_count": summary["subfamily_count"],
                "cohort_count": summary["cohort_count"],
                "positive_family_count": summary["positive_family_count"],
                "improved_vs_v6_count": summary["improved_vs_v6_count"],
                "pf_above_110_count": summary["pf_above_110_count"],
                "trade_active_pf_above_110_count": summary["trade_active_pf_above_110_count"],
                "no_trade_only_subfamily_count": summary["no_trade_only_subfamily_count"],
                "v6_top_pf": summary["v6_top_pf"],
                "holdout_survival_count": summary["holdout_survival_count"],
                "trade_active_holdout_survival_count": summary["trade_active_holdout_survival_count"],
                "regime_score_count": summary["regime_score_count"],
                "comparison_count": summary["comparison_count"],
                "top_family": summary["top_family"],
                "top_subfamily": summary["top_subfamily"],
                "top_cohort": summary["top_cohort"],
                "top_net_pnl": summary["top_net_pnl"],
                "top_profit_factor": summary["top_profit_factor"],
                "top_trade_active_profit_factor": summary["top_trade_active_profit_factor"],
                "top_sample_count": summary["top_sample_count"],
                "top_trade_active_sample_count": summary["top_trade_active_sample_count"],
                "v7_min_breakthrough_pf": summary["v7_min_breakthrough_pf"],
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
