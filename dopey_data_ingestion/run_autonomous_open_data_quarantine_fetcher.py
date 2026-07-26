"""CLI runner for autonomous open-data quarantine fetcher."""
from __future__ import annotations

import json

from .autonomous_open_data_quarantine_fetcher import run_autonomous_open_data_quarantine_fetcher


def main() -> int:
    result = run_autonomous_open_data_quarantine_fetcher()
    print(json.dumps({
        "fetch_status": result["fetch_status"],
        "fetch_attempt_count": result["fetch_attempt_count"],
        "fetch_success_count": result["fetch_success_count"],
        "summary_path": result["artifact_paths"]["open_data_quarantine_fetch_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

