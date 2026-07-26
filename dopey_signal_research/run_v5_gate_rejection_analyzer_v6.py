"""CLI for V5 gate rejection analyzer (V6)."""
from __future__ import annotations

import json

from dopey_signal_research.v5_gate_rejection_analyzer_v6 import run_v5_gate_rejection_analyzer_v6


def main() -> int:
    summary = run_v5_gate_rejection_analyzer_v6()
    print(
        json.dumps(
            {
                "v5_gate_rejection_analyzer_status": summary["v5_gate_rejection_analyzer_status"],
                "watchlist_candidate_count": summary["watchlist_candidate_count"],
                "pf_above_threshold_watchlist_count": summary["pf_above_threshold_watchlist_count"],
                "breakthrough_blocker_count": summary["breakthrough_blocker_count"],
                "repairable_candidate_count": summary["repairable_candidate_count"],
                "live_trading_enabled": summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
