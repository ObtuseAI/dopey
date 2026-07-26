"""CLI entry point for V7 research candidate generator (Workstream F)."""
from __future__ import annotations

import json

from dopey_signal_research.research_candidate_generator_v7 import run_research_candidate_generator_v7


def main() -> int:
    summary = run_research_candidate_generator_v7()
    print(
        json.dumps(
            {
                "research_candidate_generator_v7_status": summary["research_candidate_generator_v7_status"],
                "candidate_count": summary["candidate_count"],
                "family_count": summary["family_count"],
                "subfamily_count": summary["subfamily_count"],
                "symbol_count": summary["symbol_count"],
                "sector_count": summary["sector_count"],
                "long_call_count": summary["long_call_count"],
                "long_put_count": summary["long_put_count"],
                "no_trade_count": summary["no_trade_count"],
                "trade_active_count": summary["trade_active_count"],
                "no_trade_ratio": summary["no_trade_ratio"],
                "family_share_max": summary["family_share_max"],
                "max_family_share_cap": summary["max_family_share_cap"],
                "family_share_cap_respected": summary["family_share_cap_respected"],
                "max_no_trade_ratio_respected": summary["max_no_trade_ratio_respected"],
                "min_trade_active_per_pair": summary["min_trade_active_per_pair"],
                "trade_active_sample_respected": summary["trade_active_sample_respected"],
                "no_trade_only_breakthrough_blocked": summary["no_trade_only_breakthrough_blocked"],
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
