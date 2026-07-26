"""CLI runner for public signal research V2 preflight."""
from __future__ import annotations

import json

from .public_signal_research_v2_preflight import run_public_signal_research_v2_preflight


def main() -> int:
    summary = run_public_signal_research_v2_preflight()
    print(json.dumps({
        "public_signal_research_v2_preflight_status": summary["public_signal_research_v2_preflight_status"],
        "v1_watchlist_count": summary.get("v1_watchlist_count", 0),
        "summary_path": summary["artifact_paths"]["public_signal_research_v2_preflight_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
