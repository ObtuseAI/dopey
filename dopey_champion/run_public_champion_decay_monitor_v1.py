"""CLI runner for public champion decay monitor V1."""
from __future__ import annotations

import json

from dopey_champion.public_champion_decay_monitor_v1 import run_public_champion_decay_monitor_v1


def main() -> int:
    summary = run_public_champion_decay_monitor_v1()
    print(json.dumps({
        "decay_monitor_status": summary["decay_monitor_status"],
        "champions_monitored": summary["champions_monitored"],
        "decay_alert_count": summary["decay_alert_count"],
        "stable_champion_count": summary["stable_champion_count"],
        "degraded_champion_count": summary["degraded_champion_count"],
        "summary_path": summary["artifact_paths"]["public_champion_decay_monitor_v1_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
