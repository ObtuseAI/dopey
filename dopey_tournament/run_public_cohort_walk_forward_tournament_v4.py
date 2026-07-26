"""CLI runner for cohort walk-forward tournament V4."""
from __future__ import annotations

import json

from .public_cohort_walk_forward_tournament_v4 import run_public_cohort_walk_forward_tournament_v4


def main() -> int:
    summary = run_public_cohort_walk_forward_tournament_v4()
    print(json.dumps({
        "public_cohort_walk_forward_status": summary["public_cohort_walk_forward_status"],
        "trade_count": summary["trade_count"],
        "cohort_counts": summary["cohort_counts"],
        "leaderboard_count": summary["leaderboard_count"],
        "candidate_champion_count": summary["candidate_champion_count"],
        "top_strategy": summary["top_strategy"],
        "top_cohort_level": summary["top_cohort_level"],
        "top_net_pnl": summary["top_net_pnl"],
        "top_profit_factor": summary["top_profit_factor"],
        "top_sample_count": summary["top_sample_count"],
        "top_split_pass_rate": summary["top_split_pass_rate"],
        "public_data_only": summary["public_data_only"],
        "summary_path": summary["artifact_paths"]["public_cohort_walk_forward_tournament_v4_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
