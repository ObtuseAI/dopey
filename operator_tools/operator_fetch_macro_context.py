"""OPERATOR TOOL - manual macro/positioning context fetch. NOT part of the DOPEY pipeline.

Run by a human operator only; no pipeline module or supervisor stage may import
or invoke this file. Stages four license-reviewed public lanes under
dopey_data/real/raw/macro_context/ with sha256 pins in a merged manifest:

1. US Treasury daily par yield curve (home.treasury.gov, US-government public
   domain) - the REAL risk-free curve, replacing the hardcoded 4% assumption.
2. Volatility term structure: ^VIX9D/^VIX/^VIX3M/^VIX6M closes + ^SKEW
   (Yahoo Finance via yfinance, personal-research use, non-redistributable).
3. FINRA daily short-sale volume for the tradable universe (cdn.finra.org
   public-dissemination files, internal research use only).
4. CFTC Commitments of Traders, Legacy Futures Only, E-mini S&P 500
   (publicreporting.cftc.gov Socrata API, US-government public data).

Explicitly REFUSED lanes (governance): DoltHub community options databases and
similar unlicensed aggregations - provenance and license are unreviewable, so
the import gates must never see them.

Usage:  .venv\\Scripts\\python operator_tools\\operator_fetch_macro_context.py
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
import yfinance as yf

REPO = Path(__file__).resolve().parent.parent

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))  # operator scripts run from anywhere; repo packages must resolve
from dopey_core.market_calendar import is_trading_day, previous_trading_day  # noqa: E402
MACRO_DIR = REPO / "dopey_data" / "real" / "raw" / "macro_context"
MACRO_MANIFEST_PATH = REPO / "dopey_data" / "real" / "manifests" / "macro_context_manifest.json"

VOL_INDEX_SYMBOLS = ("^VIX9D", "^VIX", "^VIX3M", "^VIX6M", "^SKEW")
_BASE_UNIVERSE = (
    "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META",
    "AMZN", "GOOGL", "NFLX", "JPM", "BAC", "XLF", "XLK", "XLE", "XLY", "XLI",
    "XLU", "XLP", "XLV",
    "IBIT", "MSTR", "COIN",
    # short-candidate cohort (2026-07-10): short-flow visibility on the names
    # the fundamentals screen flagged
    "AI", "BBAI", "CLSK", "IONQ", "LCID", "MARA", "PLTR", "RIOT", "RIVN", "SOUN",
)


def _probation_extras() -> tuple[str, ...]:
    """Registry-staged probation names join the macro lanes automatically;
    quarantined/retired names drop out the same way. Fail-safe to the base."""
    try:
        from dopey_universe.universe_registry import probation_symbols

        return tuple(s for s in probation_symbols() if s not in _BASE_UNIVERSE)
    except Exception:  # noqa: BLE001
        return ()


UNIVERSE = _BASE_UNIVERSE + _probation_extras()
FINRA_LOOKBACK_SESSIONS = 5
COT_MARKET = "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE"
COT_REPORTS = 104  # ~2 years of weekly positioning
USER_AGENT = {"User-Agent": "dopey-operator-research/1.0 (personal research)"}
# Crowd-attention proxy: Wikimedia pageviews are OPEN data (no credentials, no
# ToS-violating scraping). Single names only - ETF articles carry no retail
# attention signal. Sources like X/Twitter are refused (paid/ToS-restricted);
# Reddit/StockTwits would need operator-owned API credentials kept outside the
# repo and are a user decision, not staged here.
ATTENTION_ARTICLES = {
    "AAPL": "Apple_Inc.", "MSFT": "Microsoft", "NVDA": "Nvidia",
    "AMD": "Advanced_Micro_Devices", "TSLA": "Tesla,_Inc.", "META": "Meta_Platforms",
    "AMZN": "Amazon_(company)", "GOOGL": "Alphabet_Inc.", "NFLX": "Netflix",
    "JPM": "JPMorgan_Chase", "BAC": "Bank_of_America",
}
ATTENTION_LOOKBACK_DAYS = 120
# Crypto series (Yahoo lane): 24/7 markets - weekend moves are a TESTABLE
# leading-indicator hypothesis for Monday equities. Context/foundry input only;
# direct crypto exchange trading stays outside the envelope.
CRYPTO_SYMBOLS = ("BTC-USD", "ETH-USD")
# Druckenmiller liquidity-impulse inputs (FRED keyless CSV; Fed data = public):
# net liquidity ~ WALCL (Fed balance sheet) - RRPONTSYD (reverse repo) - WTREGEN (TGA)
FRED_LIQUIDITY_SERIES = ("WALCL", "RRPONTSYD", "WTREGEN")
# Congressional STOCK Act disclosures (public government records) via the
# open-source senate-stock-watcher aggregate. 45-day filing delay, amount
# RANGES not exact sizes - a positioning/attention lane, never a copy-trade.
# senate-stock-watcher aggregate verified STALE (ends 2020-12); kadoa's
# congress-trading-monitor parses the official House Clerk + Senate eFD
# portals and is current (verified through 2026-06 on 2026-07-10).
CONGRESS_TICKER_BASE = "https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/ticker"


def _atomic_write_text(path: Path, text: str) -> None:
    """Durably replace one staged text artifact without exposing partial bytes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def fetch_treasury_curve(today: date) -> tuple[str, int]:
    """Current-month daily par yield curve; falls back to prior month early in a month."""
    months = [today.strftime("%Y%m"), (today.replace(day=1) - timedelta(days=1)).strftime("%Y%m")]
    rows: list[str] = ["date,label,maturity_years,yield_pct\n"]
    maturity_years = {
        "1 Mo": 1 / 12, "1.5 Month": 0.125, "2 Mo": 2 / 12, "3 Mo": 0.25, "4 Mo": 4 / 12,
        "6 Mo": 0.5, "1 Yr": 1.0, "2 Yr": 2.0, "3 Yr": 3.0, "5 Yr": 5.0, "7 Yr": 7.0,
        "10 Yr": 10.0, "20 Yr": 20.0, "30 Yr": 30.0,
    }
    for month in months:
        url = (
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            f"daily-treasury-rates.csv/all/{month}?type=daily_treasury_yield_curve"
            f"&field_tdr_date_value_month={month}&page&_format=csv"
        )
        response = requests.get(url, headers=USER_AGENT, timeout=30)
        if response.status_code != 200 or "Date" not in response.text[:200]:
            continue
        lines = response.text.splitlines()
        header = [column.strip().strip('"') for column in lines[0].split(",")]
        for line in lines[1:]:
            cells = [cell.strip().strip('"') for cell in line.split(",")]
            if len(cells) != len(header) or not cells[0]:
                continue
            try:
                iso = datetime.strptime(cells[0], "%m/%d/%Y").date().isoformat()
            except ValueError:
                continue
            for label, years in maturity_years.items():
                if label in header:
                    value = cells[header.index(label)]
                    if value:
                        rows.append(f"{iso},{label.replace(' ', '')},{years:.6f},{value}\n")
        if len(rows) > 1:
            break
    path = MACRO_DIR / "treasury_yield_curve.csv"
    if len(rows) <= 1:
        print("treasury: fetch failed, existing file preserved", flush=True)
        return path.name, 0
    _atomic_write_text(path, "".join(rows))
    print(f"treasury: {len(rows) - 1} tenor rows staged", flush=True)
    return path.name, len(rows) - 1


