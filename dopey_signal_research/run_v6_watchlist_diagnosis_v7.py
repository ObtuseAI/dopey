"""CLI for V6 watchlist and blocker diagnosis (V7)."""
from __future__ import annotations

import json

from dopey_signal_research.v6_gate_blocker_analyzer_v7 import run_v6_gate_blocker_analyzer_v7


def main() -> int:
    summary = run_v6_gate_blocker_analyzer_v7()
    print(
        json.dumps(
            {
                "v6_watchlist_diagnosis_v7_status": summary["v6_watchlist_diagnosis_v7_status"],
                "watchlist_candidate_count": summary["watchlist_candidate_count"],
                "pf_above_110_count": summary["pf_above_110_count"],
                "diagnosed_candidate_count": summary["diagnosed_candidate_count"],
                "breakthrough_blocker_count": summary["breakthrough_blocker_count"],
                "repairable_candidate_count": summary["repairable_candidate_count"],
                "no_trade_dominant_count": summary["no_trade_dominant_count"],
                "live_trading_enabled": summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
