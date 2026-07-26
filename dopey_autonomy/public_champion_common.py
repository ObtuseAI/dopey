"""Shared helpers for the public-market paper champion evolution bundle."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from dopey_wealth_engine.common import ARTIFACT_ROOT, DATA_ROOT, stable_hash


PUBLIC_SOURCE_TYPES = frozenset({"public_live_fetch", "public_cache"})
TEST_SYMBOL_PREFIXES = ("SIM", "TEST", "FIXTURE", "SYNTH")
BUNDLE_VERSION = "dopey-public-market-paper-champion-evolution-v1"

PUBLIC_CHAMPION_ROOT = ARTIFACT_ROOT / "public_champion_evolution"
CHAMPION_ROOT = ARTIFACT_ROOT / "champions"
SCOREBOARD_ROOT = ARTIFACT_ROOT / "scoreboard"
SIGNAL_ROOT = ARTIFACT_ROOT / "signals"
OPTIONS_ENGINE_ROOT = ARTIFACT_ROOT / "options_engine"
TOURNAMENT_ROOT = ARTIFACT_ROOT / "tournament"
RISK_ROOT = ARTIFACT_ROOT / "risk"
EVOLUTION_ROOT = ARTIFACT_ROOT / "evolution"
LIVE_GATE_ROOT = ARTIFACT_ROOT / "live_gate"

MANIFEST_PATH = DATA_ROOT / "market_lake" / "manifests" / "market_lake_manifest.json"
PUBLIC_DAILY_ROOT = DATA_ROOT / "market_lake" / "public" / "daily_ohlcv"
ACTIVE_DAILY_ROOT = DATA_ROOT / "market_lake" / "active" / "daily_ohlcv"
CACHE_ROOT = DATA_ROOT / "market_lake" / "cache" / "public_ohlcv"

OHLCV_FIELDNAMES = [
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

SECTOR_BY_SYMBOL = {
    "SPY": "broad_etf",
    "QQQ": "broad_etf",
    "IWM": "broad_etf",
    "DIA": "broad_etf",
    "XLK": "technology",
    "XLF": "financials",
    "XLE": "energy",
    "XLV": "healthcare",
    "XLY": "consumer_discretionary",
    "XLP": "consumer_staples",
    "XLI": "industrials",
    "XLU": "utilities",
    "XLB": "materials",
    "XLRE": "real_estate",
    "TLT": "rates_proxy",
    "IEF": "rates_proxy",
    "SHY": "rates_proxy",
    "HYG": "credit_proxy",
    "LQD": "credit_proxy",
    "GLD": "commodity_proxy",
    "SLV": "commodity_proxy",
    "USO": "energy",
    "EEM": "intl_equity",
    "EFA": "intl_equity",
    "SMH": "semiconductors",
    "XBI": "healthcare",
    "ARKK": "technology",
    "XLC": "communications",
    "AAPL": "technology",
    "MSFT": "technology",
    "NVDA": "semiconductors",
    "AMD": "semiconductors",
    "AVGO": "semiconductors",
    "SMCI": "ai_infrastructure",
    "INTC": "semiconductors",
    "MU": "semiconductors",
    "META": "technology",
    "GOOGL": "technology",
    "AMZN": "consumer_discretionary",
    "TSLA": "consumer_discretionary",
    "JPM": "financials",
    "BAC": "financials",
    "C": "financials",
    "GS": "financials",
    "MS": "financials",
    "V": "financials",
    "MA": "financials",
    "COST": "consumer_staples",
    "WMT": "consumer_staples",
    "HD": "consumer_discretionary",
    "UNH": "healthcare",
    "LLY": "healthcare",
    "JNJ": "healthcare",
    "MRK": "healthcare",
    "PFE": "healthcare",
    "CAT": "industrials",
    "DE": "industrials",
    "BA": "defense_aerospace",
    "GE": "industrials",
    "RTX": "defense_aerospace",
    "CVX": "energy",
    "COP": "energy",
    "SLB": "energy",
    "OXY": "energy",
    "MPC": "energy",
    "CRM": "software",
    "NOW": "software",
    "ADBE": "software",
    "ORCL": "software",
    "SNOW": "cloud",
    "DDOG": "cloud",
    "NET": "cloud",
    "CRWD": "cyber",
    "PANW": "cyber",
    "FTNT": "cyber",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed
    return {"records": parsed}


def write_json_file(path: Path, record: Mapping[str, object]) -> Path:
    ensure_parent(path)
    path.write_text(json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def read_jsonl_file(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                records.append(parsed)
    return records


def write_jsonl_file(path: Path, records: Iterable[Mapping[str, object]]) -> Path:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")
    return path


def read_csv_file(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_file(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> Path:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def record_with_hash(record: Mapping[str, object], field_name: str) -> dict[str, object]:
    output = dict(record)
    output[field_name] = stable_hash(output)
    return output


def proof_record(proof_id: str, status: str, payload: Mapping[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "public_champion_evolution_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "bundle_version": BUNDLE_VERSION,
        "payload": dict(payload),
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "real_orders_placed": False,
        "live_trading_enabled": False,
    }
    return record_with_hash(record, "proof_hash")


def safe_float(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isfinite(parsed):
        return parsed
    return 0.0


def safe_int(value: object) -> int:
    try:
        parsed = int(float(str(value)))
    except (TypeError, ValueError):
        return 0
    return parsed


def active_manifest() -> dict[str, object]:
    return read_json_file(MANIFEST_PATH)


def manifest_files() -> list[dict[str, object]]:
    manifest = active_manifest()
    files = manifest.get("files", [])
    if not isinstance(files, list):
        return []
    return [file_record for file_record in files if isinstance(file_record, dict)]


def public_manifest_files() -> list[dict[str, object]]:
    return [
        record for record in manifest_files()
        if str(record.get("market_data_source_type", "")) in PUBLIC_SOURCE_TYPES
    ]


def fixture_manifest_files() -> list[dict[str, object]]:
    return [
        record for record in manifest_files()
        if str(record.get("market_data_source_type", "")) == "fixture_fallback"
    ]


def is_test_symbol(symbol: str) -> bool:
    normalized = symbol.upper()
    return any(normalized.startswith(prefix) for prefix in TEST_SYMBOL_PREFIXES)


def load_rows_for_file_record(file_record: Mapping[str, object]) -> list[dict[str, str]]:
    path_value = str(file_record.get("active_path") or file_record.get("path") or "")
    if not path_value:
        return []
    return sanitize_ohlcv_rows(read_csv_file(Path(path_value)))


def sanitize_ohlcv_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for row in rows:
        date_value = str(row.get("date", ""))[:10]
        open_value = safe_float(row.get("open"))
        high_value = safe_float(row.get("high"))
        low_value = safe_float(row.get("low"))
        close_value = safe_float(row.get("close"))
        if not date_value or min(open_value, high_value, low_value, close_value) <= 0.0:
            continue
        cleaned.append({
            "date": date_value,
            "open": str(open_value),
            "high": str(high_value),
            "low": str(low_value),
            "close": str(close_value),
            "adjusted_close": str(safe_float(row.get("adjusted_close")) or close_value),
            "volume": str(safe_int(row.get("volume"))),
            "provider": str(row.get("provider", "")),
            "source_url": str(row.get("source_url", "")),
            "fetch_timestamp": str(row.get("fetch_timestamp", "")),
            "adjustment_status": str(row.get("adjustment_status", "")),
            "market_data_source_type": str(row.get("market_data_source_type", "")),
        })
    return sorted(cleaned, key=lambda item: item["date"])


def active_rows_by_symbol() -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for file_record in public_manifest_files():
        symbol = str(file_record.get("symbol", ""))
        rows = load_rows_for_file_record(file_record)
        if symbol and rows:
            grouped[symbol] = rows
    return grouped


def sector_for_symbol(symbol: str) -> str:
    return SECTOR_BY_SYMBOL.get(symbol.upper(), "other")


def provider_from_rows(rows: Sequence[Mapping[str, object]]) -> str:
    for row in rows:
        provider = str(row.get("provider", "")).strip()
        if provider:
            return provider
    return "manifest"


def date_from_text(value: object) -> date:
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return date(1970, 1, 1)


def pct_return(start_value: float, end_value: float) -> float:
    if start_value <= 0.0:
        return 0.0
    return (end_value / start_value) - 1.0


def rolling_mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def rolling_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = rolling_mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(variance, 0.0))


def realized_volatility(closes: Sequence[float]) -> float:
    if len(closes) < 3:
        return 0.25
    returns: list[float] = []
    previous = closes[0]
    for close in closes[1:]:
        if previous > 0.0 and close > 0.0:
            returns.append(math.log(close / previous))
        previous = close
    vol = rolling_std(returns) * math.sqrt(252.0)
    return min(max(vol, 0.08), 1.80)


def max_drawdown(pnl_values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for pnl in pnl_values:
        equity += pnl
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return round(worst, 6)


def profit_factor(pnl_values: Sequence[float]) -> float:
    gains = sum(value for value in pnl_values if value > 0.0)
    losses = abs(sum(value for value in pnl_values if value < 0.0))
    if losses == 0.0:
        return round(gains, 6) if gains > 0.0 else 0.0
    return round(gains / losses, 6)


def expectancy(pnl_values: Sequence[float]) -> float:
    if not pnl_values:
        return 0.0
    return round(sum(pnl_values) / len(pnl_values), 6)


def pnl_metrics(trades: Sequence[Mapping[str, object]]) -> dict[str, object]:
    pnl_values = [safe_float(trade.get("paper_pnl")) for trade in trades]
    symbols = [str(trade.get("symbol", "")) for trade in trades if str(trade.get("symbol", ""))]
    sectors = [sector_for_symbol(symbol) for symbol in symbols]
    regimes = [str(trade.get("regime", "")) for trade in trades if str(trade.get("regime", ""))]
    wins = [value for value in pnl_values if value > 0.0]
    losses = [value for value in pnl_values if value < 0.0]
    symbol_counts = Counter(symbols)
    sector_counts = Counter(sectors)
    regime_counts = Counter(regimes)
    trade_count = len(pnl_values)
    return {
        "trade_count": trade_count,
        "net_pnl": round(sum(pnl_values), 6),
        "expectancy": expectancy(pnl_values),
        "profit_factor": profit_factor(pnl_values),
        "max_drawdown": max_drawdown(pnl_values),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / trade_count, 6) if trade_count else 0.0,
        "sample_count": trade_count,
        "symbol_count": len(symbol_counts),
        "sector_count": len(sector_counts),
        "regime_count": len(regime_counts),
        "top_symbol": symbol_counts.most_common(1)[0][0] if symbol_counts else "",
        "top_symbol_trade_share": round(symbol_counts.most_common(1)[0][1] / trade_count, 6) if symbol_counts and trade_count else 0.0,
        "top_sector": sector_counts.most_common(1)[0][0] if sector_counts else "",
        "top_sector_trade_share": round(sector_counts.most_common(1)[0][1] / trade_count, 6) if sector_counts and trade_count else 0.0,
        "top_regime": regime_counts.most_common(1)[0][0] if regime_counts else "",
        "top_regime_trade_share": round(regime_counts.most_common(1)[0][1] / trade_count, 6) if regime_counts and trade_count else 0.0,
        "worst_trade": round(min(pnl_values), 6) if pnl_values else 0.0,
        "best_trade": round(max(pnl_values), 6) if pnl_values else 0.0,
    }


def group_records(records: Sequence[Mapping[str, object]], field_name: str) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get(field_name, ""))].append(dict(record))
    return dict(grouped)


def load_public_champion_trades() -> list[dict[str, object]]:
    return read_jsonl_file(OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v3_trades.jsonl")


def load_public_leaderboard() -> list[dict[str, object]]:
    return read_jsonl_file(TOURNAMENT_ROOT / "public_tournament_leaderboard_v3.jsonl")


def load_public_champion_gate_results() -> list[dict[str, object]]:
    return read_jsonl_file(CHAMPION_ROOT / "public_paper_champion_gate_results.jsonl")


def public_data_only(records: Sequence[Mapping[str, object]]) -> bool:
    return all(str(record.get("market_data_source_type", "")) in PUBLIC_SOURCE_TYPES for record in records)


def live_safety_fields() -> dict[str, object]:
    return {
        "paper_only": True,
        "public_data_only": True,
        "fixture_trade_count": 0,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "broker_connection_enabled": False,
        "real_orders_placed": False,
        "real_order_enabled": False,
        "live_trading_enabled": False,
        "live_blocked": True,
    }


def write_summary_with_hash(path: Path, summary: Mapping[str, object]) -> dict[str, object]:
    output = dict(summary)
    output["summary_hash"] = stable_hash(output)
    write_json_file(path, output)
    return output

