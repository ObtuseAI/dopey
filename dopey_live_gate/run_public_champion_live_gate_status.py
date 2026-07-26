"""CLI runner for public champion live-gate status."""
from __future__ import annotations

import json

from .public_champion_live_gate_status import run_public_champion_live_gate_status


def main() -> int:
    summary = run_public_champion_live_gate_status()
    print(json.dumps({
        "live_gate_status": summary["live_gate_status"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "summary_path": summary["artifact_paths"]["public_champion_live_gate_status"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
