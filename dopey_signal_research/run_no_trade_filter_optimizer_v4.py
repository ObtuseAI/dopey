"""CLI runner for V4 no-trade filter optimizer."""
from __future__ import annotations

import json

from dopey_signal_research.no_trade_filter_optimizer_v4 import run_no_trade_filter_optimizer_v4


def main() -> int:
    summary = run_no_trade_filter_optimizer_v4()
    print(
        json.dumps(
            {
                "no_trade_filter_optimizer_status": summary["no_trade_filter_optimizer_status"],
                "filter_rule_count": summary["filter_rule_count"],
                "future_leakage_detected": summary["future_leakage_detected"],
                "summary_path": summary["artifact_paths"]["no_trade_filter_optimizer_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
