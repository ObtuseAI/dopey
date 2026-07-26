"""Corrected Stooq no-key CSV OHLCV provider with explicit non-CSV diagnostics."""
from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request

from dopey_wealth_engine.common import utc_now_iso

from .public_ohlcv_provider_models import PublicFetchResult


def stooq_symbol(symbol: str) -> str:
    return f"{symbol.lower()}.us"


def fetch_stooq_ohlcv_v2(symbol: str, timeout_seconds: int) -> PublicFetchResult:
    mapped = stooq_symbol(symbol)
    url = f"https://stooq.com/q/d/l/?s={mapped}&i=d"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Dopey public-no-key research"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body_bytes = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        return _empty(symbol, url, "http_error", f"HTTPError: {exc.code} {exc.reason}", exc.code, 0, "missing")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _empty(symbol, url, "fetch_failed", f"{type(exc).__name__}: {exc}", None, 0, "missing")
    if not body_bytes:
        return _empty(symbol, url, "empty_response", "empty_response", status, 0, "missing")
    body = body_bytes.decode("utf-8", errors="replace")
    rows, header_status = _parse_stooq_body(symbol, url, body)
    error = "" if rows else ("empty_response" if header_status == "empty_csv" else header_status)
    return {
        "provider": "stooq_v2",
        "symbol": symbol,
        "status": "ok" if rows else ("empty_response" if header_status == "empty_csv" else "non_csv_response"),
        "rows": rows,
        "attempted_url": url,
        "error": error,
        "response_status": status,
        "response_bytes": len(body_bytes),
        "header_status": header_status,
        "empty_response": not bool(rows) and header_status == "empty_csv",
        "package_import_status": "not_required",
        "market_data_source_type": "public_live_fetch",
    }


def _parse_stooq_body(symbol: str, source_url: str, body: str) -> tuple[list[dict], str]:
    first_line = body.splitlines()[0].strip() if body.splitlines() else ""
    if not first_line:
        return [], "empty_csv"
    if "Date,Open,High,Low,Close,Volume" not in first_line:
        if first_line.lower().startswith("<!doctype") or "<html" in first_line.lower():
            return [], "browser_verification_or_html"
        return [], "unexpected_header"
    reader = csv.DictReader(io.StringIO(body))
    fetch_timestamp = utc_now_iso()
    rows: list[dict] = []
    for row in reader:
        if not row.get("Date") or not row.get("Close") or str(row.get("Close")).lower() == "null":
            continue
        close_value = str(row["Close"])
        rows.append({
            "date": str(row["Date"])[:10],
            "open": str(row["Open"]),
            "high": str(row["High"]),
            "low": str(row["Low"]),
            "close": close_value,
            "adjusted_close": close_value,
            "volume": str(row["Volume"]),
            "provider": "stooq_v2",
            "source_url": source_url,
            "fetch_timestamp": fetch_timestamp,
            "adjustment_status": "adjusted_close_unavailable_close_used",
            "market_data_source_type": "public_live_fetch",
        })
    return rows, "csv_ok" if rows else "empty_csv"


def _empty(symbol: str, url: str, status: str, error: str, response_status: int | None, response_bytes: int, header_status: str) -> PublicFetchResult:
    return {
        "provider": "stooq_v2",
        "symbol": symbol,
        "status": status,
        "rows": [],
        "attempted_url": url,
        "error": error,
        "response_status": response_status,
        "response_bytes": response_bytes,
        "header_status": header_status,
        "empty_response": status == "empty_response",
        "package_import_status": "not_required",
        "market_data_source_type": "public_live_fetch",
    }
