"""Optional yfinance adapter for no-key OHLCV intake."""
from __future__ import annotations

import importlib.util


def run_yfinance_market_intake_adapter(symbols: list[str]) -> dict:
    if importlib.util.find_spec("yfinance") is None:
        return {
            "adapter": "yfinance",
            "status": "not_installed_fallback_required",
            "yfinance_used": False,
            "symbols_requested": symbols,
            "records": [],
            "errors": ["yfinance_not_installed"],
            "credentials_created": False,
            "env_created": False,
            "broker_connection_used": False,
            "live_trading_enabled": False,
        }
    return {
        "adapter": "yfinance",
        "status": "installed_not_used_by_stdlib_runner",
        "yfinance_used": False,
        "symbols_requested": symbols,
        "records": [],
        "errors": ["stdlib_runner_prefers_direct_public_csv_to_avoid_optional_dependency_runtime"],
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }

