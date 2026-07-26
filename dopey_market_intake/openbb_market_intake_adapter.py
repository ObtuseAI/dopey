"""OpenBB intake adapter detection for the wealth engine."""
from __future__ import annotations

import importlib.metadata
import importlib.util


def run_openbb_market_intake_adapter(symbols: list[str]) -> dict:
    spec = importlib.util.find_spec("openbb")
    available = spec is not None
    version = ""
    if available:
        try:
            version = importlib.metadata.version("openbb")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
    return {
        "adapter": "openbb",
        "status": "installed_adapter_ready_no_credential_fetch_skipped" if available else "not_installed_adapter_ready",
        "openbb_used": False,
        "openbb_import_available": available,
        "openbb_version": version,
        "symbols_requested": symbols,
        "records": [],
        "errors": [] if available else ["openbb_not_installed"],
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }

