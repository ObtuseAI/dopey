"""CLI runner for public OHLCV cache persistence."""
from __future__ import annotations

import json

from .market_data_cache_manager import run_market_data_cache_manager


def main() -> int:
    summary = run_market_data_cache_manager(14)
    print(json.dumps({
        "market_data_cache_status": summary["market_data_cache_status"],
        "cache_file_count": summary["cache_file_count"],
        "cache_symbol_count": summary["cache_symbol_count"],
        "cache_rows": summary["cache_rows"],
        "summary_path": summary["artifact_paths"]["market_data_cache_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