def fetch_vol_term_structure() -> tuple[str, int]:
    path = MACRO_DIR / "vol_term_structure.csv"
    existing = _read_vol_term_rows(path)
    fetched: dict[str, list[tuple[str, float]]] = {}
    for symbol in VOL_INDEX_SYMBOLS:
        normalized_symbol = symbol.lstrip("^")
        symbol_rows: list[tuple[str, float]] = []
        try:
            history = yf.Ticker(symbol).history(period="2y", auto_adjust=False)
            for index, close in history["Close"].items():
                if close == close and float(close) > 0:
                    symbol_rows.append(
                        (
                            index.date().isoformat(),
                            round(float(close), 4),
                        )
                    )
            time.sleep(0.4)
        except Exception as error:  # noqa: BLE001 - operator lane: report and continue
            print(f"{symbol}: vol index fetch failed {type(error).__name__}", flush=True)
        if symbol_rows:
            fetched[normalized_symbol] = symbol_rows
    if not fetched:
        print("vol term structure: ALL fetches failed, existing file preserved", flush=True)
        return path.name, 0
    merged = _merge_vol_term_rows(existing, fetched)
    staged_rows = [
        (observed_date, symbol, close)
        for symbol, rows in merged.items()
        for observed_date, close in rows
    ]
    staged_rows.sort(key=lambda row: (row[0], row[1]))
    encoded = ["date,symbol,close\n"]
    encoded.extend(
        f"{observed_date},{symbol},{close}\n"
        for observed_date, symbol, close in staged_rows
    )
    _atomic_write_text(path, "".join(encoded))
    refreshed_count = sum(
        bool(fetched.get(symbol))
        and merged[symbol] == sorted(fetched[symbol])
        for symbol in merged
    )
    print(
        "vol term structure: "
        f"{len(staged_rows)} rows staged "
        f"({refreshed_count} refreshed, {len(merged) - refreshed_count} preserved indices)",
        flush=True,
    )
    return path.name, len(staged_rows)


