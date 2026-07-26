"""CLI runner for autonomous open-data source discovery."""
from __future__ import annotations

import json

from .autonomous_open_data_source_discovery import run_autonomous_open_data_source_discovery


def main() -> int:
    result = run_autonomous_open_data_source_discovery()
    print(json.dumps({
        "open_data_candidate_count": result["open_data_candidate_count"],
        "open_data_accepted_count": result["open_data_accepted_count"],
        "accepted_ingest_source_count": result["accepted_ingest_source_count"],
        "summary_path": result["artifact_paths"]["autonomous_open_data_source_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

