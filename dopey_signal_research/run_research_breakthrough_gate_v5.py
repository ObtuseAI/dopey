"""CLI for V5 breakthrough gate."""
from __future__ import annotations

import json

from dopey_signal_research.research_breakthrough_gate_v5 import run_research_breakthrough_gate_v5


def main() -> int:
    summary = run_research_breakthrough_gate_v5()
    print(
        json.dumps(
            {
                "research_breakthrough_gate_v5_status": summary["research_breakthrough_gate_v5_status"],
                "candidate_count": summary["candidate_count"],
                "breakthrough_candidate_count": summary["breakthrough_candidate_count"],
                "watchlist_count": summary["watchlist_count"],
                "rejection_count": summary["rejection_count"],
                "improved_watchlist_count": summary["improved_watchlist_count"],
                "pf_above_threshold_count": summary["pf_above_threshold_count"],
                "paper_champion_candidate_locked_count": summary["paper_champion_candidate_locked_count"],
                "top_rejection_reasons": summary["top_rejection_reasons"],
                "v5_min_breakthrough_pf": summary["v5_min_breakthrough_pf"],
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