def _read_vol_term_rows(
    path: Path,
) -> dict[str, list[tuple[str, float]]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["date", "symbol", "close"]:
            raise ValueError(
                "existing volatility term-structure schema is invalid: "
                f"path={path}, fields={reader.fieldnames}"
            )
        rows: dict[str, list[tuple[str, float]]] = {}
        for line_number, row in enumerate(reader, start=2):
            observed_date = str(row.get("date", ""))
            symbol = str(row.get("symbol", ""))
            try:
                date.fromisoformat(observed_date)
                close = float(str(row.get("close", "")))
            except ValueError as error:
                raise ValueError(
                    "existing volatility term-structure row is invalid: "
                    f"path={path}, line={line_number}"
                ) from error
            if not symbol or close <= 0.0:
                raise ValueError(
                    "existing volatility term-structure row is invalid: "
                    f"path={path}, line={line_number}"
                )
            rows.setdefault(symbol, []).append((observed_date, close))
    return rows


def _merge_vol_term_rows(
    existing: dict[str, list[tuple[str, float]]],
    fetched: dict[str, list[tuple[str, float]]],
) -> dict[str, list[tuple[str, float]]]:
    merged: dict[str, list[tuple[str, float]]] = {}
    for symbol in sorted(set(existing) | set(fetched)):
        prior = sorted(existing.get(symbol, []))
        staged = sorted(fetched.get(symbol, []))
        staged_is_non_regressive = bool(staged) and (
            not prior
            or (
                len(staged) >= max(1, int(len(prior) * 0.9))
                and staged[-1][0] >= prior[-1][0]
            )
        )
        merged[symbol] = staged if staged_is_non_regressive else prior
    return merged


def fetch_finra_short_volume(today: date) -> tuple[str, int]:
    universe = set(UNIVERSE)
    rows = ["date,symbol,short_volume,short_exempt_volume,total_volume\n"]
    day = today if is_trading_day(today) else previous_trading_day(today)
    fetched_days = 0
    market_scan_rows: list[tuple[str, int, int]] = []  # (symbol, short_vol, total_vol) newest day
    market_scan_day = ""
    while fetched_days < FINRA_LOOKBACK_SESSIONS:
        url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{day.strftime('%Y%m%d')}.txt"
        try:
            response = requests.get(url, headers=USER_AGENT, timeout=30)
            if response.status_code == 200 and "|" in response.text[:200]:
                for line in response.text.splitlines()[1:]:
                    parts = line.split("|")
                    if len(parts) >= 5:
                        if parts[1] in universe:
                            rows.append(f"{day.isoformat()},{parts[1]},{parts[2]},{parts[3]},{parts[4]}\n")
                        # whole-market discovery scan: aggregate the NEWEST
                        # successfully fetched day once (the file is already in
                        # hand - no extra network for discovery)
                        if not market_scan_day or market_scan_day == day.isoformat():
                            try:
                                market_scan_rows.append((parts[1], int(parts[2]), int(parts[4])))
                                market_scan_day = day.isoformat()
                            except ValueError:
                                pass
                fetched_days += 1
            else:
                print(f"finra {day.isoformat()}: HTTP {response.status_code}, skipped", flush=True)
                fetched_days += 1  # count the attempt: missing day, not an infinite walk
        except Exception as error:  # noqa: BLE001
            print(f"finra {day.isoformat()}: fetch failed {type(error).__name__}", flush=True)
            fetched_days += 1
        day = previous_trading_day(day)
        time.sleep(0.4)
    _write_finra_market_scan(market_scan_day, market_scan_rows, universe)
    path = MACRO_DIR / "finra_short_volume.csv"
    if len(rows) <= 1:
        print("finra short volume: nothing staged, existing file preserved", flush=True)
        return path.name, 0
    _atomic_write_text(path, "".join(rows))
    print(f"finra short volume: {len(rows) - 1} symbol-day rows staged", flush=True)
    return path.name, len(rows) - 1


def _write_finra_market_scan(scan_day: str, scan_rows: list[tuple[str, int, int]], universe: set[str]) -> None:
    """Whole-market activity scan for the universe governor's OFFLINE
    discovery: the most-active non-universe common-stock tickers plus the
    short-flow extremes among them. Same license posture as the filtered lane
    (FINRA public dissemination, internal research use). Discovery input
    only - never edge evidence."""
    if not scan_day or not scan_rows:
        return
    liquid = [
        (symbol, short_vol, total_vol)
        for symbol, short_vol, total_vol in scan_rows
        if symbol not in universe
        and total_vol >= 2_000_000
        and symbol.isalpha() and 1 <= len(symbol) <= 5   # skip test issues / units / warrants-style suffixes
    ]
    by_volume = sorted(liquid, key=lambda item: -item[2])[:50]
    with_ratio = [
        {"symbol": s, "total_volume": tv, "short_volume_ratio": round(sv / tv, 4)}
        for s, sv, tv in liquid if tv > 0
    ]
    by_ratio = sorted(with_ratio, key=lambda item: -item["short_volume_ratio"])[:50]
    scan = {
        "artifact_type": "finra_market_scan",
        "scan_date": scan_day,
        "most_active_non_universe": [
            {"symbol": s, "total_volume": tv, "short_volume_ratio": round(sv / tv, 4) if tv else 0.0}
            for s, sv, tv in by_volume
        ],
        "short_ratio_extremes_non_universe": by_ratio,
        "liquidity_floor_shares": 2_000_000,
        "semantics": "discovery_input_only_not_edge_evidence",
        "paper_only": True,
        "live_blocked": True,
    }
    target = REPO / "artifacts" / "dopey" / "universe" / "finra_market_scan.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, json.dumps(scan, indent=2, sort_keys=True) + "\n")
    print(f"finra market scan: {len(by_volume)} active + {len(by_ratio)} ratio-extreme non-universe names ({scan_day})", flush=True)


def fetch_cftc_cot() -> tuple[str, int]:
    url = (
        "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
        f"?market_and_exchange_names={requests.utils.quote(COT_MARKET)}"
        f"&$order=report_date_as_yyyy_mm_dd%20DESC&$limit={COT_REPORTS}"
    )
    path = MACRO_DIR / "cftc_cot_es.csv"
    try:
        response = requests.get(url, headers=USER_AGENT, timeout=30)
        records = response.json() if response.status_code == 200 else []
    except Exception as error:  # noqa: BLE001
        print(f"cftc cot: fetch failed {type(error).__name__}", flush=True)
        records = []
    rows = ["report_date,noncomm_long,noncomm_short,noncomm_net,open_interest\n"]
    for record in records:
        try:
            long_positions = float(record["noncomm_positions_long_all"])
            short_positions = float(record["noncomm_positions_short_all"])
            rows.append(
                f"{str(record['report_date_as_yyyy_mm_dd'])[:10]},{long_positions:.0f},{short_positions:.0f},"
                f"{long_positions - short_positions:.0f},{float(record['open_interest_all']):.0f}\n"
            )
        except (KeyError, ValueError, TypeError):
            continue
    if len(rows) <= 1:
        print("cftc cot: nothing staged, existing file preserved", flush=True)
        return path.name, 0
    _atomic_write_text(path, "".join(rows))
    print(f"cftc cot: {len(rows) - 1} weekly reports staged", flush=True)
    return path.name, len(rows) - 1


def fetch_wikipedia_attention(today: date) -> tuple[str, int]:
    # pageviews publish with ~24-48h lag; a range ending on an unpublished day
    # 404s for SOME articles (API inconsistency) - end two days back, always
    end_day = today - timedelta(days=2)
    start = (end_day - timedelta(days=ATTENTION_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = end_day.strftime("%Y%m%d")
    rows = ["date,symbol,article,views\n"]
    fetched_symbols: set[str] = set()
    for symbol, article in ATTENTION_ARTICLES.items():
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/user/{requests.utils.quote(article, safe='')}/daily/{start}/{end}"
        )
        items: list[dict] = []
        for attempt in range(2):  # transient 429/5xx from the API are common
            try:
                response = requests.get(url, headers=USER_AGENT, timeout=30)
                if response.status_code == 200:
                    items = response.json().get("items", [])
                    break
                print(f"{symbol}: attention HTTP {response.status_code} (attempt {attempt + 1})", flush=True)
                time.sleep(1.5)
            except Exception as error:  # noqa: BLE001
                print(f"{symbol}: attention fetch failed {type(error).__name__} (attempt {attempt + 1})", flush=True)
                time.sleep(1.5)
        for item in items:
            stamp = str(item.get("timestamp", ""))[:8]
            views = int(item.get("views", 0))
            if len(stamp) == 8 and views >= 0:
                # article titles can contain commas (Tesla,_Inc.) - underscore
                # them so the CSV stays 4 naive-split-safe columns
                rows.append(f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]},{symbol},{article.replace(',', '_')},{views}\n")
        if items:
            fetched_symbols.add(symbol)
        time.sleep(0.3)
    path = MACRO_DIR / "wikipedia_pageviews.csv"
    # MERGE: a failed symbol keeps its previously staged rows instead of being
    # silently erased by the wholesale rewrite (the freshness sentinel still
    # sees per-lane staleness via the max date).
    missing = set(ATTENTION_ARTICLES) - fetched_symbols
    if missing and path.exists():
        carried = 0
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split(",")
            if len(parts) == 4 and parts[1] in missing:
                rows.append(line + "\n")
                carried += 1
        if carried:
            print(f"attention: carried forward {carried} prior rows for failed names {sorted(missing)}", flush=True)
    if len(rows) <= 1:
        print("attention: ALL fetches failed, existing file preserved", flush=True)
        return path.name, 0
    _atomic_write_text(path, "".join(rows))
    print(f"attention: {len(rows) - 1} rows staged ({len(fetched_symbols)}/{len(ATTENTION_ARTICLES)} names fresh)", flush=True)
    return path.name, len(rows) - 1


def fetch_crypto_series() -> tuple[str, int]:
    rows = ["date,symbol,close\n"]
    for symbol in CRYPTO_SYMBOLS:
        try:
            history = yf.Ticker(symbol).history(period="2y", auto_adjust=False)
            for index, close in history["Close"].items():
                if close == close and float(close) > 0:
                    rows.append(f"{index.date().isoformat()},{symbol.replace('-USD', '')},{round(float(close), 2)}\n")
            time.sleep(0.4)
        except Exception as error:  # noqa: BLE001
            print(f"{symbol}: crypto fetch failed {type(error).__name__}", flush=True)
    path = MACRO_DIR / "crypto_series.csv"
    if len(rows) <= 1:
        print("crypto: ALL fetches failed, existing file preserved", flush=True)
        return path.name, 0
    _atomic_write_text(path, "".join(rows))
    print(f"crypto: {len(rows) - 1} rows staged (24/7 series incl weekends)", flush=True)
    return path.name, len(rows) - 1


def fetch_fed_liquidity() -> tuple[str, int]:
    rows = ["date,series,value\n"]
    for series in FRED_LIQUIDITY_SERIES:
        try:
            response = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}", headers=USER_AGENT, timeout=30)
            for line in response.text.splitlines()[1:] if response.status_code == 200 else []:
                parts = line.split(",")
                if len(parts) == 2 and parts[1] not in (".", "") and parts[0] >= "2020-01-01":
                    rows.append(f"{parts[0]},{series},{parts[1]}\n")
            time.sleep(0.4)
        except Exception as error:  # noqa: BLE001
            print(f"{series}: liquidity fetch failed {type(error).__name__}", flush=True)
    path = MACRO_DIR / "fed_liquidity.csv"
    if len(rows) <= 1:
        print("fed liquidity: ALL fetches failed, existing file preserved", flush=True)
        return path.name, 0
    _atomic_write_text(path, "".join(rows))
    print(f"fed liquidity: {len(rows) - 1} rows staged ({len(FRED_LIQUIDITY_SERIES)} series)", flush=True)
    return path.name, len(rows) - 1


