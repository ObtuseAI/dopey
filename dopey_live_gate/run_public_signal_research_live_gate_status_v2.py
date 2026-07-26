"""CLI runner for public signal research live gate status V2."""
from __future__ import annotations

import json

from .public_signal_research_live_gate_status_v2 import run_public_signal_research_live_gate_status_v2


def main() -> int:
    summary = run_public_signal_research_live_gate_status_v2()
    print(json.dumps({
        "live_gate_status": summary["live_gate_status"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "watchlist_count": summary.get("watchlist_count", 0),
        "summary_path": summary["artifact_paths"]["public_signal_research_live_gate_status_v2"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
