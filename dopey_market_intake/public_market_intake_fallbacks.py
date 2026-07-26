"""No-key public and deterministic fallback market data intake."""
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from dopey_wealth_engine.common import read_csv
from dopey_wealth_engine.fixtures import generate_fixture_ohlcv


def fetch_stooq_daily(symbol: str, timeout_seconds: int) -> dict:
    stooq_symbol = f"{symbol.lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "dopey-wealth-engine/1.0"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"source": "stooq", "symbol": symbol, "status": "fetch_failed", "rows": [], "error": f"{type(exc).__name__}: {exc}"}
    rows = _parse_stooq_csv(body)
    return {"source": "stooq", "symbol": symbol, "status": "ok" if rows else "empty", "rows": rows, "error": ""}


def load_local_fixture_daily(symbol: str, fixture_path: Path) -> dict:
    rows = read_csv(fixture_path)
    if not rows:
        rows = generate_fixture_ohlcv(symbol, 900)
    return {"source": "fixture_fallback", "symbol": symbol, "status": "ok", "rows": rows, "error": ""}


def _parse_stooq_csv(body: str) -> list[dict]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    rows: list[dict] = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) != 6:
            continue
        date_value, open_value, high_value, low_value, close_value, volume_value = parts
        if close_value.lower() == "null":
            continue
        rows.append({
            "date": date_value,
            "open": open_value,
            "high": high_value,
            "low": low_value,
            "close": close_value,
            "volume": volume_value,
        })
    return rows