def fetch_congress_trades() -> tuple[str, int]:
    rows = ["transaction_date,disclosure_date,symbol,member,type,amount_range\n"]
    for symbol in SYMBOLS_FOR_CONGRESS:
        try:
            response = requests.get(f"{CONGRESS_TICKER_BASE}/{symbol}.json", headers=USER_AGENT, timeout=30)
            trades = response.json().get("trades", []) if response.status_code == 200 else []
        except Exception as error:  # noqa: BLE001
            print(f"{symbol}: congress fetch failed {type(error).__name__}", flush=True)
            trades = []
        for record in trades:
            iso = str(record.get("transaction_date", ""))
            if len(iso) != 10 or iso < "2025-01-01":
                continue
            kind = str(record.get("type", record.get("transaction_type", ""))).replace(",", ";")
            member = str(record.get("filer_id", "")).replace(",", ";")
            amount = str(record.get("amount", record.get("amount_range", ""))).replace(",", ";")
            disclosure = str(record.get("filing_date", "")).replace(",", ";")
            rows.append(f"{iso},{disclosure},{symbol},{member},{kind},{amount}\n")
        time.sleep(0.25)
    path = MACRO_DIR / "congress_trades.csv"
    if len(rows) <= 1:
        print("congress trades: nothing staged (source empty/unreachable), existing file preserved", flush=True)
        return path.name, 0
    _atomic_write_text(path, "".join(rows))
    print(f"congress trades: {len(rows) - 1} universe transactions staged since 2025-01-01", flush=True)
    return path.name, len(rows) - 1


