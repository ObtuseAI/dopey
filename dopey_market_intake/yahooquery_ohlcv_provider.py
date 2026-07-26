"""yahooquery package OHLCV provider through the repo venv."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from dopey_runtime_bootstrap.active_python_resolver import preferred_repo_python
from dopey_runtime_bootstrap.venv_package_import_audit import audit_imports_for_python
from dopey_wealth_engine.common import REPO_ROOT, read_csv, utc_now_iso

from .public_ohlcv_provider_models import PublicFetchResult


_PACKAGE_STATUS_CACHE: dict[str, str] = {}


def fetch_yahooquery_ohlcv(symbol: str, timeout_seconds: int) -> PublicFetchResult:
    import_status = _package_status("yahooquery")
    if import_status != "importable":
        return _empty(symbol, "missing_package", "missing_package", import_status)
    with tempfile.TemporaryDirectory(prefix="dopey_yahooquery_") as temp_dir:
        output_path = Path(temp_dir) / f"{symbol}.csv"
        script = (
            "from yahooquery import Ticker; "
            f"df=Ticker({symbol!r}, asynchronous=False).history(period='max', interval='1d'); "
            "df=df.reset_index(); "
            f"df.to_csv({str(output_path)!r}, index=False)"
        )
        try:
            completed = subprocess.run([str(preferred_repo_python()), "-c", script], cwd=str(REPO_ROOT), text=True, capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            return _empty(symbol, "Ticker.history(period=max)", "timeout", f"TimeoutExpired: {exc}")
        except OSError as exc:
            return _empty(symbol, "Ticker.history(period=max)", "fetch_failed", f"{type(exc).__name__}: {exc}")
        if completed.returncode != 0:
            return _empty(symbol, "Ticker.history(period=max)", "fetch_failed", completed.stderr[-500:])
        rows = _normalize_rows(symbol, "yahooquery.Ticker.history(period=max)", read_csv(output_path))
        return {
            "provider": "yahooquery",
            "symbol": symbol,
            "status": "ok" if rows else "empty_response",
            "rows": rows,
            "attempted_url": "yahooquery.Ticker.history(period=max, interval=1d)",
            "error": "" if rows else "empty_response",
            "response_status": None,
            "response_bytes": output_path.stat().st_size if output_path.exists() else 0,
            "header_status": "package_csv_ok" if rows else "package_empty",
            "empty_response": not bool(rows),
            "package_import_status": import_status,
            "market_data_source_type": "public_live_fetch",
        }


def _normalize_rows(symbol: str, source_url: str, rows: list[dict]) -> list[dict]:
    fetch_timestamp = utc_now_iso()
    normalized: list[dict] = []
    for row in rows:
        close = row.get("close") or row.get("Close")
        date_value = row.get("date") or row.get("Date")
        if not date_value or not close:
            continue
        adjusted = row.get("adjclose") or row.get("adj_close") or close
        normalized.append({
            "date": str(date_value)[:10],
            "open": str(row.get("open") or row.get("Open")),
            "high": str(row.get("high") or row.get("High")),
            "low": str(row.get("low") or row.get("Low")),
            "close": str(close),
            "adjusted_close": str(adjusted),
            "volume": str(row.get("volume") or row.get("Volume") or "0"),
            "provider": "yahooquery",
            "source_url": source_url,
            "fetch_timestamp": fetch_timestamp,
            "adjustment_status": "adjusted_close_available" if adjusted != close else "adjusted_close_unavailable_close_used",
            "market_data_source_type": "public_live_fetch",
        })
    return sorted(normalized, key=lambda row: str(row["date"]))


def _package_status(package: str) -> str:
    if package in _PACKAGE_STATUS_CACHE:
        return _PACKAGE_STATUS_CACHE[package]
    records = audit_imports_for_python(preferred_repo_python(), [package], 5)
    status = str(records[0]["import_status"]) if records else "missing"
    _PACKAGE_STATUS_CACHE[package] = status
    return status


def _empty(symbol: str, attempted_url: str, status: str, error: str) -> PublicFetchResult:
    return {
        "provider": "yahooquery",
        "symbol": symbol,
        "status": status,
        "rows": [],
        "attempted_url": attempted_url,
        "error": error,
        "response_status": None,
        "response_bytes": 0,
        "header_status": status,
        "empty_response": status == "empty_response",
        "package_import_status": error if status == "missing_package" else "importable",
        "market_data_source_type": "public_live_fetch",
    }
