"""Deterministic fixture generation for no-data wealth-engine fallback."""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

from .common import DATA_ROOT, stable_hash, write_csv, write_json, write_jsonl


DEFAULT_UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "NVDA", "AMD", "META", "GOOGL", "AMZN", "TSLA",
    "XLF", "XLK", "XLE", "XLV", "XLY", "XLI", "XLP", "XLU", "XLB", "XLRE",
]

OHLCV_FIELDS = ["date", "open", "high", "low", "close", "volume"]
FIXTURE_CASE_FAMILIES = [
    "data_intake", "charting", "indicator_engine", "aggressive_signals",
    "model_priced_options", "paper_tournament", "scoreboard", "risk_throttle",
    "winner_promotion", "loser_elimination", "live_gate", "no_data_fallback",
    "validation_stabilizer", "timeout_inconclusive",
]


def generate_fixture_ohlcv(symbol: str, day_count: int) -> list[dict]:
    start = date(2016, 1, 4)
    rows: list[dict] = []
    symbol_seed = sum(ord(char) for char in symbol)
    base = 45.0 + (symbol_seed % 180)
    price = base
    day_index = 0
    while len(rows) < day_count:
        current = start + timedelta(days=day_index)
        day_index += 1
        if current.weekday() >= 5:
            continue
        wave = math.sin((len(rows) + symbol_seed) / 13.0) * 0.014
        drift = ((symbol_seed % 11) - 5) * 0.00025 + 0.00055
        shock = math.sin((len(rows) + 3) / 37.0) * 0.006
        previous = price
        price = max(5.0, price * (1.0 + drift + wave + shock))
        high = max(previous, price) * (1.0 + 0.006 + abs(wave) * 0.4)
        low = min(previous, price) * (1.0 - 0.006 - abs(shock) * 0.3)
        rows.append({
            "date": current.isoformat(),
            "open": f"{previous:.4f}",
            "high": f"{high:.4f}",
            "low": f"{low:.4f}",
            "close": f"{price:.4f}",
            "volume": str(1_000_000 + (symbol_seed * 997 + len(rows) * 7919) % 9_000_000),
        })
    return rows


def ensure_wealth_engine_fixtures(fixtures_root: Path, minimum_cases: int) -> dict:
    fixtures_root.mkdir(parents=True, exist_ok=True)
    case_records: list[dict] = []
    for index in range(minimum_cases):
        family = FIXTURE_CASE_FAMILIES[index % len(FIXTURE_CASE_FAMILIES)]
        symbol = DEFAULT_UNIVERSE[index % len(DEFAULT_UNIVERSE)]
        record = {
            "artifact_type": "wealth_engine_fixture_case",
            "case_id": f"wealth-fixture-{index + 1:04d}",
            "family": family,
            "symbol": symbol,
            "expected_live_trading_enabled": False,
            "expected_broker_connection_used": False,
            "expected_credentials_created": False,
            "paper_only": True,
            "live_blocked": True,
        }
        record["case_hash"] = stable_hash(record)
        case_records.append(record)
    write_jsonl(fixtures_root / "wealth_engine_cases.jsonl", case_records, False)

    ohlcv_paths: list[str] = []
    for symbol in DEFAULT_UNIVERSE:
        rows = generate_fixture_ohlcv(symbol, 900)
        path = fixtures_root / "ohlcv" / f"{symbol}.csv"
        write_csv(path, rows, OHLCV_FIELDS)
        ohlcv_paths.append(str(path))

    summary = {
        "artifact_type": "wealth_engine_fixture_summary",
        "fixture_status": "complete",
        "case_count": len(case_records),
        "ohlcv_symbol_count": len(DEFAULT_UNIVERSE),
        "ohlcv_rows_per_symbol": 900,
        "fixture_root": str(fixtures_root),
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(fixtures_root / "wealth_engine_fixture_summary.json", summary)
    return {**summary, "ohlcv_paths": ohlcv_paths}