SYMBOLS_FOR_CONGRESS = (
    "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META",
    "AMZN", "GOOGL", "NFLX", "JPM", "BAC", "XLF", "XLK", "XLE", "XLY", "XLI",
    "XLU", "XLP", "XLV", "IBIT", "MSTR", "COIN",
    "AI", "BBAI", "CLSK", "IONQ", "LCID", "MARA", "PLTR", "RIOT", "RIVN", "SOUN",
)

# Fundamentals screen (put-side research): tradable single names PLUS a
# speculative watchlist across the themes where valuation excess concentrates.
# Watchlist names are SCREENED, not traded - promotion into the tradable
# universe is a separate governed operator step (history staged, chains
# snapshotted, spine re-validated). ETFs are excluded (no comparable P/E).
TRADABLE_SINGLE_NAMES = (
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "NFLX",
    "JPM", "BAC", "MSTR", "COIN",
    # short-candidate cohort promoted 2026-07-10 (history + chains staged)
    "AI", "BBAI", "CLSK", "IONQ", "LCID", "MARA", "PLTR", "RIOT", "RIVN", "SOUN",
) + _probation_extras()  # registry-staged names are tradable single names by construction (options-probed)
FUNDAMENTALS_WATCHLIST = {
    # theme -> symbols (liquid, optionable; screened for valuation excess)
    "ev": ("TSLA", "RIVN", "LCID", "NIO"),
    "quantum": ("IONQ", "RGTI", "QBTS"),
    "ai": ("PLTR", "AI", "SOUN", "BBAI", "SMCI", "NVDA", "AMD", "META", "MSFT", "GOOGL", "AAPL", "AMZN", "NFLX"),
    "crypto": ("MSTR", "COIN", "MARA", "RIOT", "CLSK"),
    "financials": ("JPM", "BAC"),
}
FUNDAMENTALS_ACCRUAL_DAYS = 400  # keep point-in-time history for future foundry joins
SHORT_CROWDING_ACCRUAL_DAYS = 400
IPO_LOOKBACK_MONTHS = 24


def fetch_fundamentals(today: date) -> tuple[str, int]:
    """Valuation + quality snapshot per name (yfinance info, personal research).
    Accrues by (date,symbol) so the screen gains point-in-time history."""

    theme_by_symbol: dict[str, str] = {}
    for theme, symbols in FUNDAMENTALS_WATCHLIST.items():
        for symbol in symbols:
            theme_by_symbol.setdefault(symbol, theme)
    for symbol in TRADABLE_SINGLE_NAMES:
        theme_by_symbol.setdefault(symbol, "governed_universe")
    field_names = (
        "date",
        "symbol",
        "theme",
        "in_universe",
        "market_cap",
        "enterprise_value",
        "total_revenue",
        "trailing_pe",
        "forward_pe",
        "price_to_sales",
        "price_to_book",
        "profit_margin",
        "revenue_growth",
        "free_cashflow",
        "total_debt",
        "total_cash",
        "first_trade_date",
    )
    fresh: dict[str, dict[str, str]] = {}
    for symbol, theme in sorted(theme_by_symbol.items()):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            history_metadata = ticker.history_metadata or {}
        except Exception as error:  # noqa: BLE001
            print(f"{symbol}: fundamentals fetch failed {type(error).__name__}", flush=True)
            time.sleep(0.4)
            continue
        quote_type = str(info.get("quoteType", "")).upper()
        if quote_type and quote_type != "EQUITY":
            print(
                f"{symbol}: fundamentals skipped quoteType={quote_type}",
                flush=True,
            )
            time.sleep(0.4)
            continue
        def _num(key: str) -> str:
            value = info.get(key)
            return f"{float(value):.6g}" if isinstance(value, (int, float)) and not isinstance(value, bool) else ""

        def _utc_date(value: object) -> str:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return ""
            parsed = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
                seconds=float(value)
            )
            if parsed.date() > today:
                raise ValueError(
                    "provider first-trade date is in the future: "
                    f"symbol={symbol}, firstTradeDate={value}, parsed={parsed.date()}"
                )
            return parsed.date().isoformat()

        market_cap = _num("marketCap")
        if not market_cap:
            print(f"{symbol}: fundamentals empty (no marketCap), skipped", flush=True)
            time.sleep(0.4)
            continue
        in_universe = "1" if symbol in TRADABLE_SINGLE_NAMES else "0"
        fresh[symbol] = {
            "date": today.isoformat(),
            "symbol": symbol,
            "theme": theme,
            "in_universe": in_universe,
            "market_cap": market_cap,
            "enterprise_value": _num("enterpriseValue"),
            "total_revenue": _num("totalRevenue"),
            "trailing_pe": _num("trailingPE"),
            "forward_pe": _num("forwardPE"),
            "price_to_sales": _num("priceToSalesTrailing12Months"),
            "price_to_book": _num("priceToBook"),
            "profit_margin": _num("profitMargins"),
            "revenue_growth": _num("revenueGrowth"),
            "free_cashflow": _num("freeCashflow"),
            "total_debt": _num("totalDebt"),
            "total_cash": _num("totalCash"),
            "first_trade_date": _utc_date(history_metadata.get("firstTradeDate")),
        }
        time.sleep(0.4)
    path = MACRO_DIR / "fundamentals.csv"
    # merge: prior rows for other dates (and today's rows for symbols that
    # failed this pass) survive; window capped to the accrual horizon
    merged: dict[tuple[str, str], dict[str, str]] = {}
    cutoff = (today - timedelta(days=FUNDAMENTALS_ACCRUAL_DAYS)).isoformat()
    if path.exists():
        reader = csv.DictReader(path.read_text(encoding="utf-8").splitlines())
        for row in reader:
            observed = str(row.get("date", ""))
            symbol = str(row.get("symbol", "")).upper()
            if observed >= cutoff and symbol:
                merged[(observed, symbol)] = {
                    field: str(row.get(field, "")) for field in field_names
                }
    for symbol, row in fresh.items():
        merged[(today.isoformat(), symbol)] = row
    if not merged:
        print("fundamentals: nothing staged, existing file preserved", flush=True)
        return path.name, 0
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=field_names, lineterminator="\n")
    writer.writeheader()
    writer.writerows(merged[key] for key in sorted(merged))
    _atomic_write_text(path, output.getvalue())
    print(f"fundamentals: {len(fresh)}/{len(theme_by_symbol)} names fresh, {len(merged)} rows accrued", flush=True)
    return path.name, len(merged)


