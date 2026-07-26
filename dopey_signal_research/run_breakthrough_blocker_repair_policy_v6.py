"""CLI for V6 breakthrough blocker repair policy."""
from __future__ import annotations

import json

from dopey_signal_research.breakthrough_blocker_repair_policy_v6 import run_breakthrough_blocker_repair_policy_v6


def main() -> int:
    summary = run_breakthrough_blocker_repair_policy_v6()
    print(
        json.dumps(
            {
                "breakthrough_blocker_repair_policy_status": summary["breakthrough_blocker_repair_policy_status"],
                "repair_rule_count": summary["repair_rule_count"],
                "future_leakage_detected": summary["future_leakage_detected"],
                "thresholds_lowered": summary["thresholds_lowered"],
                "live_trading_enabled": summary["live_trading_enabled"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
