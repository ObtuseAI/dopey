"""CLI runner for public champion risk engine V3."""
from __future__ import annotations

import json

from .public_champion_risk_engine_v3 import run_public_champion_risk_engine_v3


def main() -> int:
    summary = run_public_champion_risk_engine_v3()
    print(json.dumps({
        "public_champion_risk_status": summary["public_champion_risk_status"],
        "risk_throttle_count": summary["risk_throttle_count"],
        "kill_switch_record_count": summary["kill_switch_record_count"],
        "summary_path": summary["artifact_paths"]["public_champion_risk_summary_v3"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