def _ipo_month_keys(today: date, lookback_months: int) -> tuple[str, ...]:
    if lookback_months <= 0:
        raise ValueError(
            f"IPO lookback must be positive: lookback_months={lookback_months}"
        )
    current_month = today.year * 12 + today.month - 1
    return tuple(
        f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"
        for month_index in range(
            current_month - lookback_months + 1,
            current_month + 1,
        )
    )


def _ipo_number(value: object) -> str:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    if not text or "-" in text:
        return ""
    try:
        return f"{float(text):.10g}"
    except ValueError:
        return ""


def fetch_nasdaq_ipo_calendar(
    today: date,
    lookback_months: int,
) -> tuple[str, int]:
    """Stage priced IPOs for governed recent-listing discovery and fragility."""

    field_names = (
        "event_date",
        "symbol",
        "company_name",
        "exchange",
        "offer_price",
        "shares_offered",
        "offer_amount",
        "status",
        "source",
    )
    staged: dict[tuple[str, str], dict[str, str]] = {}
    headers = {
        **USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    for month in _ipo_month_keys(today, lookback_months):
        url = f"https://api.nasdaq.com/api/ipo/calendar?date={month}"
        response: requests.Response | None = None
        for attempt in range(1, 4):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                break
            except requests.RequestException as error:
                print(
                    "nasdaq IPO calendar fetch warning: "
                    f"month={month}, attempt={attempt}, error={error}",
                    flush=True,
                )
                if attempt == 3:
                    raise RuntimeError(
                        "nasdaq IPO calendar fetch failed after retries: "
                        f"month={month}, url={url}, error={error}"
                    ) from error
                time.sleep(float(attempt))
        if response is None:
            raise RuntimeError(
                f"nasdaq IPO calendar returned no response: month={month}, url={url}"
            )
        try:
            payload = response.json()
        except requests.JSONDecodeError as error:
            raise ValueError(
                "nasdaq IPO calendar returned invalid JSON: "
                f"month={month}, url={url}, body={response.text[:500]}"
            ) from error
        data = payload.get("data")
        priced = data.get("priced") if isinstance(data, dict) else None
        rows = priced.get("rows") if isinstance(priced, dict) else None
        for record in rows if isinstance(rows, list) else []:
            if not isinstance(record, dict):
                continue
            symbol = str(record.get("proposedTickerSymbol", "")).strip().upper()
            raw_date = str(record.get("pricedDate", "")).strip()
            if not symbol or not raw_date:
                continue
            try:
                event_date = datetime.strptime(raw_date, "%m/%d/%Y").date()
            except ValueError as error:
                raise ValueError(
                    "nasdaq IPO calendar contained an invalid priced date: "
                    f"month={month}, symbol={symbol}, pricedDate={raw_date!r}"
                ) from error
            if event_date > today:
                continue
            staged[(event_date.isoformat(), symbol)] = {
                "event_date": event_date.isoformat(),
                "symbol": symbol,
                "company_name": str(record.get("companyName", "")).strip(),
                "exchange": str(record.get("proposedExchange", "")).strip(),
                "offer_price": _ipo_number(record.get("proposedSharePrice")),
                "shares_offered": _ipo_number(record.get("sharesOffered")),
                "offer_amount": _ipo_number(
                    record.get("dollarValueOfSharesOffered")
                ),
                "status": "priced",
                "source": "nasdaq_ipo_calendar",
            }
        time.sleep(0.25)
    path = MACRO_DIR / "ipo_calendar.csv"
    if not staged:
        raise RuntimeError(
            "nasdaq IPO calendar returned no priced rows: "
            f"lookback_months={lookback_months}"
        )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=field_names, lineterminator="\n")
    writer.writeheader()
    writer.writerows(staged[key] for key in sorted(staged))
    _atomic_write_text(path, output.getvalue())
    print(
        f"nasdaq IPO calendar: {len(staged)} priced listings staged across "
        f"{lookback_months} months",
        flush=True,
    )
    return path.name, len(staged)


