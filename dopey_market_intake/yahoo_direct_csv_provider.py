"""Yahoo direct no-key chart-query OHLCV provider."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from dopey_wealth_engine.common import utc_now_iso

from .public_ohlcv_provider_models import PublicFetchResult


def fetch_yahoo_direct_ohlcv(symbol: str, timeout_seconds: int) -> PublicFetchResult:
    period2 = int(time.time())
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?period1=0&period2={period2}&interval=1d&events=history&includeAdjustedClose=true"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Dopey public-no-key research"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        return _empty(symbol, url, "http_error", f"HTTPError: {exc.code} {exc.reason}", exc.code, 0, "missing")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _empty(symbol, url, "fetch_failed", f"{type(exc).__name__}: {exc}", None, 0, "missing")
    if not body:
        return _empty(symbol, url, "empty_response", "empty_response", status, 0, "missing")
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace"))
        result = parsed.get("chart", {}).get("result") or []
        if not result:
            error = parsed.get("chart", {}).get("error")
            return _empty(symbol, url, "no_chart_result", json.dumps(error, sort_keys=True), status, len(body), "json_no_result")
        payload = result[0]
        rows = _rows_from_payload(symbol, url, payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _empty(symbol, url, "parse_failed", f"{type(exc).__name__}: {exc}", status, len(body), "json_parse_failed")
    return {
        "provider": "yahoo_direct_csv",
        "symbol": symbol,
        "status": "ok" if rows else "empty_response",
        "rows": rows,
        "attempted_url": url,
        "error": "" if rows else "no_valid_rows",
        "response_status": status,
        "response_bytes": len(body),
        "header_status": "json_chart_ok" if rows else "json_no_valid_rows",
        "empty_response": not bool(rows),
        "package_import_status": "not_required",
        "market_data_source_type": "public_live_fetch",
    }


def _rows_from_payload(symbol: str, source_url: str, payload: dict) -> list[dict]:
    timestamps = payload.get("timestamp") or []
    indicators = payload.get("indicators", {})
    quote = (indicators.get("quote") or [{}])[0]
    adjclose_values = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    fetch_timestamp = utc_now_iso()
    rows: list[dict] = []
    for index, timestamp in enumerate(timestamps):
        if index >= min(len(opens), len(highs), len(lows), len(closes), len(volumes)):
            continue
        open_value = opens[index]
        high_value = highs[index]
        low_value = lows[index]
        close_value = closes[index]
        volume_value = volumes[index]
        if open_value is None or high_value is None or low_value is None or close_value is None or volume_value is None:
            continue
        adjusted_value = adjclose_values[index] if index < len(adjclose_values) and adjclose_values[index] is not None else close_value
        rows.append({
            "date": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat(),
            "open": f"{float(open_value):.6f}",
            "high": f"{float(high_value):.6f}",
            "low": f"{float(low_value):.6f}",
            "close": f"{float(close_value):.6f}",
            "adjusted_close": f"{float(adjusted_value):.6f}",
            "volume": str(int(float(volume_value))),
            "provider": "yahoo_direct_csv",
            "source_url": source_url,
            "fetch_timestamp": fetch_timestamp,
            "adjustment_status": "adjusted_close_available" if adjclose_values else "adjusted_close_unavailable_close_used",
            "market_data_source_type": "public_live_fetch",
        })
    return sorted(rows, key=lambda row: str(row["date"]))


def _empty(symbol: str, url: str, status: str, error: str, response_status: int | None, response_bytes: int, header_status: str) -> PublicFetchResult:
    return {
        "provider": "yahoo_direct_csv",
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
