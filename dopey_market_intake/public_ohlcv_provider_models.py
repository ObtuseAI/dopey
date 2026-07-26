"""Models and constants for the public no-key OHLCV provider ladder V2."""
from __future__ import annotations

from typing import TypedDict


PRIMARY_UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "NVDA", "AMD", "META", "GOOGL", "AMZN", "TSLA",
    "XLF", "XLK", "XLE", "XLV", "XLY", "XLI", "XLP", "XLU", "XLB", "XLRE",
]

SECONDARY_EXPANSION_UNIVERSE = [
    "JPM", "BAC", "C", "GS", "MS",
    "NFLX", "AVGO", "SMCI", "INTC", "MU",
    "V", "MA", "COST", "WMT", "HD",
    "TLT", "HYG", "LQD", "GLD", "SLV", "USO",
    "UNH", "LLY", "JNJ", "MRK", "PFE",
    "CAT", "DE", "BA", "GE", "RTX",
    "CVX", "COP", "SLB", "OXY", "MPC",
]

PUBLIC_OHLCV_FIELDS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "provider",
    "source_url",
    "fetch_timestamp",
    "adjustment_status",
    "market_data_source_type",
]

PROVIDER_ORDER = [
    "local_cache",
    "yfinance",
    "yahooquery",
    "yahoo_direct_csv",
    "stooq_v2",
    "pandas_datareader",
    "openbb",
]


class PublicFetchResult(TypedDict):
    provider: str
    symbol: str
    status: str
    rows: list[dict]
    attempted_url: str
    error: str
    response_status: int | None
    response_bytes: int
    header_status: str
    empty_response: bool
    package_import_status: str
    market_data_source_type: str
