"""CLI for V5 research candidate generator."""
from __future__ import annotations

import json

from dopey_signal_research.research_candidate_generator_v5 import run_research_candidate_generator_v5


def main() -> int:
    summary = run_research_candidate_generator_v5()
    print(
        json.dumps(
            {
                "research_candidate_generator_v5_status": summary["research_candidate_generator_v5_status"],
                "candidate_count": summary["candidate_count"],
                "family_count": summary["family_count"],
                "subfamily_count": summary["subfamily_count"],
                "symbol_count": summary["symbol_count"],
                "sector_count": summary["sector_count"],
                "long_call_count": summary["long_call_count"],
                "long_put_count": summary["long_put_count"],
                "no_trade_count": summary["no_trade_count"],
                "no_trade_filtered_count": summary["no_trade_filtered_count"],
                "fixture_candidate_count": summary["fixture_candidate_count"],
                "family_share_max": summary["family_share_max"],
                "max_family_share_cap": summary["max_family_share_cap"],
                "v5_min_breakthrough_pf": 1.10,
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
