"""Public universe expansion V2 for real no-key OHLCV."""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from dopey_autonomy.public_champion_common import (
    CACHE_ROOT,
    OHLCV_FIELDNAMES,
    PUBLIC_CHAMPION_ROOT,
    PUBLIC_DAILY_ROOT,
    active_manifest,
    manifest_files,
    proof_record,
    read_csv_file,
    record_with_hash,
    sanitize_ohlcv_rows,
    utc_now_iso,
    write_csv_file,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE
from dopey_runtime_bootstrap.active_python_resolver import preferred_repo_python

from .market_lake_public_promotion import run_market_lake_public_promotion


SUMMARY_PATH = PUBLIC_CHAMPION_ROOT / "public_universe_expansion_v2_summary.json"
CANDIDATES_PATH = PUBLIC_CHAMPION_ROOT / "public_universe_candidate_symbols.jsonl"
FETCH_RECORDS_PATH = PUBLIC_CHAMPION_ROOT / "public_universe_fetch_records.jsonl"
REJECTIONS_PATH = PUBLIC_CHAMPION_ROOT / "public_universe_rejections.jsonl"
PROOF_PATH = PUBLIC_CHAMPION_ROOT / "public_universe_expansion_v2_proof.jsonl"
STARTING_WATCH_UNIVERSE_SIZE = 200
TARGET_CANDIDATE_UNIVERSE_SIZE = 250
YFINANCE_BATCH_SIZE = 50
UNIVERSE_REFERENCE = "large-cap index holdings and liquid cross-asset proxies reviewed 2026-07-16"
HISTORY_DAILY_ROOT = Path(__file__).resolve().parent.parent / "dopey_data" / "history" / "raw"


def candidate_symbol_universe_v2() -> list[str]:
    symbols = [
        "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "RSP", "MDY", "EFA", "EEM",
        "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC", "SMH", "SOXX", "IBB", "XBI", "IYR",
        "TLT", "IEF", "SHY", "HYG", "LQD", "TIP", "BIL", "GLD", "SLV", "USO", "UNG", "DBC", "UUP",
        "AAPL", "MSFT", "NVDA", "AMD", "AVGO", "SMCI", "INTC", "MU", "QCOM", "TXN", "AMAT", "LRCX", "ASML", "TSM",
        "META", "GOOGL", "GOOG", "AMZN", "TSLA", "NFLX", "CRM", "NOW", "ADBE", "ORCL", "SNOW", "DDOG", "NET", "MDB",
        "CRWD", "PANW", "FTNT", "ZS", "OKTA", "PLTR", "AI", "ARM", "DELL", "HPE", "ANET", "CSCO",
        "JPM", "BAC", "C", "GS", "MS", "WFC", "AXP", "BLK", "SCHW", "COF", "V", "MA", "PYPL", "SQ",
        "COST", "WMT", "HD", "LOW", "TGT", "NKE", "MCD", "SBUX", "BKNG", "ABNB", "DIS", "CMG", "LULU",
        "PG", "KO", "PEP", "PM", "MO", "CL", "KMB", "MDLZ",
        "UNH", "LLY", "JNJ", "MRK", "PFE", "ABBV", "TMO", "DHR", "ISRG", "REGN", "VRTX", "GILD", "AMGN",
        "CAT", "DE", "BA", "GE", "RTX", "LMT", "NOC", "GD", "HON", "UPS", "FDX", "UNP", "CSX", "ETN",
        "CVX", "COP", "SLB", "OXY", "MPC", "XOM", "EOG", "HAL", "PSX", "VLO", "KMI",
        "VIXY", "UVXY", "SVXY", "SQQQ", "TQQQ", "SOXL", "SOXS", "ARKK", "ARKW",
        "IBM", "ACN", "INTU", "ADP", "CDNS", "SNPS", "KLAC", "MCHP", "NXPI", "MSI", "FICO", "PAYX", "ADSK", "ROP", "GLW", "HPQ",
        "T", "VZ", "TMUS", "CHTR", "FOXA", "FOX", "EA", "TTWO", "LYV", "OMC", "IPG",
        "TJX", "ROST", "ORLY", "AZO", "GPC", "DHI", "LEN", "PHM", "NVR", "F", "GM", "RCL", "CCL", "MAR", "HLT", "YUM", "DPZ", "EBAY",
        "KR", "SYY", "EL", "GIS", "KHC", "HSY", "MKC", "ADM", "TSN", "STZ", "MNST", "CAG", "CHD", "CPB",
        "MDT", "ABT", "SYK", "BSX", "BDX", "EW", "ZBH", "RMD", "IDXX", "IQV", "MCK", "COR", "CVS", "CI", "HUM", "ELV", "HCA", "CNC", "BIIB", "MRNA",
        "BK", "STT", "TROW", "AMP", "PNC", "USB", "TFC", "FITB", "MTB", "HBAN", "RF", "CFG", "CME", "ICE", "NDAQ", "CBOE", "MCO", "SPGI", "MSCI", "AON", "AJG", "MMC", "CB", "PGR", "ALL", "TRV", "AIG", "MET", "PRU",
        "EMR", "ITW", "MMM", "CMI", "PCAR", "ROK", "PH", "FAST", "GWW", "URI", "PWR", "JCI", "CARR", "OTIS", "GEV", "WAB", "DAL", "UAL", "NSC", "ODFL",
        "WMB", "TRGP", "DVN", "FANG", "BKR",
        "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "ED", "PEG", "EIX", "WEC", "ES", "AWK", "CEG", "VST",
        "AMT", "PLD", "EQIX", "WELL", "SPG", "O", "PSA", "DLR", "CCI", "VICI", "CBRE", "AVB", "EQR",
        "LIN", "SHW", "FCX", "NEM", "APD", "ECL", "NUE", "STLD", "VMC", "MLM", "DD", "DOW", "PPG", "BALL", "LYB", "ALB",
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for symbol in symbols:
        if symbol not in seen:
            unique.append(symbol)
            seen.add(symbol)
    return unique


def run_public_universe_expansion_v2() -> dict[str, object]:
    return expand_public_universe(candidate_symbol_universe_v2(), True, 600)


def expand_public_universe(candidate_symbols: list[str], refresh_missing: bool, timeout_seconds: int) -> dict[str, object]:
    before_symbols = {str(record.get("symbol", "")) for record in manifest_files()}
    candidate_records = build_candidate_records(candidate_symbols)
    history_frontier = governed_history_frontier()
    existing_records, refresh_symbols = inspect_existing_public_files(candidate_symbols, history_frontier)
    fetch_records = list(existing_records)
    rejections: list[dict[str, object]] = []
    if refresh_missing and refresh_symbols:
        fetched, rejected = fetch_missing_with_yfinance(refresh_symbols, timeout_seconds)
        fetch_records.extend(fetched)
        rejections.extend(rejected)
    for symbol in refresh_symbols:
        public_path = PUBLIC_DAILY_ROOT / f"{symbol}.csv"
        if not public_path.exists() and not any(str(record.get("symbol", "")) == symbol for record in rejections):
            rejections.append(rejection_record(symbol, "no_public_rows_available", "all available no-key public routes returned no rows"))
    promotion = run_market_lake_public_promotion(False)
    after_manifest = active_manifest()
    active_files = after_manifest.get("files", []) if isinstance(after_manifest.get("files", []), list) else []
    active_public = [
        record for record in active_files
        if isinstance(record, dict) and str(record.get("market_data_source_type", "")).startswith("public")
    ]
    active_fixture = [
        record for record in active_files
        if isinstance(record, dict) and str(record.get("market_data_source_type", "")) == "fixture_fallback"
    ]
    loaded_symbols = sorted({str(record.get("symbol", "")) for record in active_public if str(record.get("symbol", ""))})
    provider_success_counts = Counter(str(record.get("provider", "")) for record in fetch_records if str(record.get("status", "")) in {"cached_public_file", "fetched_public_rows"})
    provider_failure_counts = Counter(str(record.get("provider", "")) for record in rejections)
    summary = {
        "artifact_type": "public_universe_expansion_v2_summary",
        "public_universe_expansion_version": "dopey-public-universe-expansion-v2",
        "public_universe_expansion_status": expansion_status(len(candidate_symbols), len(loaded_symbols), len(active_fixture)),
        "candidate_symbol_count": len(candidate_symbols),
        "starting_watch_universe_target": STARTING_WATCH_UNIVERSE_SIZE,
        "candidate_headroom_target": TARGET_CANDIDATE_UNIVERSE_SIZE,
        "universe_reference": UNIVERSE_REFERENCE,
        "governed_history_frontier": history_frontier,
        "refresh_symbol_count": len(refresh_symbols),
        "symbols_attempted": candidate_symbols,
        "symbols_loaded": loaded_symbols,
        "new_symbols_added": len(set(loaded_symbols) - before_symbols),
        "active_public_symbol_count": len(active_public),
        "active_public_rows": int(promotion.get("public_rows_active", 0)),
        "provider_success_counts": dict(sorted(provider_success_counts.items())),
        "provider_failure_counts": dict(sorted(provider_failure_counts.items())),
        "fixture_symbols_added": len(active_fixture),
        "failed_symbol_count": len(rejections),
        "live_trading_enabled": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(CANDIDATES_PATH, candidate_records)
    write_jsonl_file(FETCH_RECORDS_PATH, fetch_records)
    write_jsonl_file(REJECTIONS_PATH, rejections)
    write_jsonl_file(PROOF_PATH, [proof_record("public-universe-expansion-v2", str(summary["public_universe_expansion_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def build_candidate_records(candidate_symbols: list[str]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, symbol in enumerate(candidate_symbols):
        record = {
            "artifact_type": "public_universe_candidate_symbol",
            "rank": index + 1,
            "symbol": symbol,
            "target_source": "real_public_no_key_ohlcv",
            "fixture_allowed": False,
        }
        records.append(record_with_hash(record, "record_hash"))
    return records


def governed_history_frontier() -> str:
    last_dates: list[str] = []
    for symbol in REQUIRED_HISTORY_UNIVERSE:
        rows = sanitize_ohlcv_rows(read_csv_file(HISTORY_DAILY_ROOT / f"{symbol}.csv"))
        if rows:
            last_dates.append(rows[-1]["date"])
    if not last_dates:
        raise FileNotFoundError(
            f"governed history frontier unavailable: history_root={HISTORY_DAILY_ROOT}"
        )
    return max(last_dates)


def inspect_existing_public_files(
    candidate_symbols: list[str],
    history_frontier: str,
) -> tuple[list[dict[str, object]], list[str]]:
    records: list[dict[str, object]] = []
    refresh: list[str] = []
    for symbol in candidate_symbols:
        path = PUBLIC_DAILY_ROOT / f"{symbol}.csv"
        rows = sanitize_ohlcv_rows(read_csv_file(path))
        if rows and rows[-1]["date"] >= history_frontier:
            record = {
                "artifact_type": "public_universe_fetch_record",
                "symbol": symbol,
                "provider": provider_from_public_path(path, rows),
                "status": "cached_public_file",
                "row_count": len(rows),
                "first_date": rows[0]["date"],
                "last_date": rows[-1]["date"],
                "path": str(path),
                "market_data_source_type": "public_cache" if str(rows[0].get("market_data_source_type", "")) == "public_cache" else "public_live_fetch",
            }
            records.append(record_with_hash(record, "record_hash"))
        else:
            refresh.append(symbol)
    return records, refresh


def provider_from_public_path(path: Path, rows: list[dict[str, str]]) -> str:
    for row in rows:
        provider = str(row.get("provider", "")).strip()
        if provider:
            return provider
    return path.parent.name


def fetch_missing_with_yfinance(symbols: list[str], timeout_seconds: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not symbols:
        return [], []
    records: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    for offset in range(0, len(symbols), YFINANCE_BATCH_SIZE):
        batch = symbols[offset:offset + YFINANCE_BATCH_SIZE]
        fetched, rejected = _fetch_yfinance_batch(batch, timeout_seconds)
        records.extend(fetched)
        rejections.extend(rejected)
    return records, rejections


def _fetch_yfinance_batch(symbols: list[str], timeout_seconds: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    with tempfile.TemporaryDirectory(prefix="dopey_public_universe_yf_") as temp_dir:
        output_dir = Path(temp_dir)
        script = yfinance_batch_script(symbols, output_dir)
        try:
            completed = subprocess.run(
                [str(preferred_repo_python()), "-c", script],
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return [], [rejection_record(symbol, "yfinance_timeout", str(exc)) for symbol in symbols]
        except OSError as exc:
            return [], [rejection_record(symbol, "yfinance_subprocess_error", f"{type(exc).__name__}: {exc}") for symbol in symbols]
        if completed.returncode != 0:
            return [], [rejection_record(symbol, "yfinance_fetch_failed", completed.stderr[-800:]) for symbol in symbols]
        records: list[dict[str, object]] = []
        rejections: list[dict[str, object]] = []
        for symbol in symbols:
            raw_rows = read_csv_file(output_dir / f"{symbol}.csv")
            normalized_candidates = [normalize_yfinance_row(row) for row in raw_rows]
            normalized = sanitize_ohlcv_rows(normalized_candidates)
            if normalized:
                write_csv_file(PUBLIC_DAILY_ROOT / f"{symbol}.csv", normalized, OHLCV_FIELDNAMES)
                write_csv_file(CACHE_ROOT / "yfinance" / f"{symbol}.csv", normalized, OHLCV_FIELDNAMES)
                record = {
                    "artifact_type": "public_universe_fetch_record",
                    "symbol": symbol,
                    "provider": "yfinance",
                    "status": "fetched_public_rows",
                    "row_count": len(normalized),
                    "first_date": normalized[0]["date"],
                    "last_date": normalized[-1]["date"],
                    "path": str(PUBLIC_DAILY_ROOT / f"{symbol}.csv"),
                    "market_data_source_type": "public_live_fetch",
                }
                records.append(record_with_hash(record, "record_hash"))
            else:
                rejections.append(rejection_record(symbol, "yfinance_empty_response", "no valid rows returned"))
        return records, rejections


def yfinance_batch_script(symbols: list[str], output_dir: Path) -> str:
    return "\n".join([
        "import pandas as pd",
        "import yfinance as yf",
        f"symbols = {json.dumps(symbols)}",
        f"output_dir = {str(output_dir)!r}",
        "data = yf.download(' '.join(symbols), period='max', interval='1d', auto_adjust=False, progress=False, threads=True, group_by='ticker')",
        "for symbol in symbols:",
        "    try:",
        "        frame = data[symbol] if hasattr(data, 'columns') and getattr(data.columns, 'nlevels', 1) > 1 and symbol in data.columns.get_level_values(0) else data",
        "        frame = frame.reset_index()",
        "        frame.to_csv(f'{output_dir}/{symbol}.csv', index=False)",
        "    except Exception:",
        "        pd.DataFrame().to_csv(f'{output_dir}/{symbol}.csv', index=False)",
    ])


def normalize_yfinance_row(row: dict[str, str]) -> dict[str, object]:
    close = str(row.get("close") or row.get("Close") or "")
    adjusted = str(row.get("adjusted_close") or row.get("Adj Close") or close)
    return {
        "date": str(row.get("date") or row.get("Date") or row.get("Datetime") or "")[:10],
        "open": str(row.get("open") or row.get("Open") or ""),
        "high": str(row.get("high") or row.get("High") or ""),
        "low": str(row.get("low") or row.get("Low") or ""),
        "close": close,
        "adjusted_close": adjusted,
        "volume": str(row.get("volume") or row.get("Volume") or "0"),
        "provider": "yfinance",
        "source_url": "yfinance.download(period=max, interval=1d)",
        "fetch_timestamp": utc_now_iso(),
        "adjustment_status": "adjusted_close_available" if adjusted and adjusted != close else "adjusted_close_unavailable_close_used",
        "market_data_source_type": "public_live_fetch",
    }


def rejection_record(symbol: str, reason: str, message: str) -> dict[str, object]:
    record = {
        "artifact_type": "public_universe_rejection",
        "symbol": symbol,
        "provider": "yfinance",
        "reason": reason,
        "message": message,
        "fixture_used": False,
        "live_trading_enabled": False,
    }
    return record_with_hash(record, "record_hash")


def expansion_status(candidate_count: int, active_public_count: int, active_fixture_count: int) -> str:
    if active_fixture_count > 0:
        return "public_universe_expanded_with_fixture_contamination_blocked"
    if candidate_count >= TARGET_CANDIDATE_UNIVERSE_SIZE and active_public_count >= STARTING_WATCH_UNIVERSE_SIZE:
        return "public_universe_expanded_target_met"
    if candidate_count >= TARGET_CANDIDATE_UNIVERSE_SIZE and active_public_count > 0:
        return "public_universe_expanded_partial_public_provider_limit"
    return "public_universe_expansion_blocked"


def artifact_paths() -> dict[str, str]:
    return {
        "public_universe_expansion_v2_summary": str(SUMMARY_PATH),
        "public_universe_candidate_symbols": str(CANDIDATES_PATH),
        "public_universe_fetch_records": str(FETCH_RECORDS_PATH),
        "public_universe_rejections": str(REJECTIONS_PATH),
        "public_universe_expansion_v2_proof": str(PROOF_PATH),
    }
