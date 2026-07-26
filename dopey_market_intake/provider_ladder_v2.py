"""Public no-key OHLCV provider ladder V2."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from dopey_runtime_bootstrap.venv_package_import_audit import repo_venv_import_status
from dopey_wealth_engine.common import ARTIFACT_ROOT, DATA_ROOT, proof_record, stable_hash, write_csv, write_json, write_jsonl
from dopey_wealth_engine.fixtures import generate_fixture_ohlcv

from .local_cache_provider import CACHE_ROOT, PUBLIC_DAILY_ROOT, fetch_local_cache_ohlcv
from .pandas_datareader_provider import fetch_pandas_datareader_ohlcv
from .public_ohlcv_provider_models import PRIMARY_UNIVERSE, PROVIDER_ORDER, PUBLIC_OHLCV_FIELDS, PublicFetchResult
from .stooq_ohlcv_provider_v2 import fetch_stooq_ohlcv_v2
from .yahoo_direct_csv_provider import fetch_yahoo_direct_ohlcv
from .yahooquery_ohlcv_provider import fetch_yahooquery_ohlcv
from .yfinance_ohlcv_provider import fetch_yfinance_ohlcv


ARTIFACT_DIR = ARTIFACT_ROOT / "market_intake"
REGISTRY_PATH = ARTIFACT_DIR / "public_ohlcv_provider_registry_v2.jsonl"
ATTEMPTS_PATH = ARTIFACT_DIR / "public_ohlcv_fetch_attempts_v2.jsonl"
SUCCESSES_PATH = ARTIFACT_DIR / "public_ohlcv_fetch_successes_v2.jsonl"
FAILURES_PATH = ARTIFACT_DIR / "public_ohlcv_fetch_failures_v2.jsonl"
CACHE_MANIFEST_PATH = ARTIFACT_DIR / "public_ohlcv_cache_manifest_v2.json"
SUMMARY_PATH = ARTIFACT_DIR / "public_ohlcv_provider_ladder_v2_summary.json"
PROOF_PATH = ARTIFACT_DIR / "public_ohlcv_provider_ladder_v2_proof.jsonl"


def run_public_ohlcv_provider_ladder_v2(symbols: list[str], use_fixture_fallback: bool, timeout_seconds: int) -> dict:
    registry = _registry()
    attempts: list[dict] = []
    successes: list[dict] = []
    failures: list[dict] = []
    best_provider_by_symbol: dict[str, str] = {}
    loaded_symbols: list[str] = []
    total_rows = 0
    provider_success_counts: Counter[str] = Counter()
    provider_failure_counts: Counter[str] = Counter()
    for symbol in symbols:
        symbol_loaded = False
        for provider in PROVIDER_ORDER:
            result = _fetch(provider, symbol, timeout_seconds)
            attempt = _attempt_record(result)
            attempts.append(attempt)
            if result["rows"]:
                rows = _valid_rows(result["rows"])
                if rows:
                    _write_public_rows(provider, symbol, rows)
                    success = _success_record(result, rows)
                    successes.append(success)
                    provider_success_counts[provider] += 1
                    best_provider_by_symbol[symbol] = provider
                    loaded_symbols.append(symbol)
                    total_rows += len(rows)
                    symbol_loaded = True
                    break
            failure = _failure_record(result)
            failures.append(failure)
            provider_failure_counts[provider] += 1
        if not symbol_loaded and use_fixture_fallback:
            rows = _fixture_rows(symbol)
            _write_fixture_rows(symbol, rows)
    primary_loaded = len([symbol for symbol in PRIMARY_UNIVERSE if symbol in set(loaded_symbols)])
    status = _ladder_status(primary_loaded, len(loaded_symbols), total_rows)
    used_fixture_fallback = use_fixture_fallback and not loaded_symbols
    cache_manifest = _cache_manifest(successes)
    summary = {
        "artifact_type": "public_ohlcv_provider_ladder_v2_summary",
        "provider_ladder_version": "dopey-public-ohlcv-provider-ladder-v2",
        "provider_ladder_status": status,
        "providers_attempted": sorted({record["provider"] for record in attempts}),
        "providers_successful": sorted({record["provider"] for record in successes}),
        "symbols_attempted": symbols,
        "symbols_loaded": loaded_symbols,
        "symbol_success_count": len(loaded_symbols),
        "symbol_failure_count": len(symbols) - len(loaded_symbols),
        "public_ohlcv_rows_loaded": total_rows,
        "public_ohlcv_file_count": len(successes),
        "date_range": _date_range_from_successes(successes),
        "best_provider_by_symbol": best_provider_by_symbol,
        "provider_success_counts": dict(sorted(provider_success_counts.items())),
        "provider_failure_counts": dict(sorted(provider_failure_counts.items())),
        "used_fixture_fallback": used_fixture_fallback,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(REGISTRY_PATH, registry, False)
    write_jsonl(ATTEMPTS_PATH, attempts, False)
    write_jsonl(SUCCESSES_PATH, successes, False)
    write_jsonl(FAILURES_PATH, failures, False)
    write_json(CACHE_MANIFEST_PATH, cache_manifest)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("public-ohlcv-provider-ladder-v2", status, summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def _fetch(provider: str, symbol: str, timeout_seconds: int) -> PublicFetchResult:
    if provider == "local_cache":
        return fetch_local_cache_ohlcv(symbol)
    if provider == "yfinance":
        return fetch_yfinance_ohlcv(symbol, timeout_seconds)
    if provider == "yahooquery":
        return fetch_yahooquery_ohlcv(symbol, timeout_seconds)
    if provider == "yahoo_direct_csv":
        return fetch_yahoo_direct_ohlcv(symbol, timeout_seconds)
    if provider == "stooq_v2":
        return fetch_stooq_ohlcv_v2(symbol, timeout_seconds)
    if provider == "pandas_datareader":
        return fetch_pandas_datareader_ohlcv(symbol, timeout_seconds)
    return _openbb_skipped(symbol)


def _openbb_skipped(symbol: str) -> PublicFetchResult:
    import_status = repo_venv_import_status(5).get("openbb", "missing")
    return {
        "provider": "openbb",
        "symbol": symbol,
        "status": "missing_package" if import_status != "importable" else "skipped_no_key_route_not_configured",
        "rows": [],
        "attempted_url": "openbb optional no-key route",
        "error": import_status,
        "response_status": None,
        "response_bytes": 0,
        "header_status": import_status,
        "empty_response": True,
        "package_import_status": import_status,
        "market_data_source_type": "public_live_fetch",
    }


def _valid_rows(rows: list[dict]) -> list[dict]:
    valid: list[dict] = []
    for row in rows:
        try:
            if min(float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])) <= 0:
                continue
            int(float(row["volume"]))
        except (KeyError, TypeError, ValueError):
            continue
        valid.append(row)
    return valid


def _write_public_rows(provider: str, symbol: str, rows: list[dict]) -> None:
    write_csv(CACHE_ROOT / provider / f"{symbol}.csv", rows, PUBLIC_OHLCV_FIELDS)
    write_csv(PUBLIC_DAILY_ROOT / f"{symbol}.csv", rows, PUBLIC_OHLCV_FIELDS)


def _write_fixture_rows(symbol: str, rows: list[dict]) -> None:
    write_csv(DATA_ROOT / "market_lake" / "fixture_fallback" / "daily_ohlcv" / f"{symbol}.csv", rows, ["date", "open", "high", "low", "close", "volume"])


def _fixture_rows(symbol: str) -> list[dict]:
    return generate_fixture_ohlcv(symbol, 900)


def _attempt_record(result: PublicFetchResult) -> dict:
    record = {
        "artifact_type": "public_ohlcv_fetch_attempt_v2",
        "provider": result["provider"],
        "symbol": result["symbol"],
        "status": result["status"],
        "attempted_url": result["attempted_url"],
        "response_status": result["response_status"],
        "response_bytes": result["response_bytes"],
        "header_status": result["header_status"],
        "row_count": len(result["rows"]),
        "package_import_status": result["package_import_status"],
        "empty_response": result["empty_response"],
        "market_data_source_type": result["market_data_source_type"],
    }
    record["record_hash"] = stable_hash(record)
    return record


def _success_record(result: PublicFetchResult, rows: list[dict]) -> dict:
    record = {
        "artifact_type": "public_ohlcv_fetch_success_v2",
        "provider": result["provider"],
        "symbol": result["symbol"],
        "row_count": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "normalized_path": str(PUBLIC_DAILY_ROOT / f"{result['symbol']}.csv"),
        "cache_path": str(CACHE_ROOT / result["provider"] / f"{result['symbol']}.csv"),
        "market_data_source_type": result["market_data_source_type"],
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _failure_record(result: PublicFetchResult) -> dict:
    record = {
        "artifact_type": "public_ohlcv_fetch_failure_v2",
        "provider": result["provider"],
        "symbol": result["symbol"],
        "status": result["status"],
        "attempted_url": result["attempted_url"],
        "error": result["error"],
        "response_status": result["response_status"],
        "response_bytes": result["response_bytes"],
        "header_status": result["header_status"],
        "empty_response": result["empty_response"],
        "package_import_status": result["package_import_status"],
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _registry() -> list[dict]:
    records: list[dict] = []
    for provider in PROVIDER_ORDER:
        record = {
            "artifact_type": "public_ohlcv_provider_registry_v2",
            "provider": provider,
            "provider_type": "local_cache" if provider == "local_cache" else "public_no_key",
            "credential_required": False,
            "broker_provider": False,
            "live_trading_enabled": False,
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
    return records


def _ladder_status(primary_loaded: int, loaded_count: int, total_rows: int) -> str:
    if primary_loaded >= len(PRIMARY_UNIVERSE):
        return "public_ohlcv_loaded_primary_universe"
    if primary_loaded >= 5 and total_rows >= 2_500:
        return "public_ohlcv_loaded_minimum_viable"
    if loaded_count > 0:
        return "public_ohlcv_loaded_partial_universe"
    return "public_ohlcv_failed_all_routes_fixture_fallback_only"


def _date_range_from_successes(successes: list[dict]) -> dict:
    dates: list[str] = []
    for record in successes:
        dates.append(str(record["first_date"]))
        dates.append(str(record["last_date"]))
    return {"start": min(dates) if dates else "", "end": max(dates) if dates else ""}


def _cache_manifest(successes: list[dict]) -> dict:
    files: list[dict] = []
    for record in successes:
        path = Path(str(record["cache_path"]))
        files.append({
            "symbol": record["symbol"],
            "provider": record["provider"],
            "path": str(path),
            "row_count": record["row_count"],
            "first_date": record["first_date"],
            "last_date": record["last_date"],
            "exists": path.exists(),
        })
    manifest = {
        "artifact_type": "public_ohlcv_cache_manifest_v2",
        "cache_file_count": len(files),
        "files": files,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    return manifest


def artifact_paths() -> dict[str, str]:
    return {
        "public_ohlcv_provider_registry_v2": str(REGISTRY_PATH),
        "public_ohlcv_fetch_attempts_v2": str(ATTEMPTS_PATH),
        "public_ohlcv_fetch_successes_v2": str(SUCCESSES_PATH),
        "public_ohlcv_fetch_failures_v2": str(FAILURES_PATH),
        "public_ohlcv_cache_manifest_v2": str(CACHE_MANIFEST_PATH),
        "public_ohlcv_provider_ladder_v2_summary": str(SUMMARY_PATH),
        "public_ohlcv_provider_ladder_v2_proof": str(PROOF_PATH),
    }
