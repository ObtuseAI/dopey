"""CLI runner for autonomous open OHLCV normalization."""
from __future__ import annotations

import json

from .autonomous_open_ohlcv_normalizer import run_autonomous_open_ohlcv_normalizer


def main() -> int:
    result = run_autonomous_open_ohlcv_normalizer()
    print(json.dumps({
        "normalization_status": result["normalization_status"],
        "accepted_ohlcv_file_count": result["accepted_ohlcv_file_count"],
        "summary_path": result["artifact_paths"]["open_ohlcv_normalization_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

