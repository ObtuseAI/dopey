"""CLI for V7 live gate status."""
from __future__ import annotations

import json

from dopey_live_gate.public_signal_research_live_gate_status_v7 import (
    run_public_signal_research_live_gate_status_v7,
)


def main() -> int:
    summary = run_public_signal_research_live_gate_status_v7()
    print(
        json.dumps(
            {
                "live_gate_status": summary["live_gate_status"],
                "live_trading_enabled": summary["live_trading_enabled"],
                "broker_connection_enabled": summary["broker_connection_enabled"],
                "real_order_enabled": summary["real_order_enabled"],
                "credentials_present": summary["credentials_present"],
                "env_present": summary["env_present"],
                "official_robinhood_market_data_allowed": summary["official_robinhood_market_data_allowed"],
                "unofficial_robinhood_api_blocked": summary["unofficial_robinhood_api_blocked"],
                "robinhood_scraping_blocked": summary["robinhood_scraping_blocked"],
                "robinhood_reverse_auth_blocked": summary["robinhood_reverse_auth_blocked"],
                "robinhood_live_trading_enabled": summary["robinhood_live_trading_enabled"],
                "blocker_count": summary["blocker_count"],
                "breakthrough_candidate_count": summary["breakthrough_candidate_count"],
                "watchlist_candidate_count": summary["watchlist_candidate_count"],
                "v7_min_breakthrough_pf": summary["v7_min_breakthrough_pf"],
                "thresholds_lowered": summary["thresholds_lowered"],
                "public_data_only": summary["public_data_only"],
                "paper_only": summary["paper_only"],
                "live_blocked": summary["live_blocked"],
                "no_trade_only_breakthroughs_blocked": summary["no_trade_only_breakthroughs_blocked"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
