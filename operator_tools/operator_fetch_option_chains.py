"""OPERATOR TOOL - manual options-chain snapshot fetch. NOT part of the DOPEY pipeline.

Run by a human operator only. No pipeline module or supervisor stage may import
or invoke this file; DOPEY itself performs no network fetch. Fetches the
CURRENT public options chain (Yahoo Finance via yfinance, personal-research
use, non-redistributable) for the tradable universe, targets the expiration
nearest TARGET_DTE, normalizes both sides, and stages one CSV per symbol under
dopey_data/real/raw/options_chains/<snapshot_date>/, then refreshes the
options manifest with sha256 pins.

Usage:  .venv\\Scripts\\python operator_tools\\operator_fetch_option_chains.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Final

import yfinance as yf

REPO = Path(__file__).resolve().parent.parent

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))  # operator scripts run from anywhere; repo packages must resolve
from dopey_core.market_calendar import is_trading_day  # noqa: E402
CHAIN_RAW_DIR = REPO / "dopey_data" / "real" / "raw" / "options_chains"
OPTIONS_MANIFEST_PATH = REPO / "dopey_data" / "real" / "manifests" / "options_data_manifest.json"
FORWARD_LEDGER_PATH: Final[Path] = REPO / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
_BASE_SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META",
    "AMZN", "GOOGL", "NFLX", "JPM", "BAC", "XLF", "XLK", "XLE", "XLY", "XLI",
    "XLU", "XLP", "XLV",
    "IBIT", "MSTR", "COIN",  # crypto-linked: BTC ETF, BTC treasury, exchange
    # short-candidate cohort (fundamentals screen 2026-07-10): put-side chains
    "AI", "BBAI", "CLSK", "IONQ", "LCID", "MARA", "PLTR", "RIOT", "RIVN", "SOUN",
    # liquid-ETF cohort (2026-07-23): signals already fire on these from local
    # history, but with no chain snapshot they died at missing_entry_context.
    # Hand-picked for options liquidity + asset-class diversity beyond equity
    # sectors; thin/duplicate ETFs (BIL/SHY/IEF/VOO/RSP/...) deliberately left
    # out - the entry liquidity floors would only reject them.
    "GLD", "TLT", "EEM", "EFA", "HYG", "SMH", "XBI", "ARKK", "USO",
    "XLB", "XLC", "XLRE",
)
# ETFs have no earnings; keep them out of the earnings-calendar fetch.
_NON_EARNINGS_ETFS = frozenset({
    "SPY", "QQQ", "IWM", "DIA", "IBIT",
    "GLD", "TLT", "EEM", "EFA", "HYG", "SMH", "XBI", "ARKK", "USO",
})


def _probation_extras() -> tuple[str, ...]:
    """Registry-staged probation names get chains snapshotted automatically;
    quarantined/retired names drop out the same way. Fail-safe to the base
    tuple (operator lanes never die on registry problems)."""
    try:
        from dopey_universe.universe_registry import probation_symbols

        return tuple(s for s in probation_symbols() if s not in _BASE_SYMBOLS)
    except Exception:  # noqa: BLE001
        return ()


SYMBOLS = _BASE_SYMBOLS + _probation_extras()
TARGET_DTE = 30
SURFACE_TARGET_DTES = (14, 30, 60)  # term structure for vol-surface metrics
HEADER = (
    "snapshot_date,symbol,expiry,dte_calendar,option_type,strike,bid,ask,mid,last,"
    "volume,open_interest,implied_vol,underlying_spot,source\n"
)
SOURCE_LABEL = "yahoo_finance_chain_snapshot"


def load_open_contract_requirements(path: Path) -> dict[str, tuple[tuple[str, str, float], ...]]:
    """Return exact open contracts that must remain in every later snapshot."""
    if not path.exists():
        return {}
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"forward ledger is unreadable: path={path}, error={error}") from error
    if not isinstance(ledger, dict):
        raise TypeError(f"forward ledger must be an object: path={path}")
    raw_positions = ledger.get("open_positions", [])
    if not isinstance(raw_positions, list):
        raise TypeError(f"forward ledger open_positions must be an array: path={path}")
    requirements: dict[str, set[tuple[str, str, float]]] = {}
    for index, raw_position in enumerate(raw_positions):
        if not isinstance(raw_position, dict):
            raise TypeError(f"forward open position must be an object: path={path}, index={index}")
        symbol = str(raw_position.get("symbol", ""))
        expiry = str(raw_position.get("expiry", ""))
        option_type = str(raw_position.get("option_type", ""))
        strike = raw_position.get("strike")
        if not symbol or not expiry or option_type not in {"call", "put"} or not isinstance(strike, (int, float)):
            raise ValueError(
                "forward open position has an invalid contract identity: "
                f"path={path}, index={index}, symbol={symbol!r}, expiry={expiry!r}, "
                f"option_type={option_type!r}, strike={strike!r}"
            )
        requirements.setdefault(symbol, set()).add((expiry, option_type, float(strike)))
    return {
        symbol: tuple(sorted(contracts))
        for symbol, contracts in sorted(requirements.items())
    }


def _contract_keys(lines: list[str]) -> set[tuple[str, str, float]]:
    keys: set[tuple[str, str, float]] = set()
    for line in lines:
        columns = line.rstrip("\n").split(",")
        if len(columns) != 15:
            raise ValueError(f"normalized option row has an invalid column count: count={len(columns)}")
        keys.add((columns[2], columns[4], float(columns[5])))
    return keys


def pick_expiry(expirations: tuple[str, ...], today: date, target_dte: int = TARGET_DTE) -> str | None:
    scored = []
    for expiry in expirations:
        try:
            dte = (date.fromisoformat(expiry) - today).days
        except ValueError:
            continue
        if 5 <= dte <= 100:
            scored.append((abs(dte - target_dte), expiry))
    return min(scored)[1] if scored else None


def pick_surface_expiries(expirations: tuple[str, ...], today: date) -> list[str]:
    chosen: list[str] = []
    for target in SURFACE_TARGET_DTES:
        expiry = pick_expiry(expirations, today, target)
        if expiry and expiry not in chosen:
            chosen.append(expiry)
    return chosen


def rows_for_side(frame, side: str, symbol: str, expiry: str, dte: int, spot: float, today: date) -> list[str]:
    rows: list[str] = []
    for _, row in frame.iterrows():
        strike = float(row["strike"])
        bid = float(row["bid"]) if row["bid"] == row["bid"] else 0.0
        ask = float(row["ask"]) if row["ask"] == row["ask"] else 0.0
        if strike <= 0 or ask <= 0 or bid < 0 or ask < bid:
            continue
        if not (0.5 * spot <= strike <= 1.5 * spot):
            continue
        iv = float(row["impliedVolatility"]) if row["impliedVolatility"] == row["impliedVolatility"] else 0.0
        if not (0.005 <= iv <= 5.0):
            continue
        last = float(row["lastPrice"]) if row["lastPrice"] == row["lastPrice"] else 0.0
        volume = int(row["volume"]) if row["volume"] == row["volume"] else 0
        open_interest = int(row["openInterest"]) if row["openInterest"] == row["openInterest"] else 0
        mid = round((bid + ask) / 2.0, 6)
        rows.append(
            f"{today.isoformat()},{symbol},{expiry},{dte},{side},{strike},{round(bid, 6)},{round(ask, 6)},"
            f"{mid},{round(last, 6)},{volume},{open_interest},{round(iv, 8)},{round(spot, 6)},{SOURCE_LABEL}\n"
        )
    return rows


EARNINGS_SYMBOLS = tuple(s for s in SYMBOLS if not s.startswith("XL") and s not in _NON_EARNINGS_ETFS)
EARNINGS_OUT = REPO / "dopey_data" / "real" / "raw" / "earnings_calendar"

# Transient provider hiccups (rate limits, empty envelopes) must never lose a
# symbol's day: every network call retries with backoff, persistent failures
# fall back to the newest prior calendar (the blackout reader consumes ONLY the
# newest file, so a dropped symbol would silently exit the IV-crush blackout),
# and a machine-readable health sidecar feeds the kaizen defect queue.
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.5


def _with_retries(action):
    """(result, None) on success; (None, last_error) after RETRY_ATTEMPTS."""
    last_error: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return action(), None
        except Exception as error:  # noqa: BLE001 - retried, then reported
            last_error = error
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
    return None, last_error


def _prior_calendar_future_rows(today: date) -> dict[str, list[str]]:
    """symbol -> future earnings dates from the newest existing calendar file."""
    files = sorted(EARNINGS_OUT.glob("*_earnings.csv")) if EARNINGS_OUT.exists() else []
    files = [f for f in files if not f.name.startswith(today.isoformat())]
    if not files:
        return {}
    rows: dict[str, list[str]] = {}
    for line in files[-1].read_text(encoding="utf-8").splitlines()[1:]:
        columns = line.split(",")
        if len(columns) < 4:
            continue
        symbol, earnings_date = columns[1], columns[2]
        try:
            if date.fromisoformat(earnings_date) >= today:
                rows.setdefault(symbol, []).append(earnings_date)
        except ValueError:
            continue
    return rows


def fetch_earnings_dates(today: date) -> None:
    """Upcoming earnings dates for single names (ETFs have none)."""
    EARNINGS_OUT.mkdir(parents=True, exist_ok=True)
    lines = ["snapshot_date,symbol,earnings_date,source\n"]
    failed: dict[str, str] = {}
    carried_forward: list[str] = []
    for symbol in EARNINGS_SYMBOLS:
        frame, error = _with_retries(lambda s=symbol: yf.Ticker(s).get_earnings_dates(limit=8))
        if error is not None:
            failed[symbol] = type(error).__name__
            print(f"{symbol}: earnings fetch failed after {RETRY_ATTEMPTS} attempts ({type(error).__name__})", flush=True)
            continue
        if frame is None or len(frame) == 0:
            continue
        future = sorted(
            {index.date().isoformat() for index in frame.index if index.date() >= today}
        )
        for earnings_date in future[:2]:
            lines.append(f"{today.isoformat()},{symbol},{earnings_date},yahoo_finance_earnings\n")
        time.sleep(0.4)
    if failed:
        # A failed symbol must not silently leave the blackout window: carry its
        # future dates forward from the newest prior calendar, provenance-marked.
        prior = _prior_calendar_future_rows(today)
        for symbol in sorted(failed):
            for earnings_date in prior.get(symbol, [])[:2]:
                lines.append(f"{today.isoformat()},{symbol},{earnings_date},carried_forward_prior_calendar\n")
                carried_forward.append(symbol)
    if len(lines) <= 1:
        # Total fetch failure: keep whatever calendar we already have instead of
        # overwriting the day with a header-only file that reads as "no earnings".
        print("earnings calendar: ALL fetches failed, existing files preserved", flush=True)
        return
    (EARNINGS_OUT / f"{today.isoformat()}_earnings.csv").write_text("".join(lines), encoding="utf-8")
    health = {
        "artifact_type": "earnings_fetch_health",
        "snapshot_date": today.isoformat(),
        "symbols_attempted": len(EARNINGS_SYMBOLS),
        "symbols_failed_after_retries": failed,
        "carried_forward_from_prior_calendar": sorted(set(carried_forward)),
        "retry_attempts": RETRY_ATTEMPTS,
    }
    (EARNINGS_OUT / f"{today.isoformat()}_earnings_fetch_health.json").write_text(
        json.dumps(health, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"earnings calendar: {len(lines) - 1} rows staged"
        f" ({len(failed)} failed after retries, {len(set(carried_forward))} carried forward)",
        flush=True,
    )


def _snapshot_symbol(
    symbol: str,
    today: date,
    held_contracts: tuple[tuple[str, str, float], ...],
) -> tuple[str, list[str], float, list[str]]:
    """(status, expiries, spot, rows) for one symbol; raises on provider errors."""
    ticker = yf.Ticker(symbol)
    expirations = tuple(ticker.options)
    expiries = pick_surface_expiries(expirations, today)
    held_expiries = tuple(sorted({contract[0] for contract in held_contracts}))
    expiries.extend(expiry for expiry in held_expiries if expiry in expirations and expiry not in expiries)
    if not expiries:
        return "no_eligible_expiry", [], 0.0, []
    spot = float(ticker.fast_info["last_price"])
    lines: list[str] = []
    for expiry in expiries:
        chain = ticker.option_chain(expiry)
        dte = (date.fromisoformat(expiry) - today).days
        lines += rows_for_side(chain.calls, "call", symbol, expiry, dte, spot, today)
        lines += rows_for_side(chain.puts, "put", symbol, expiry, dte, spot, today)
        time.sleep(0.3)
    return "ok", expiries, spot, lines


def main() -> int:
    today = date.today()
    if not is_trading_day(today):
        print("market closed (weekend/holiday): no snapshot taken (prevents stale marking sessions)", flush=True)
        return 0
    fetch_earnings_dates(today)
    open_contracts = load_open_contract_requirements(FORWARD_LEDGER_PATH)
    effective_symbols = tuple(dict.fromkeys((*SYMBOLS, *open_contracts)))
    out_dir = CHAIN_RAW_DIR / today.isoformat()
    file_hashes: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    missing_open_contracts: dict[str, list[dict[str, object]]] = {}
    failed_symbols: dict[str, str] = {}
    covered_open_contract_count = 0
    required_open_contract_count = sum(len(contracts) for contracts in open_contracts.values())
    for symbol in effective_symbols:
        held = open_contracts.get(symbol, ())
        result, error = _with_retries(lambda s=symbol, h=held: _snapshot_symbol(s, today, h))
        if error is not None:
            failed_symbols[symbol] = f"{type(error).__name__}: {error}"
            print(f"{symbol}: FAILED after {RETRY_ATTEMPTS} attempts {type(error).__name__}: {error}", flush=True)
            for expiry, option_type, strike in held:
                missing_open_contracts.setdefault(symbol, []).append(
                    {
                        "expiry": expiry,
                        "option_type": option_type,
                        "strike": strike,
                        "reason": f"symbol_fetch_failed_{type(error).__name__}",
                    }
                )
            continue
        status, expiries, spot, lines = result
        if status == "no_eligible_expiry":
            print(f"{symbol}: no eligible expiry, skipped", flush=True)
            for expiry, option_type, strike in held:
                missing_open_contracts.setdefault(symbol, []).append(
                    {"expiry": expiry, "option_type": option_type, "strike": strike, "reason": "expiry_unavailable"}
                )
            continue
        if len(lines) < 10:
            print(f"{symbol}: too few clean rows ({len(lines)}), skipped", flush=True)
            for expiry, option_type, strike in held:
                missing_open_contracts.setdefault(symbol, []).append(
                    {
                        "expiry": expiry,
                        "option_type": option_type,
                        "strike": strike,
                        "reason": "symbol_snapshot_too_few_clean_rows",
                    }
                )
            continue
        out_dir.mkdir(parents=True, exist_ok=True)  # created only once a real file lands:
        # a total-failure day must not leave an empty dir that the loader picks as "latest"
        path = out_dir / f"{symbol}_chain.csv"
        path.write_text(HEADER + "".join(lines), encoding="utf-8")
        relative = path.relative_to(REPO).as_posix()
        file_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        row_counts[relative] = len(lines)
        staged_contracts = _contract_keys(lines)
        for contract in held:
            if contract in staged_contracts:
                covered_open_contract_count += 1
                continue
            missing_open_contracts.setdefault(symbol, []).append(
                {
                    "expiry": contract[0],
                    "option_type": contract[1],
                    "strike": contract[2],
                    "reason": "exact_open_contract_not_staged",
                }
            )
        print(f"{symbol}: {len(lines)} rows expiries {expiries} spot {spot:.2f}", flush=True)
        time.sleep(0.7)
    if not file_hashes:
        print("NO CHAIN FILES STAGED", flush=True)
        return 1
    # MERGE with the existing manifest: prior snapshot days must keep their sha256
    # pins or the archive's history becomes unverifiable (and unloadable).
    if OPTIONS_MANIFEST_PATH.exists():
        try:
            prior = json.loads(OPTIONS_MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
        for relative, digest in prior.get("file_hashes", {}).items():
            if relative not in file_hashes and (REPO / relative).exists():
                file_hashes[relative] = digest
                row_counts.setdefault(relative, int(prior.get("row_counts", {}).get(relative, 0)))
    manifest = {
        "manifest_id": f"options-chain-snapshots-operator-{today.isoformat()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_family": "options_chain_snapshots",
        "provider_name": "yahoo_finance_via_yfinance_operator_staged",
        "provider_terms_reviewed": True,
        "license_status": "reviewed_allowed_internal_research",
        "redistribution_allowed": False,
        "template_only": False,
        "snapshot_dates": sorted({p.name for p in CHAIN_RAW_DIR.iterdir() if p.is_dir()}),
        "local_file_paths": sorted(file_hashes),
        "file_hashes": file_hashes,
        "row_counts": row_counts,
        "open_contract_coverage_status": (
            "complete" if not missing_open_contracts else "blocked_missing_open_contract_quotes"
        ),
        "required_open_contract_count": required_open_contract_count,
        "covered_open_contract_count": covered_open_contract_count,
        "missing_open_contract_count": sum(len(records) for records in missing_open_contracts.values()),
        "missing_open_contracts": missing_open_contracts,
        "open_contract_expiries_preserved_beyond_rotating_surface": True,
        "manual_operator_note": (
            "Current-day public options-chain snapshots fetched manually by the operator "
            "outside the DOPEY pipeline. Personal/internal research use only; never "
            "redistributed. Snapshots accumulate forward to grow a quote-priced archive."
        ),
        "not_broker_data": True,
        "not_credentials": True,
        "not_live_data": True,
        "not_network_fetched_by_dopey": True,
        "not_real_data": False,
        "paper_only": True,
        "live_blocked": True,
        "fetch_health": {
            "snapshot_date": today.isoformat(),
            "symbols_attempted": len(effective_symbols),
            "symbols_staged": len({p.split("/")[-1] for p in file_hashes if p.startswith(f"dopey_data/real/raw/options_chains/{today.isoformat()}/")}),
            "symbols_failed_after_retries": failed_symbols,
            "retry_attempts": RETRY_ATTEMPTS,
        },
    }
    temp = OPTIONS_MANIFEST_PATH.with_name(OPTIONS_MANIFEST_PATH.name + ".tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, OPTIONS_MANIFEST_PATH)
    print(f"manifest pins {len(file_hashes)} chain files across {len(manifest['snapshot_dates'])} snapshot dates", flush=True)
    if missing_open_contracts:
        print(
            "OPEN CONTRACT COVERAGE INCOMPLETE: "
            f"missing={sum(len(records) for records in missing_open_contracts.values())}, "
            f"required={required_open_contract_count}",
            flush=True,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
