"""CLI runner for repair live gate."""
from __future__ import annotations

import json

from dopey_live_gate.public_champion_repair_live_gate_status_v1 import run_public_champion_repair_live_gate_status_v1


def main() -> int:
    summary = run_public_champion_repair_live_gate_status_v1()
    print(json.dumps({
        "live_gate_status": summary["live_gate_status"],
        "retuned_hardened_count": summary["retuned_hardened_count"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "summary_path": summary["artifact_paths"]["public_champion_repair_live_gate_status_v1"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
