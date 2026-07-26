"""CLI for V6 research tournament."""
from __future__ import annotations

import json

from dopey_signal_research.research_tournament_v6 import run_research_tournament_v6


def main() -> int:
    summary = run_research_tournament_v6()
    print(
        json.dumps(
            {
                "research_tournament_v6_status": summary["research_tournament_v6_status"],
                "trade_count": summary["trade_count"],
                "family_count": summary["family_count"],
                "subfamily_count": summary["subfamily_count"],
                "cohort_count": summary["cohort_count"],
                "positive_family_count": summary["positive_family_count"],
                "improved_vs_v5_count": summary["improved_vs_v5_count"],
                "pf_above_110_count": summary["pf_above_110_count"],
                "gate_blocker_repaired_count": summary["gate_blocker_repaired_count"],
                "v5_top_pf": summary["v5_top_pf"],
                "holdout_survival_count": summary["holdout_survival_count"],
                "regime_score_count": summary["regime_score_count"],
                "comparison_count": summary["comparison_count"],
                "top_family": summary["top_family"],
                "top_subfamily": summary["top_subfamily"],
                "top_cohort": summary["top_cohort"],
                "top_net_pnl": summary["top_net_pnl"],
                "top_profit_factor": summary["top_profit_factor"],
                "top_sample_count": summary["top_sample_count"],
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
