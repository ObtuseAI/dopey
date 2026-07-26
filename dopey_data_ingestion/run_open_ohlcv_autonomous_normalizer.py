"""CLI runner for breakthrough OHLCV normalizer."""
from __future__ import annotations

import json

from .open_ohlcv_autonomous_normalizer import run_open_ohlcv_autonomous_normalizer


def main() -> int:
    result = run_open_ohlcv_autonomous_normalizer()
    print(json.dumps({
        "open_ohlcv_normalization_status": result["open_ohlcv_normalization_status"],
        "normalized_ohlcv_file_count": result["normalized_ohlcv_file_count"],
        "summary_path": result["artifact_paths"]["open_ohlcv_normalization_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

