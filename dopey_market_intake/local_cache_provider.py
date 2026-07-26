"""Local public OHLCV cache provider."""
from __future__ import annotations

from pathlib import Path

from dopey_wealth_engine.common import DATA_ROOT, read_csv

from .public_ohlcv_provider_models import PublicFetchResult


CACHE_ROOT = DATA_ROOT / "market_lake" / "cache" / "public_ohlcv"
PUBLIC_DAILY_ROOT = DATA_ROOT / "market_lake" / "public" / "daily_ohlcv"


def fetch_local_cache_ohlcv(symbol: str) -> PublicFetchResult:
    candidates = sorted(CACHE_ROOT.glob(f"*/{symbol}.csv")) + [PUBLIC_DAILY_ROOT / f"{symbol}.csv"]
    for path in candidates:
        rows = read_csv(path)
        if rows:
            normalized = []
            for row in rows:
                normalized_row = dict(row)
                normalized_row["market_data_source_type"] = "public_cache"
                normalized.append(normalized_row)
            return {
                "provider": "local_cache",
                "symbol": symbol,
                "status": "ok",
                "rows": normalized,
                "attempted_url": str(path),
                "error": "",
                "response_status": None,
                "response_bytes": path.stat().st_size,
                "header_status": "csv_cache_ok",
                "empty_response": False,
                "package_import_status": "not_required",
                "market_data_source_type": "public_cache",
            }
    return {
        "provider": "local_cache",
        "symbol": symbol,
        "status": "cache_miss",
        "rows": [],
        "attempted_url": str(CACHE_ROOT),
        "error": "cache_miss",
        "response_status": None,
        "response_bytes": 0,
        "header_status": "cache_miss",
        "empty_response": True,
        "package_import_status": "not_required",
        "market_data_source_type": "public_cache",
    }
