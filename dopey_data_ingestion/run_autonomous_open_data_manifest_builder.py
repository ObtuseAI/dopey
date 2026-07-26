"""CLI runner for autonomous open-data manifest builder."""
from __future__ import annotations

import json

from .autonomous_open_data_manifest_builder import run_autonomous_open_data_manifest_builder


def main() -> int:
    result = run_autonomous_open_data_manifest_builder()
    print(json.dumps({
        "manifest_status": result["manifest_status"],
        "accepted_file_count": result["accepted_file_count"],
        "summary_path": result["artifact_paths"]["autonomous_open_data_manifest_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

