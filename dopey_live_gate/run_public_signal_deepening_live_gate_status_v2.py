"""CLI runner for public signal deepening live gate status V2."""
from __future__ import annotations

import json

from .public_signal_deepening_live_gate_status_v2 import run_public_signal_deepening_live_gate_status_v2


def main() -> int:
    summary = run_public_signal_deepening_live_gate_status_v2()
    print(json.dumps({
        "live_gate_status": summary["live_gate_status"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "broker_connection_enabled": summary["broker_connection_enabled"],
        "real_order_enabled": summary["real_order_enabled"],
        "env_present": summary["env_present"],
        "blocker_count": summary["blocker_count"],
        "robinhood_policy": summary["robinhood_policy"],
        "status_path": summary["artifact_paths"]["public_signal_deepening_live_gate_status_v2"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
