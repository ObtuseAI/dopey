"""CLI runner for breakthrough manifest builder."""
from __future__ import annotations

import json

from .open_data_breakthrough_manifest_builder import run_open_data_breakthrough_manifest_builder


def main() -> int:
    result = run_open_data_breakthrough_manifest_builder()
    print(json.dumps({
        "manifest_status": result["manifest_status"],
        "accepted_ohlcv_file_count": result["accepted_ohlcv_file_count"],
        "accepted_options_file_count": result["accepted_options_file_count"],
        "summary_path": result["artifact_paths"]["open_data_evidence_manifest_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

