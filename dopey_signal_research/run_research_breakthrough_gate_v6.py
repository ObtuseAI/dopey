"""CLI for V6 research breakthrough gate."""
from __future__ import annotations

import json

from dopey_signal_research.research_breakthrough_gate_v6 import run_research_breakthrough_gate_v6


def main() -> int:
    summary = run_research_breakthrough_gate_v6()
    print(
        json.dumps(
            {
                "research_breakthrough_gate_v6_status": summary["research_breakthrough_gate_v6_status"],
                "candidate_count": summary["candidate_count"],
                "breakthrough_candidate_count": summary["breakthrough_candidate_count"],
                "watchlist_count": summary["watchlist_count"],
                "improved_watchlist_count": summary["improved_watchlist_count"],
                "rejection_count": summary["rejection_count"],
                "pf_above_threshold_count": summary["pf_above_threshold_count"],
                "paper_champion_candidate_locked_count": summary["paper_champion_candidate_locked_count"],
                "v6_min_breakthrough_pf": summary["v6_min_breakthrough_pf"],
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
