"""CLI runner for breakthrough quarantine downloader."""
from __future__ import annotations

import json

from .open_data_breakthrough_quarantine_downloader import run_open_data_breakthrough_quarantine_downloader


def main() -> int:
    result = run_open_data_breakthrough_quarantine_downloader()
    print(json.dumps({
        "download_status": result["download_status"],
        "download_attempt_count": result["download_attempt_count"],
        "download_success_count": result["download_success_count"],
        "summary_path": result["artifact_paths"]["quarantine_download_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

