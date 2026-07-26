"""CLI writer for the manual OHLCV manifest draft."""
from __future__ import annotations

import json

from .manual_ohlcv_manifest_draft import MANUAL_OHLCV_MANIFEST_DRAFT_PATH, write_manual_ohlcv_manifest_draft


def run_manual_ohlcv_manifest_draft() -> dict:
    return write_manual_ohlcv_manifest_draft()


def main() -> int:
    result = run_manual_ohlcv_manifest_draft()
    print(json.dumps({
        "draft_status": result["draft_status"],
        "hash_record_count": result["hash_record_count"],
        "real_data_files_present": result["real_data_files_present"],
        "manifest_draft_path": str(MANUAL_OHLCV_MANIFEST_DRAFT_PATH),
        "network_fetch_performed": result["network_fetch_performed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
