"""CLI runner for public signal research live gate status V4."""
from __future__ import annotations

import json

from dopey_live_gate.public_signal_research_live_gate_status_v4 import run_public_signal_research_live_gate_status_v4


def main() -> int:
    summary = run_public_signal_research_live_gate_status_v4()
    print(
        json.dumps(
            {
                "live_gate_status": summary["live_gate_status"],
                "watchlist_count": summary.get("watchlist_count", 0),
                "summary_path": summary["artifact_paths"]["public_signal_research_live_gate_status_v4"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
