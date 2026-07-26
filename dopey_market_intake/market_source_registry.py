"""Market source registry for no-key market vision intake."""
from __future__ import annotations

from dopey_wealth_engine.common import ARTIFACT_ROOT, stable_hash, write_jsonl


REGISTRY_PATH = ARTIFACT_ROOT / "market_intake" / "market_source_registry.jsonl"


def build_market_source_registry() -> list[dict]:
    sources = [
        _source("openbb", "openbb_provider_adapter", "optional local OpenBB adapter", False, False, False, False, "adapter_detection"),
        _source("yfinance", "python_package", "optional no-key Yahoo public market data", False, False, False, False, "ohlcv"),
        _source("stooq", "public_csv", "no-key public daily OHLCV CSV endpoint", False, False, False, False, "ohlcv"),
        _source("sec", "public_context", "SEC public company filing context", False, False, False, False, "context"),
        _source("fred", "public_macro", "public macro context if accessible without key", False, False, False, False, "context"),
        _source("local_cache", "local_files", "existing Dopey local market files", False, False, False, False, "ohlcv"),
        _source("fixture_fallback", "deterministic_fixture", "internal non-evidence fallback OHLCV", False, False, False, False, "ohlcv"),
        _source("alpha_vantage", "excluded", "forbidden in this bundle", True, False, False, False, "excluded"),
        _source("alpaca", "excluded", "broker/feed excluded in this bundle", True, True, False, True, "excluded"),
        _source("databento", "excluded", "paid/vendor feed excluded in this bundle", True, False, True, False, "excluded"),
        _source("tradingview", "excluded", "explicitly ignored in this bundle", True, False, False, False, "excluded"),
    ]
    write_jsonl(REGISTRY_PATH, sources, False)
    return sources


def _source(source_id: str, source_kind: str, description: str, excluded: bool, broker_adjacent: bool, paid: bool, credentials: bool, data_family: str) -> dict:
    record = {
        "artifact_type": "market_source_registry",
        "registry_version": "dopey-market-source-registry-v1",
        "source_id": source_id,
        "source_kind": source_kind,
        "description": description,
        "excluded": excluded,
        "broker_adjacent": broker_adjacent,
        "requires_payment": paid,
        "requires_credentials": credentials,
        "data_family": data_family,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record

