"""CLI for V5 no-trade filter optimizer."""
from __future__ import annotations

import json

from dopey_signal_research.no_trade_filter_optimizer_v5 import run_no_trade_filter_optimizer_v5


def main() -> int:
    summary = run_no_trade_filter_optimizer_v5()
    print(
        json.dumps(
            {
                "no_trade_filter_optimizer_v5_status": summary["no_trade_filter_optimizer_v5_status"],
                "filter_rule_count": summary["filter_rule_count"],
                "feature_rule_count": summary["feature_rule_count"],
                "historical_prior_rule_count": summary["historical_prior_rule_count"],
                "leakage_audit_passed_rule_count": summary["leakage_audit_passed_rule_count"],
                "leakage_audit_failed_rule_count": summary["leakage_audit_failed_rule_count"],
                "future_leakage_detected": summary["future_leakage_detected"],
                "coverage_preservation_status": summary["coverage_preservation_status"],
                "expected_pruned_trade_count": summary["expected_pruned_trade_count"],
                "v4_no_trade_filter_record_count": summary["v4_no_trade_filter_record_count"],
                "v5_min_breakthrough_pf": 1.10,
                "thresholds_lowered": False,
                "live_trading_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
