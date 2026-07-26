"""CLI for V7 trade-active repair policy."""
from __future__ import annotations

import json

from dopey_signal_research.trade_active_repair_policy_v7 import run_trade_active_repair_policy_v7


def main() -> int:
    summary = run_trade_active_repair_policy_v7()
    print(
        json.dumps(
            {
                "trade_active_repair_policy_status": summary["trade_active_repair_policy_status"],
                "repair_rule_count": summary["repair_rule_count"],
                "future_leakage_detected": summary["future_leakage_detected"],
                "thresholds_lowered": summary["thresholds_lowered"],
                "min_breakthrough_pf": summary["min_breakthrough_pf"],
                "no_trade_only_blocked": summary["no_trade_only_blocked"],
                "live_trading_enabled": summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
