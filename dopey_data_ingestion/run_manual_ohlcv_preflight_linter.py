"""CLI writer for the manual OHLCV preflight linter."""
from __future__ import annotations

import json

from .manual_ohlcv_preflight_linter import MANUAL_OHLCV_PREFLIGHT_SUMMARY_PATH, write_manual_ohlcv_preflight


def run_manual_ohlcv_preflight_linter() -> dict:
    return write_manual_ohlcv_preflight()


def main() -> int:
    result = run_manual_ohlcv_preflight_linter()
    print(json.dumps({
        "preflight_status": result["preflight_status"],
        "file_count": result["file_count"],
        "preflight_failure_count": result["preflight_failure_count"],
        "summary_path": str(MANUAL_OHLCV_PREFLIGHT_SUMMARY_PATH),
        "network_fetch_performed": result["network_fetch_performed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