def fetch_short_crowding(today: date) -> tuple[str, int]:
    """Stage actual open-short snapshots separately from daily short-sale flow."""

    header = (
        "date,symbol,shares_short,shares_short_prior_month,short_percent_float,"
        "short_ratio,float_shares,shares_outstanding,held_percent_institutions,"
        "held_percent_insiders,average_volume,market_cap,source\n"
    )
    fresh: dict[str, str] = {}
    for symbol in sorted(set(UNIVERSE)):
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as error:  # noqa: BLE001 - operator lane keeps per-symbol failures visible
            print(
                f"{symbol}: short-crowding fetch failed {type(error).__name__}",
                flush=True,
            )
            time.sleep(0.4)
            continue

        def _number(key: str) -> str:
            value = info.get(key)
            return (
                f"{float(value):.10g}"
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else ""
            )

        if not _number("sharesShort") or not _number("shortPercentOfFloat"):
            print(
                f"{symbol}: actual short-interest snapshot unavailable, skipped",
                flush=True,
            )
            time.sleep(0.4)
            continue
        fresh[symbol] = (
            f"{today.isoformat()},{symbol},{_number('sharesShort')},"
            f"{_number('sharesShortPriorMonth')},{_number('shortPercentOfFloat')},"
            f"{_number('shortRatio')},{_number('floatShares')},"
            f"{_number('sharesOutstanding')},{_number('heldPercentInstitutions')},"
            f"{_number('heldPercentInsiders')},{_number('averageVolume')},"
            f"{_number('marketCap')},yahoo_finance_personal_research\n"
        )
        time.sleep(0.4)

    path = MACRO_DIR / "short_crowding.csv"
    merged: dict[tuple[str, str], str] = {}
    cutoff = (today - timedelta(days=SHORT_CROWDING_ACCRUAL_DAYS)).isoformat()
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
        if existing and existing[0] != header.strip():
            raise ValueError(
                "existing short-crowding schema mismatch: "
                f"path={path}, header={existing[0]!r}"
            )
        for line in existing[1:]:
            parts = line.split(",")
            if len(parts) == 13 and parts[0] >= cutoff:
                merged[(parts[0], parts[1])] = line + "\n"
    for symbol, row in fresh.items():
        merged[(today.isoformat(), symbol)] = row
    if not merged:
        print(
            "short crowding: no actual open-short snapshots staged",
            flush=True,
        )
        return path.name, 0
    _atomic_write_text(
        path,
        "".join([header, *(merged[key] for key in sorted(merged))]),
    )
    print(
        f"short crowding: {len(fresh)}/{len(set(UNIVERSE))} symbols fresh, "
        f"{len(merged)} rows accrued",
        flush=True,
    )
    return path.name, len(merged)


def fetch_nasdaq_threshold_securities(today: date) -> tuple[str, int]:
    """Stage the latest official Nasdaq Regulation SHO threshold list."""

    day = today if is_trading_day(today) else previous_trading_day(today)
    response: requests.Response | None = None
    source_url = ""
    observed_date = ""
    for _day_attempt in range(5):
        source_url = (
            "https://www.nasdaqtrader.com/dynamic/symdir/regsho/"
            f"nasdaqth{day.strftime('%Y%m%d')}.txt"
        )
        for request_attempt in range(1, 4):
            try:
                response = requests.get(
                    source_url,
                    headers=USER_AGENT,
                    timeout=30,
                )
                response.raise_for_status()
                if "Reg SHO Threshold Flag" not in response.text[:250]:
                    raise ValueError(
                        "Nasdaq threshold response does not contain the "
                        f"expected header: url={source_url}, "
                        f"body={response.text[:250]!r}"
                    )
                observed_date = day.isoformat()
                break
            except (requests.RequestException, ValueError) as error:
                print(
                    "nasdaq threshold fetch warning: "
                    f"date={day}, attempt={request_attempt}, error={error}",
                    flush=True,
                )
                response = None
                if request_attempt < 3:
                    time.sleep(float(request_attempt))
        if response is not None:
            break
        day = previous_trading_day(day)
    if response is None or not observed_date:
        raise RuntimeError(
            "Nasdaq threshold list unavailable after five trading dates: "
            f"last_url={source_url}"
        )
    reader = csv.DictReader(io.StringIO(response.text), delimiter="|")
    required = (
        "Symbol",
        "Security Name",
        "Market Category",
        "Reg SHO Threshold Flag",
        "Rule 3210",
        "Filler",
    )
    if tuple(reader.fieldnames or ()) != required:
        raise ValueError(
            "Nasdaq threshold list schema mismatch: "
            f"url={source_url}, fields={reader.fieldnames}"
        )
    rows = [
        {
            "date": observed_date,
            "symbol": str(record["Symbol"]).strip().upper(),
            "exchange": "XNAS",
            "source": "nasdaq_reg_sho_threshold_official",
        }
        for record in reader
        if str(record.get("Symbol", "")).strip()
        and str(record.get("Reg SHO Threshold Flag", "")).strip() == "Y"
    ]
    if not rows:
        raise RuntimeError(
            f"Nasdaq threshold list contained no flagged securities: url={source_url}"
        )
    path = MACRO_DIR / "threshold_securities.csv"
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=("date", "symbol", "exchange", "source"),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    _atomic_write_text(path, output.getvalue())
    print(
        f"nasdaq threshold securities: {len(rows)} rows staged for "
        f"{observed_date}",
        flush=True,
    )
    return path.name, len(rows)


