"""CLI runner for public champion hardening repair queue V1."""
from __future__ import annotations

import json

from dopey_evolution.public_champion_hardening_repair_queue_v1 import run_public_champion_hardening_repair_queue_v1


def main() -> int:
    summary = run_public_champion_hardening_repair_queue_v1()
    print(json.dumps({
        "repair_queue_status": summary["repair_queue_status"],
        "repair_queue_count": summary["repair_queue_count"],
        "repair_type_counts": summary["repair_type_counts"],
        "summary_path": summary["artifact_paths"]["public_champion_hardening_repair_summary_v1"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
