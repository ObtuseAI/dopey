"""CLI runner for the DOPEY market data lake builder."""
from __future__ import annotations

import json

from .market_data_lake_builder import run_market_data_lake_builder


def main() -> int:
    summary = run_market_data_lake_builder(True, True)
    print(json.dumps({
        "market_data_status": summary["market_data_status"],
        "symbols_fetched": summary["symbols_fetched"],
        "daily_ohlcv_rows": summary["daily_ohlcv_rows"],
        "openbb_status": summary["openbb_status"],
        "yfinance_status": summary["yfinance_status"],
        "summary_path": summary["artifact_paths"]["market_data_lake_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
