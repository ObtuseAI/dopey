"""CLI runner for public champion hardening gate V1."""
from __future__ import annotations

import json

from dopey_champion.public_champion_hardening_gate_v1 import run_public_champion_hardening_gate_v1


def main() -> int:
    summary = run_public_champion_hardening_gate_v1()
    print(json.dumps({
        "champion_hardening_gate_status": summary["champion_hardening_gate_status"],
        "hardened_champion_count": summary["hardened_champion_count"],
        "conditional_champion_count": summary["conditional_champion_count"],
        "demoted_champion_count": summary["demoted_champion_count"],
        "repair_queue_count": summary["repair_queue_count"],
        "summary_path": summary["artifact_paths"]["public_champion_hardening_gate_v1_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