def parse_finra_margin_statistics(page_html: str) -> tuple[tuple[str, float, float, float], ...]:
    """Parse FINRA's server-rendered margin table into ascending month rows."""

    parsed: list[tuple[str, float, float, float]] = []
    for row_html in re.findall(
        r"<tr\b[^>]*>(.*?)</tr>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        cells = [
            re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()
            for cell in re.findall(
                r"<t[dh]\b[^>]*>(.*?)</t[dh]>",
                row_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
        ]
        if len(cells) < 4 or re.fullmatch(r"[A-Z][a-z]{2}-\d{2}", cells[0]) is None:
            continue
        month = datetime.strptime(cells[0], "%b-%y").strftime("%Y-%m-01")
        try:
            debit, cash_credit, margin_credit = (
                float(value.replace(",", "")) for value in cells[1:4]
            )
        except ValueError as error:
            raise ValueError(
                f"FINRA margin row contains a nonnumeric balance: cells={cells[:4]}"
            ) from error
        parsed.append((month, debit, cash_credit, margin_credit))
    if not parsed:
        raise ValueError("FINRA margin page exposed zero parseable monthly rows")
    return tuple(sorted(set(parsed)))


def fetch_finra_margin_statistics() -> tuple[str, int]:
    """Stage official aggregate customer-margin balances as market leverage context."""

    url = "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"
    path = MACRO_DIR / "finra_margin_statistics.csv"
    try:
        response = requests.get(url, headers=USER_AGENT, timeout=30)
        response.raise_for_status()
        records = parse_finra_margin_statistics(response.text)
    except (requests.RequestException, ValueError) as error:
        print(
            f"FINRA margin statistics fetch failed {type(error).__name__}: {error}",
            flush=True,
        )
        if path.exists():
            existing_rows = max(
                len(path.read_text(encoding="utf-8").splitlines()) - 1,
                0,
            )
            print(
                f"FINRA margin statistics: existing {existing_rows} rows preserved",
                flush=True,
            )
            return path.name, existing_rows
        return path.name, 0
    rows = [
        "month,debit_balances_millions,free_credit_cash_millions,"
        "free_credit_margin_millions,source\n"
    ]
    rows.extend(
        f"{month},{debit:.0f},{cash_credit:.0f},{margin_credit:.0f},"
        "finra_rule_4521d_aggregate\n"
        for month, debit, cash_credit, margin_credit in records
    )
    _atomic_write_text(path, "".join(rows))
    print(
        f"FINRA margin statistics: {len(records)} monthly rows staged",
        flush=True,
    )
    return path.name, len(records)


def main() -> int:
    today = date.today()
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    staged = [
        ("treasury_yield_curve.csv", "us_treasury_public_domain") + fetch_treasury_curve(today)[1:],
        ("vol_term_structure.csv", "yahoo_finance_personal_research") + fetch_vol_term_structure()[1:],
        ("finra_short_volume.csv", "finra_public_dissemination_internal_research") + fetch_finra_short_volume(today)[1:],
        ("cftc_cot_es.csv", "cftc_us_government_public_data") + fetch_cftc_cot()[1:],
        ("wikipedia_pageviews.csv", "wikimedia_open_data_pageviews") + fetch_wikipedia_attention(today)[1:],
        ("crypto_series.csv", "yahoo_finance_personal_research") + fetch_crypto_series()[1:],
        ("fed_liquidity.csv", "federal_reserve_fred_public_data") + fetch_fed_liquidity()[1:],
        ("congress_trades.csv", "stock_act_public_disclosures_senate_stock_watcher") + fetch_congress_trades()[1:],
        ("fundamentals.csv", "yahoo_finance_personal_research") + fetch_fundamentals(today)[1:],
        ("ipo_calendar.csv", "nasdaq_ipo_calendar_internal_research")
        + fetch_nasdaq_ipo_calendar(today, IPO_LOOKBACK_MONTHS)[1:],
        ("short_crowding.csv", "yahoo_finance_personal_research_actual_open_short_snapshot")
        + fetch_short_crowding(today)[1:],
        ("threshold_securities.csv", "nasdaq_reg_sho_threshold_official")
        + fetch_nasdaq_threshold_securities(today)[1:],
        ("finra_margin_statistics.csv", "finra_rule_4521d_aggregate_internal_research")
        + fetch_finra_margin_statistics()[1:],
    ]
    file_hashes: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    sources: dict[str, str] = {}
    for name, source, rows in staged:
        target = MACRO_DIR / name
        if not target.exists():
            continue
        relative = target.relative_to(REPO).as_posix()
        file_hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        row_counts[relative] = rows if rows > 0 else row_counts.get(relative, 0)
        sources[relative] = source
    if not file_hashes:
        print("NO MACRO FILES STAGED", flush=True)
        return 1
    if MACRO_MANIFEST_PATH.exists():
        try:
            prior = json.loads(MACRO_MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
        for relative, count in prior.get("row_counts", {}).items():
            if row_counts.get(relative) in (None, 0) and (REPO / relative).exists():
                row_counts[relative] = int(count)
    manifest = {
        "manifest_id": f"macro-context-operator-{today.isoformat()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_family": "macro_positioning_context",
        "provider_name": "treasury_gov+yahoo_finance+finra_cdn+cftc_socrata_operator_staged",
        "provider_terms_reviewed": True,
        "license_status": "reviewed_allowed_internal_research",
        "redistribution_allowed": False,
        "template_only": False,
        "per_file_sources": sources,
        "local_file_paths": sorted(file_hashes),
        "file_hashes": file_hashes,
        "row_counts": row_counts,
        "refused_sources_note": (
            "DoltHub community options databases and similar unlicensed aggregations are "
            "REFUSED: license/provenance unreviewable, so they never enter the import gates."
        ),
        "manual_operator_note": (
            "Public macro/positioning context fetched manually by the operator outside the "
            "DOPEY pipeline. Treasury and CFTC lanes are US-government public data; Yahoo "
            "and FINRA lanes are personal/internal research use only, never redistributed."
        ),
        "not_broker_data": True,
        "not_credentials": True,
        "not_live_data": True,
        "not_network_fetched_by_dopey": True,
        "not_real_data": False,
        "paper_only": True,
        "live_blocked": True,
    }
    _atomic_write_text(
        MACRO_MANIFEST_PATH,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    print(f"macro manifest pins {len(file_hashes)} files", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
