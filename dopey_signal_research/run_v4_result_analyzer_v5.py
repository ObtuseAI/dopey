"""CLI for V5 V4 result analyzer (and V4 repair target extractor)."""
from __future__ import annotations

import json

from dopey_signal_research.v4_repair_target_extractor_v5 import run_v4_repair_target_extractor_v5
from dopey_signal_research.v4_result_analyzer_v5 import run_v4_result_analyzer_v5


def main() -> int:
    summary = run_v4_result_analyzer_v5()
    ext = run_v4_repair_target_extractor_v5()
    print(
        json.dumps(
            {
                "v4_result_analyzer_status": summary["v4_result_analyzer_status"],
                "v4_repair_target_count": summary["v4_repair_target_count"],
                "v4_near_breakthrough_count": summary["v4_near_breakthrough_count"],
                "v4_loss_driver_count": summary["v4_loss_driver_count"],
                "v4_watchlist_count": summary["v4_watchlist_count"],
                "v4_breakthrough_count": summary["v4_breakthrough_count"],
                "v4_top_pf": summary["v4_top_pf"],
                "v4_research_candidate_count": summary["v4_research_candidate_count"],
                "v4_simulated_trade_count": summary["v4_simulated_trade_count"],
                "extracted_repair_target_count": ext["v4_repair_target_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
