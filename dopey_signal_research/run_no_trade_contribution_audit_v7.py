"""CLI for V7 no-trade contribution audit."""
from __future__ import annotations

import json

from dopey_signal_research.no_trade_contribution_audit_v7 import run_no_trade_contribution_audit_v7


def main() -> int:
    summary = run_no_trade_contribution_audit_v7()
    print(
        json.dumps(
            {
                "no_trade_contribution_audit_status": summary["no_trade_contribution_audit_status"],
                "leaderboard_count": summary["leaderboard_count"],
                "watchlist_count": summary["watchlist_count"],
                "rejection_count": summary["rejection_count"],
                "no_trade_ratio_overall": summary["no_trade_ratio_overall"],
                "trade_active_ratio_overall": summary["trade_active_ratio_overall"],
                "no_trade_only_candidate_count": summary["no_trade_only_candidate_count"],
                "blocked_no_trade_only_count": summary["blocked_no_trade_only_count"],
                "live_trading_enabled": summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
