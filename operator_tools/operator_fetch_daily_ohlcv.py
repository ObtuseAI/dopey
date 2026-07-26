"""OPERATOR TOOL - daily OHLCV spine updater. NOT part of the DOPEY pipeline.

Run by a human operator (or their scheduled ritual) only; no pipeline module
imports this. Appends the latest daily bars (Yahoo Finance via yfinance,
personal-research use, non-redistributable) for the 24-symbol governed universe
to BOTH staged copies of the spine:

    dopey_data/real/raw/daily_ohlcv/<SYMBOL>.csv   (import-gate lane)
    dopey_data/history/raw/<SYMBOL>.csv            (history-spine lane)

then re-pins sha256 hashes in both manifests, recomputing the history
manifest's reproducibility hash with the repo's own canonical function so the
validators keep passing. Idempotent: only rows with date > the file's last
date are appended; schema matches the spine exactly
(date,symbol,open,high,low,close,adjusted_close,volume,source).

Without this the signal engine can never see a bar newer than the original
staging date and forward-walk entries starve within a week.

Usage:  .venv\\Scripts\\python operator_tools\\operator_fetch_daily_ohlcv.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import yfinance as yf

REPO = Path(__file__).resolve().parent.parent

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from dopey_core.market_calendar import is_trading_day  # noqa: E402
from dopey_data.history_models import history_manifest_hash  # noqa: E402
from dopey_data.history_validator import validate_history_dataset  # noqa: E402

REAL_DIR = REPO / "dopey_data" / "real" / "raw" / "daily_ohlcv"
HISTORY_DIR = REPO / "dopey_data" / "history" / "raw"
REAL_MANIFEST_PATH = REPO / "dopey_data" / "real" / "manifests" / "real_data_manifest.json"
HISTORY_MANIFEST_PATH = REPO / "dopey_data" / "history" / "history_dataset_manifest.json"
YAHOO_TICKERS = {"VIX": "^VIX"}  # everything else maps to itself
DAILY_BAR_FINALIZATION_DELAY = timedelta(minutes=30)
REAL_PROVIDER_SOURCES = frozenset({"protected_public_lake", "yahoo_finance"})
PROVIDER_FETCH_ATTEMPTS = 3
PROVIDER_RETRY_BASE_DELAY_SECONDS = 1.0
REFRESH_LOCK_STALE_AFTER = timedelta(hours=12)
INCOMPLETE_LOCK_GRACE = timedelta(minutes=5)


class OhlcvDataValidationError(ValueError):
    """Raised when a provider or staged OHLCV row is not safe to publish."""


class OhlcvRefreshTransactionError(RuntimeError):
    """Raised when an OHLCV generation cannot be published or restored safely."""


class OhlcvProviderFetchError(RuntimeError):
    """Raised after the bounded market-data retry policy is exhausted."""


def latest_completed_market_session(now_utc: datetime) -> date:
    """Return the latest XNYS session whose official close has passed."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    normalized = now_utc.astimezone(timezone.utc)
    calendar = xcals.get_calendar(
        "XNYS",
        start=date(normalized.year - 1, 1, 1).isoformat(),
        end=date(normalized.year + 1, 12, 31).isoformat(),
    )
    sessions = calendar.sessions_in_range(
        calendar.first_session.date(),
        normalized.date(),
    )
    completed = [
        session
        for session in sessions
        if calendar.session_close(session).to_pydatetime()
        + DAILY_BAR_FINALIZATION_DELAY
        <= normalized
    ]
    if not completed:
        raise RuntimeError(
            "XNYS calendar exposed no completed session before collection: "
            f"now_utc={normalized.isoformat()}"
        )
    return completed[-1].date()


def _finite_float(value: object, field: str, symbol: str, day: str) -> float:
    if isinstance(value, bool):
        raise OhlcvDataValidationError(
            f"invalid OHLCV field: symbol={symbol}, date={day}, field={field}, reason=boolean"
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise OhlcvDataValidationError(
            f"invalid OHLCV field: symbol={symbol}, date={day}, field={field}, "
            f"value={value!r}, reason=not_numeric"
        ) from error
    if not math.isfinite(parsed):
        raise OhlcvDataValidationError(
            f"invalid OHLCV field: symbol={symbol}, date={day}, field={field}, "
            f"value={value!r}, reason=not_finite"
        )
    return parsed


def _nonnegative_volume(value: object, symbol: str, day: str) -> int:
    parsed = _finite_float(value, "volume", symbol, day)
    if parsed < 0 or not parsed.is_integer():
        raise OhlcvDataValidationError(
            f"invalid OHLCV field: symbol={symbol}, date={day}, field=volume, "
            f"value={value!r}, reason=not_nonnegative_integer"
        )
    return int(parsed)


def _validate_ohlcv_values(
    symbol: str,
    day: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    adjusted_close: float,
    volume: int,
) -> None:
    prices = {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "adjusted_close": adjusted_close,
    }
    for field, value in prices.items():
        if not math.isfinite(value) or value <= 0:
            raise OhlcvDataValidationError(
                f"invalid OHLCV invariant: symbol={symbol}, date={day}, field={field}, "
                f"value={value!r}, reason=not_finite_positive"
            )
    if volume < 0:
        raise OhlcvDataValidationError(
            f"invalid OHLCV invariant: symbol={symbol}, date={day}, field=volume, "
            f"value={volume}, reason=negative"
        )
    if high < max(open_price, close, low):
        raise OhlcvDataValidationError(
            f"invalid OHLCV invariant: symbol={symbol}, date={day}, high={high}, "
            f"open={open_price}, low={low}, close={close}, reason=high_below_ohlc"
        )
    if low > min(open_price, close, high):
        raise OhlcvDataValidationError(
            f"invalid OHLCV invariant: symbol={symbol}, date={day}, low={low}, "
            f"open={open_price}, high={high}, close={close}, reason=low_above_ohlc"
        )


def collect_new_rows(
    symbol: str,
    maximum_completed_date: date,
) -> tuple[str, list[tuple[str, str]]]:
    """(last staged date, [(date, csv_line)] of VALID newer bars). Fetch only."""
    history_path = HISTORY_DIR / f"{symbol}.csv"
    lines = history_path.read_text(encoding="utf-8").splitlines()
    last_date = lines[-1].split(",", 1)[0] if len(lines) > 1 else "1900-01-01"
    return last_date, collect_new_rows_after_date(symbol, last_date, maximum_completed_date)


def collect_new_rows_after_date(
    symbol: str,
    last_staged_date: str,
    maximum_completed_date: date,
) -> list[tuple[str, str]]:
    """Fetch validated provider rows after an explicitly evidenced staged date."""
    try:
        parsed_last_date = date.fromisoformat(last_staged_date)
    except ValueError as error:
        raise OhlcvDataValidationError(
            f"last staged date is invalid: symbol={symbol}, date={last_staged_date!r}"
        ) from error
    provider_period = _provider_history_period(parsed_last_date, maximum_completed_date)
    frame = _fetch_provider_history_with_retries(
        symbol,
        provider_period,
        PROVIDER_FETCH_ATTEMPTS,
        PROVIDER_RETRY_BASE_DELAY_SECONDS,
    )
    new_rows: list[tuple[str, str]] = []
    observed_dates: set[str] = set()
    for index, row in frame.iterrows():
        day = index.date().isoformat()
        if (
            index.date() <= parsed_last_date
            or index.date() > maximum_completed_date
            or not is_trading_day(index.date())
        ):
            continue
        if day in observed_dates:
            raise OhlcvDataValidationError(
                f"duplicate provider bar: symbol={symbol}, date={day}"
            )
        observed_dates.add(day)
        try:
            open_price = _finite_float(row["Open"], "open", symbol, day)
            high = _finite_float(row["High"], "high", symbol, day)
            low = _finite_float(row["Low"], "low", symbol, day)
            close = _finite_float(row["Close"], "close", symbol, day)
            adjusted = _finite_float(row["Adj Close"], "adjusted_close", symbol, day)
            volume = _nonnegative_volume(row["Volume"], symbol, day)
        except KeyError as error:
            raise OhlcvDataValidationError(
                f"provider OHLCV row missing field: symbol={symbol}, date={day}, "
                f"field={error.args[0]}"
            ) from error
        _validate_ohlcv_values(
            symbol,
            day,
            open_price,
            high,
            low,
            close,
            adjusted,
            volume,
        )
        new_rows.append((day, f"{day},{symbol},{open_price},{high},{low},{close},{adjusted},{volume},yahoo_finance"))
    if parsed_last_date < maximum_completed_date and not new_rows:
        raise OhlcvDataValidationError(
            "provider returned no eligible bar despite a newer completed XNYS session: "
            f"symbol={symbol}, last_staged_date={parsed_last_date.isoformat()}, "
            f"maximum_completed_date={maximum_completed_date.isoformat()}, "
            f"provider_row_count={len(frame.index)}"
        )
    return sorted(new_rows)


def _provider_history_period(
    last_staged_date: date,
    maximum_completed_date: date,
) -> str:
    lag_days = max((maximum_completed_date - last_staged_date).days, 0)
    if lag_days <= 9:
        return "10d"
    if lag_days <= 31:
        return "1mo"
    if lag_days <= 92:
        return "3mo"
    if lag_days <= 183:
        return "6mo"
    if lag_days <= 366:
        return "1y"
    if lag_days <= 732:
        return "2y"
    return "max"


def _fetch_provider_history_with_retries(
    symbol: str,
    period: str,
    attempts: int,
    base_delay_seconds: float,
) -> Any:
    if attempts <= 0:
        raise ValueError(f"provider fetch attempts must be positive: attempts={attempts}")
    if base_delay_seconds < 0:
        raise ValueError(
            "provider retry delay must be nonnegative: "
            f"base_delay_seconds={base_delay_seconds}"
        )
    provider_symbol = YAHOO_TICKERS.get(symbol, symbol)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return yf.Ticker(provider_symbol).history(
                period=period,
                auto_adjust=False,
            )
        except Exception as error:  # noqa: BLE001 - bounded external-provider retry
            last_error = error
            print(
                "OHLCV provider fetch warning: "
                f"symbol={symbol}, provider_symbol={provider_symbol}, "
                f"period={period}, attempt={attempt}/{attempts}, "
                f"error={type(error).__name__}: {error}",
                flush=True,
            )
            if attempt < attempts:
                time.sleep(base_delay_seconds * float(attempt))
    if last_error is None:
        raise OhlcvProviderFetchError(
            "OHLCV provider fetch exhausted without a captured error: "
            f"symbol={symbol}, provider_symbol={provider_symbol}, period={period}"
        )
    raise OhlcvProviderFetchError(
        "OHLCV provider fetch failed after bounded retries: "
        f"symbol={symbol}, provider_symbol={provider_symbol}, period={period}, "
        f"attempts={attempts}, last_error={type(last_error).__name__}: {last_error}"
    ) from last_error


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OhlcvRefreshTransactionError(
            f"cannot load transaction input JSON: path={path}, error={type(error).__name__}: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise OhlcvRefreshTransactionError(
            f"transaction input JSON must be an object: path={path}"
        )
    return parsed


def _write_bytes_durable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _stage_appended_csv(source: Path, staged: Path, rows: list[str]) -> None:
    if not source.is_file():
        raise OhlcvRefreshTransactionError(f"required OHLCV copy is missing: path={source}")
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, staged)
    with staged.open("rb+") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size == 0:
            raise OhlcvRefreshTransactionError(f"OHLCV copy is empty: path={source}")
        handle.seek(-1, os.SEEK_END)
        if handle.read(1) != b"\n":
            handle.seek(0, os.SEEK_END)
            handle.write(b"\n")
        handle.seek(0, os.SEEK_END)
        handle.write(("\n".join(rows) + "\n").encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def _last_csv_date(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2:
        return "1900-01-01"
    return lines[-1].split(",", 1)[0]


def _validate_serialized_rows(
    symbol: str,
    rows: list[str],
    previous_date: str,
    maximum_completed_date: date,
) -> None:
    prior = date.fromisoformat(previous_date)
    for line in rows:
        fields = next(csv.reader([line]))
        if len(fields) != 9:
            raise OhlcvDataValidationError(
                f"serialized OHLCV row has wrong column count: symbol={symbol}, "
                f"columns={len(fields)}, row={line!r}"
            )
        day_text, row_symbol, open_text, high_text, low_text, close_text, adjusted_text, volume_text, source = fields
        try:
            day = date.fromisoformat(day_text)
        except ValueError as error:
            raise OhlcvDataValidationError(
                f"serialized OHLCV date is invalid: symbol={symbol}, date={day_text!r}"
            ) from error
        if row_symbol != symbol:
            raise OhlcvDataValidationError(
                f"serialized OHLCV symbol mismatch: expected={symbol}, observed={row_symbol}, date={day_text}"
            )
        if day <= prior or day > maximum_completed_date or not is_trading_day(day):
            raise OhlcvDataValidationError(
                f"serialized OHLCV date violates append boundary: symbol={symbol}, date={day_text}, "
                f"previous_date={prior.isoformat()}, maximum_completed_date={maximum_completed_date.isoformat()}"
            )
        if source != "yahoo_finance":
            raise OhlcvDataValidationError(
                f"serialized OHLCV source is not allowed: symbol={symbol}, date={day_text}, source={source!r}"
            )
        open_price = _finite_float(open_text, "open", symbol, day_text)
        high = _finite_float(high_text, "high", symbol, day_text)
        low = _finite_float(low_text, "low", symbol, day_text)
        close = _finite_float(close_text, "close", symbol, day_text)
        adjusted = _finite_float(adjusted_text, "adjusted_close", symbol, day_text)
        volume = _nonnegative_volume(volume_text, symbol, day_text)
        _validate_ohlcv_values(
            symbol,
            day_text,
            open_price,
            high,
            low,
            close,
            adjusted,
            volume,
        )
        prior = day


def _staged_path(root: Path, index: int) -> Path:
    return root / "staged" / f"{index:04d}.stage"


def _validated_missing_real_bootstrap_symbols(symbols: tuple[str, ...]) -> frozenset[str]:
    missing_real = tuple(
        symbol
        for symbol in symbols
        if (HISTORY_DIR / f"{symbol}.csv").is_file()
        and not (REAL_DIR / f"{symbol}.csv").exists()
    )
    if not missing_real:
        return frozenset()
    validation = validate_history_dataset(HISTORY_MANIFEST_PATH, HISTORY_DIR, False)
    if validation.get("dataset_status") != "valid_real_dataset":
        raise OhlcvRefreshTransactionError(
            "missing-real-copy bootstrap requires a currently valid history dataset: "
            f"dataset_status={validation.get('dataset_status')!r}, symbols={list(missing_real)}"
        )
    validation_record = validation.get("validation")
    if not isinstance(validation_record, dict) or not isinstance(
        validation_record.get("file_hashes"),
        dict,
    ):
        raise OhlcvRefreshTransactionError(
            "missing-real-copy bootstrap requires validator file-hash evidence"
        )
    validated_hashes = validation_record["file_hashes"]
    history_manifest = _load_json_object(HISTORY_MANIFEST_PATH)
    entries = history_manifest.get("data_files")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise OhlcvRefreshTransactionError(
            f"history manifest data_files must be a list of objects: path={HISTORY_MANIFEST_PATH}"
        )
    entries_by_symbol: dict[str, dict[str, Any]] = {}
    for entry in entries:
        path_value = entry.get("path")
        if isinstance(path_value, str):
            entry_symbol = Path(path_value).stem
            if entry_symbol in entries_by_symbol:
                raise OhlcvRefreshTransactionError(
                    f"history manifest has duplicate symbol entry: symbol={entry_symbol}"
                )
            entries_by_symbol[entry_symbol] = entry
    for symbol in missing_real:
        history_target = HISTORY_DIR / f"{symbol}.csv"
        entry = entries_by_symbol.get(symbol)
        actual_hash = _file_sha256(history_target)
        if entry is None:
            raise OhlcvRefreshTransactionError(
                f"missing-real-copy bootstrap lacks history manifest entry: symbol={symbol}"
            )
        source = entry.get("source")
        if source not in REAL_PROVIDER_SOURCES:
            raise OhlcvRefreshTransactionError(
                f"missing-real-copy bootstrap source is not an approved real provider: "
                f"symbol={symbol}, source={source!r}"
            )
        if entry.get("sha256") != actual_hash:
            raise OhlcvRefreshTransactionError(
                f"missing-real-copy bootstrap history pin mismatch: symbol={symbol}, "
                f"pinned={entry.get('sha256')!r}, actual={actual_hash}"
            )
        if validated_hashes.get(str(history_target)) != actual_hash:
            raise OhlcvRefreshTransactionError(
                f"missing-real-copy bootstrap lacks matching full-validator evidence: "
                f"symbol={symbol}, validated={validated_hashes.get(str(history_target))!r}, "
                f"actual={actual_hash}"
            )
    return frozenset(missing_real)


def _stage_manifest_outputs(
    symbols: tuple[str, ...],
    staged_by_target: dict[Path, Path],
    data_outputs: list[tuple[Path, Path]],
    data_baseline_hashes: dict[Path, str],
    new_data_targets: frozenset[Path],
    updated_at_utc: datetime,
    transaction_root: Path,
) -> tuple[list[tuple[Path, Path]], dict[Path, str], frozenset[Path]]:
    outputs = list(data_outputs)
    baseline_hashes = dict(data_baseline_hashes)
    real_manifest = _load_json_object(REAL_MANIFEST_PATH)
    real_hashes = real_manifest.get("file_hashes")
    if not isinstance(real_hashes, dict):
        raise OhlcvRefreshTransactionError(
            f"real-data manifest file_hashes must be an object: path={REAL_MANIFEST_PATH}"
        )
    for symbol in symbols:
        target = REAL_DIR / f"{symbol}.csv"
        relative = f"dopey_data/real/raw/daily_ohlcv/{symbol}.csv"
        pinned = real_hashes.get(relative)
        if target in new_data_targets and pinned is not None:
            raise OhlcvRefreshTransactionError(
                f"missing-real-copy bootstrap refuses an orphaned manifest pin: "
                f"symbol={symbol}, pinned={pinned!r}"
            )
        if target not in new_data_targets and pinned != baseline_hashes[target]:
            raise OhlcvRefreshTransactionError(
                f"real-data manifest pin does not match pre-publish bytes: symbol={symbol}, "
                f"pinned={pinned!r}, actual={baseline_hashes[target]}"
            )
        real_hashes[relative] = _file_sha256(staged_by_target[target])
    real_manifest["last_operator_ohlcv_update_utc"] = updated_at_utc.astimezone(timezone.utc).isoformat()
    real_manifest_stage = _staged_path(transaction_root, len(outputs))
    _write_bytes_durable(
        real_manifest_stage,
        (json.dumps(real_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    outputs.append((REAL_MANIFEST_PATH, real_manifest_stage))
    baseline_hashes[REAL_MANIFEST_PATH] = _file_sha256(REAL_MANIFEST_PATH)

    history_manifest = _load_json_object(HISTORY_MANIFEST_PATH)
    pinned_manifest_hash = history_manifest.get("manifest_reproducibility_hash")
    actual_manifest_hash = history_manifest_hash(history_manifest)
    if pinned_manifest_hash != actual_manifest_hash:
        raise OhlcvRefreshTransactionError(
            f"history manifest self-hash mismatch before publish: pinned={pinned_manifest_hash!r}, "
            f"actual={actual_manifest_hash}"
        )
    data_files = history_manifest.get("data_files")
    if not isinstance(data_files, list) or any(not isinstance(entry, dict) for entry in data_files):
        raise OhlcvRefreshTransactionError(
            f"history manifest data_files must be a list of objects: path={HISTORY_MANIFEST_PATH}"
        )
    updated_symbols: set[str] = set()
    for entry in data_files:
        path_value = entry.get("path")
        if not isinstance(path_value, str):
            raise OhlcvRefreshTransactionError(
                f"history manifest data file path must be text: entry={entry!r}"
            )
        symbol = Path(path_value).stem
        if symbol not in symbols:
            continue
        if symbol in updated_symbols:
            raise OhlcvRefreshTransactionError(
                f"history manifest has duplicate symbol entry: symbol={symbol}"
            )
        target = HISTORY_DIR / f"{symbol}.csv"
        if entry.get("sha256") != baseline_hashes[target]:
            raise OhlcvRefreshTransactionError(
                f"history manifest pin does not match pre-publish bytes: symbol={symbol}, "
                f"pinned={entry.get('sha256')!r}, actual={baseline_hashes[target]}"
            )
        staged = staged_by_target[target]
        entry["sha256"] = _file_sha256(staged)
        with staged.open("r", encoding="utf-8") as handle:
            entry["row_count"] = max(sum(1 for _ in handle) - 1, 0)
        updated_symbols.add(symbol)
    missing_entries = set(symbols) - updated_symbols
    if missing_entries:
        raise OhlcvRefreshTransactionError(
            f"history manifest is missing published symbols: symbols={sorted(missing_entries)}"
        )
    history_manifest["manifest_reproducibility_hash"] = ""
    history_manifest["manifest_reproducibility_hash"] = history_manifest_hash(history_manifest)
    history_manifest_stage = _staged_path(transaction_root, len(outputs))
    _write_bytes_durable(
        history_manifest_stage,
        (json.dumps(history_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    outputs.append((HISTORY_MANIFEST_PATH, history_manifest_stage))
    baseline_hashes[HISTORY_MANIFEST_PATH] = _file_sha256(HISTORY_MANIFEST_PATH)
    return outputs, baseline_hashes, new_data_targets


def _stage_refresh_outputs(
    rows_by_symbol: dict[str, list[str]],
    maximum_completed_date: date,
    updated_at_utc: datetime,
    transaction_root: Path,
) -> tuple[list[tuple[Path, Path]], dict[Path, str], frozenset[Path]]:
    outputs: list[tuple[Path, Path]] = []
    baseline_hashes: dict[Path, str] = {}
    staged_by_target: dict[Path, Path] = {}
    symbols = tuple(sorted(rows_by_symbol))
    bootstrap_symbols = _validated_missing_real_bootstrap_symbols(symbols)
    new_targets: set[Path] = set()
    for symbol in symbols:
        if not rows_by_symbol[symbol]:
            raise OhlcvRefreshTransactionError(
                f"refresh transaction received no rows for symbol: symbol={symbol}"
        )
        history_target = HISTORY_DIR / f"{symbol}.csv"
        real_target = REAL_DIR / f"{symbol}.csv"
        if not history_target.is_file():
            raise OhlcvRefreshTransactionError(
                f"history OHLCV copy is required before refresh: symbol={symbol}, "
                f"history_exists={history_target.is_file()}, real_exists={real_target.is_file()}"
            )
        history_hash = _file_sha256(history_target)
        if real_target.is_file():
            real_hash = _file_sha256(real_target)
            if history_hash != real_hash:
                raise OhlcvRefreshTransactionError(
                    f"OHLCV copies differ before refresh: symbol={symbol}, "
                    f"history_sha256={history_hash}, real_sha256={real_hash}"
                )
        elif symbol not in bootstrap_symbols:
            raise OhlcvRefreshTransactionError(
                f"missing real OHLCV copy is not authorized for bootstrap: symbol={symbol}"
            )
        _validate_serialized_rows(
            symbol,
            rows_by_symbol[symbol],
            _last_csv_date(history_target),
            maximum_completed_date,
        )
        source_by_target = {
            history_target: history_target,
            real_target: real_target if real_target.is_file() else history_target,
        }
        for target, source in source_by_target.items():
            staged = _staged_path(transaction_root, len(outputs))
            _stage_appended_csv(source, staged, rows_by_symbol[symbol])
            outputs.append((target, staged))
            staged_by_target[target] = staged
            if target.is_file():
                baseline_hashes[target] = _file_sha256(target)
            else:
                new_targets.add(target)

    return _stage_manifest_outputs(
        symbols,
        staged_by_target,
        outputs,
        baseline_hashes,
        frozenset(new_targets),
        updated_at_utc,
        transaction_root,
    )


def _stage_repair_outputs(
    candidate_csv_by_symbol: dict[str, bytes],
    expected_baseline_sha256_by_symbol: dict[str, str],
    updated_at_utc: datetime,
    transaction_root: Path,
) -> tuple[list[tuple[Path, Path]], dict[Path, str], frozenset[Path]]:
    outputs: list[tuple[Path, Path]] = []
    baseline_hashes: dict[Path, str] = {}
    staged_by_target: dict[Path, Path] = {}
    symbols = tuple(sorted(candidate_csv_by_symbol))
    if set(symbols) != set(expected_baseline_sha256_by_symbol):
        raise OhlcvRefreshTransactionError(
            "repair candidate and expected-baseline symbol sets must match: "
            f"candidate_symbols={list(symbols)}, "
            f"baseline_symbols={sorted(expected_baseline_sha256_by_symbol)}"
        )
    expected_header = b"date,symbol,open,high,low,close,adjusted_close,volume,source\n"
    for symbol in symbols:
        candidate = candidate_csv_by_symbol[symbol]
        if not candidate.startswith(expected_header) or not candidate.endswith(b"\n"):
            raise OhlcvRefreshTransactionError(
                f"repair candidate must use the canonical CSV header and trailing newline: symbol={symbol}"
            )
        try:
            candidate.decode("utf-8")
        except UnicodeDecodeError as error:
            raise OhlcvRefreshTransactionError(
                f"repair candidate is not UTF-8: symbol={symbol}, error={error}"
            ) from error
        history_target = HISTORY_DIR / f"{symbol}.csv"
        real_target = REAL_DIR / f"{symbol}.csv"
        if not history_target.is_file() or not real_target.is_file():
            raise OhlcvRefreshTransactionError(
                f"both OHLCV copies are required before repair: symbol={symbol}, "
                f"history_exists={history_target.is_file()}, real_exists={real_target.is_file()}"
            )
        history_hash = _file_sha256(history_target)
        real_hash = _file_sha256(real_target)
        if history_hash != real_hash:
            raise OhlcvRefreshTransactionError(
                f"OHLCV copies differ before repair: symbol={symbol}, "
                f"history_sha256={history_hash}, real_sha256={real_hash}"
            )
        expected_baseline = expected_baseline_sha256_by_symbol[symbol]
        if history_hash != expected_baseline:
            raise OhlcvRefreshTransactionError(
                f"OHLCV source changed after repair candidate preparation: symbol={symbol}, "
                f"expected_sha256={expected_baseline}, actual_sha256={history_hash}"
            )
        for target in (history_target, real_target):
            staged = _staged_path(transaction_root, len(outputs))
            _write_bytes_durable(staged, candidate)
            outputs.append((target, staged))
            staged_by_target[target] = staged
            baseline_hashes[target] = _file_sha256(target)
    return _stage_manifest_outputs(
        symbols,
        staged_by_target,
        outputs,
        baseline_hashes,
        frozenset(),
        updated_at_utc,
        transaction_root,
    )


def _validate_published_generation(symbols: frozenset[str]) -> dict[str, Any]:
    try:
        result = validate_history_dataset(HISTORY_MANIFEST_PATH, HISTORY_DIR, False)
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as error:
        raise OhlcvRefreshTransactionError(
            "full post-write history validation raised: "
            f"error={type(error).__name__}: {error}"
        ) from error
    if result.get("dataset_status") != "valid_real_dataset":
        error_codes = sorted(
            {
                str(flag.get("reason_code", "unknown"))
                for flag in result.get("quality_flags", [])
                if isinstance(flag, dict) and flag.get("severity") == "error"
            }
        )
        raise OhlcvRefreshTransactionError(
            "full post-write history validation failed: "
            f"dataset_status={result.get('dataset_status')!r}, error_codes={error_codes}"
        )
    history_manifest = _load_json_object(HISTORY_MANIFEST_PATH)
    pinned_hash = history_manifest.get("manifest_reproducibility_hash")
    actual_hash = history_manifest_hash(history_manifest)
    if pinned_hash != actual_hash:
        raise OhlcvRefreshTransactionError(
            f"post-write history manifest self-hash mismatch: pinned={pinned_hash!r}, actual={actual_hash}"
        )
    real_manifest = _load_json_object(REAL_MANIFEST_PATH)
    real_hashes = real_manifest.get("file_hashes")
    if not isinstance(real_hashes, dict):
        raise OhlcvRefreshTransactionError(
            f"post-write real-data manifest file_hashes must be an object: path={REAL_MANIFEST_PATH}"
        )
    for symbol in sorted(symbols):
        history_target = HISTORY_DIR / f"{symbol}.csv"
        real_target = REAL_DIR / f"{symbol}.csv"
        history_hash = _file_sha256(history_target)
        real_hash = _file_sha256(real_target)
        if history_hash != real_hash:
            raise OhlcvRefreshTransactionError(
                f"post-write OHLCV copies differ: symbol={symbol}, "
                f"history_sha256={history_hash}, real_sha256={real_hash}"
            )
        relative = f"dopey_data/real/raw/daily_ohlcv/{symbol}.csv"
        if real_hashes.get(relative) != real_hash:
            raise OhlcvRefreshTransactionError(
                f"post-write real-data manifest pin mismatch: symbol={symbol}, "
                f"pinned={real_hashes.get(relative)!r}, actual={real_hash}"
            )
    return result


def _restore_published_outputs(
    published: list[Path],
    backups: dict[Path, Path],
    baseline_hashes: dict[Path, str],
    new_targets: frozenset[Path],
) -> list[str]:
    errors: list[str] = []
    for target in reversed(published):
        try:
            if target in new_targets:
                target.unlink(missing_ok=False)
            else:
                os.replace(backups[target], target)
        except OSError as error:
            errors.append(f"restore_failed:path={target},error={type(error).__name__}:{error}")
    for target, expected_hash in baseline_hashes.items():
        try:
            actual_hash = _file_sha256(target)
        except OSError as error:
            errors.append(f"restore_verify_failed:path={target},error={type(error).__name__}:{error}")
            continue
        if actual_hash != expected_hash:
            errors.append(
                f"restore_hash_mismatch:path={target},expected={expected_hash},actual={actual_hash}"
            )
    for target in new_targets:
        if target.exists():
            errors.append(f"restore_unexpected_bootstrap_target:path={target}")
    return errors


def _publish_staged_outputs(
    outputs: list[tuple[Path, Path]],
    baseline_hashes: dict[Path, str],
    new_targets: frozenset[Path],
    transaction_root: Path,
    symbols: frozenset[str],
) -> dict[str, Any]:
    backups: dict[Path, Path] = {}
    for index, (target, _) in enumerate(outputs):
        if target in new_targets:
            if target.exists():
                raise OhlcvRefreshTransactionError(
                    f"bootstrap target appeared during staging: path={target}"
                )
            continue
        if _file_sha256(target) != baseline_hashes[target]:
            raise OhlcvRefreshTransactionError(
                f"transaction input changed during staging: path={target}"
            )
        backup = transaction_root / "backups" / f"{index:04d}.backup"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, backup)
        if _file_sha256(backup) != baseline_hashes[target]:
            raise OhlcvRefreshTransactionError(
                f"transaction backup verification failed: path={target}, backup={backup}"
            )
        backups[target] = backup
    published: list[Path] = []
    try:
        for target, staged in outputs:
            expected_hash = _file_sha256(staged)
            if target in new_targets:
                os.link(staged, target)
                published.append(target)
            else:
                published.append(target)
                os.replace(staged, target)
            actual_hash = _file_sha256(target)
            if actual_hash != expected_hash:
                raise OhlcvRefreshTransactionError(
                    f"atomic publish hash mismatch: path={target}, expected={expected_hash}, actual={actual_hash}"
                )
        return _validate_published_generation(symbols)
    except (OSError, OhlcvRefreshTransactionError) as error:
        rollback_errors = _restore_published_outputs(
            published,
            backups,
            baseline_hashes,
            new_targets,
        )
        if rollback_errors:
            raise OhlcvRefreshTransactionError(
                "OHLCV publish failed and exact rollback could not be proven: "
                f"publish_error={type(error).__name__}: {error}, rollback_errors={rollback_errors}"
            ) from error
        raise OhlcvRefreshTransactionError(
            "OHLCV publish failed; exact prior bytes and manifests were restored: "
            f"error={type(error).__name__}: {error}"
        ) from error


@contextmanager
def _exclusive_refresh_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner_id = uuid.uuid4().hex
    descriptor = _acquire_refresh_lock(lock_path, owner_id)
    ownership_recorded = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "created_at_utc": datetime.now(timezone.utc).isoformat(),
                        "owner_id": owner_id,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        ownership_recorded = True
        yield
    finally:
        if not ownership_recorded:
            lock_path.unlink(missing_ok=True)
        else:
            current_owner = _lock_owner_id(lock_path)
            if current_owner != owner_id:
                raise OhlcvRefreshTransactionError(
                    "OHLCV refresh lock ownership changed before release: "
                    f"path={lock_path}, expected_owner_id={owner_id}, "
                    f"observed_owner_id={current_owner!r}"
                )
            lock_path.unlink(missing_ok=False)


def _acquire_refresh_lock(lock_path: Path, owner_id: str) -> int:
    for _attempt in range(3):
        try:
            return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            if _existing_refresh_lock_is_active(lock_path):
                raise OhlcvRefreshTransactionError(
                    "OHLCV refresh lock belongs to a fresh live process: "
                    f"path={lock_path}"
                ) from error
            stale_path = lock_path.with_name(
                f"{lock_path.name}.stale."
                f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}."
                f"{os.getpid()}.{owner_id}"
            )
            try:
                os.replace(lock_path, stale_path)
            except FileNotFoundError:
                continue
            print(
                "OHLCV refresh stale-lock takeover: "
                f"path={lock_path}, preserved_as={stale_path}",
                flush=True,
            )
    raise OhlcvRefreshTransactionError(
        f"OHLCV refresh lock could not be acquired after stale-lock races: path={lock_path}"
    )


def _existing_refresh_lock_is_active(lock_path: Path) -> bool:
    now = datetime.now(timezone.utc)
    try:
        stat = lock_path.stat()
    except FileNotFoundError:
        return False
    try:
        record = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return now - modified <= INCOMPLETE_LOCK_GRACE
    if not isinstance(record, dict):
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return now - modified <= INCOMPLETE_LOCK_GRACE
    pid = record.get("pid")
    created_text = record.get("created_at_utc")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if not isinstance(created_text, str):
        return False
    try:
        created = datetime.fromisoformat(created_text.replace("Z", "+00:00"))
    except ValueError:
        return False
    if created.tzinfo is None:
        return False
    age = now - created.astimezone(timezone.utc)
    return age <= REFRESH_LOCK_STALE_AFTER and _process_is_alive(pid)


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _windows_process_is_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = open_process(process_query_limited_information, False, pid)
    if handle:
        close_handle(handle)
        return True
    error_code = ctypes.get_last_error()
    if error_code == 5:
        return True
    if error_code in {87, 1168}:
        return False
    return True


def _lock_owner_id(lock_path: Path) -> str | None:
    try:
        record = json.loads(lock_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    owner_id = record.get("owner_id")
    return owner_id if isinstance(owner_id, str) else None


def publish_refresh_transaction(
    rows_by_symbol: dict[str, list[str]],
    maximum_completed_date: date,
    updated_at_utc: datetime,
) -> dict[str, Any]:
    if updated_at_utc.tzinfo is None:
        raise ValueError("updated_at_utc must be timezone-aware")
    lock_path = HISTORY_MANIFEST_PATH.with_name(".operator_fetch_daily_ohlcv.lock")
    with _exclusive_refresh_lock(lock_path):
        if not rows_by_symbol:
            return _validate_published_generation(frozenset())
        with tempfile.TemporaryDirectory(
            prefix=".daily-ohlcv-transaction-",
            dir=HISTORY_MANIFEST_PATH.parent,
        ) as temporary_directory:
            transaction_root = Path(temporary_directory)
            outputs, baseline_hashes, new_targets = _stage_refresh_outputs(
                rows_by_symbol,
                maximum_completed_date,
                updated_at_utc,
                transaction_root,
            )
            return _publish_staged_outputs(
                outputs,
                baseline_hashes,
                new_targets,
                transaction_root,
                frozenset(rows_by_symbol),
            )


def publish_tail_repair_transaction(
    candidate_csv_by_symbol: dict[str, bytes],
    expected_baseline_sha256_by_symbol: dict[str, str],
    updated_at_utc: datetime,
) -> dict[str, Any]:
    if updated_at_utc.tzinfo is None:
        raise ValueError("updated_at_utc must be timezone-aware")
    if not candidate_csv_by_symbol:
        raise OhlcvRefreshTransactionError("tail repair transaction requires at least one candidate")
    lock_path = HISTORY_MANIFEST_PATH.with_name(".operator_fetch_daily_ohlcv.lock")
    with _exclusive_refresh_lock(lock_path):
        with tempfile.TemporaryDirectory(
            prefix=".daily-ohlcv-repair-transaction-",
            dir=HISTORY_MANIFEST_PATH.parent,
        ) as temporary_directory:
            transaction_root = Path(temporary_directory)
            outputs, baseline_hashes, new_targets = _stage_repair_outputs(
                candidate_csv_by_symbol,
                expected_baseline_sha256_by_symbol,
                updated_at_utc,
                transaction_root,
            )
            return _publish_staged_outputs(
                outputs,
                baseline_hashes,
                new_targets,
                transaction_root,
                frozenset(candidate_csv_by_symbol),
            )


def _core_symbols() -> frozenset[str]:
    """The governance floor. Registry probation names are welcome passengers;
    only CORE names may hold the frontier (a dead discovery must never freeze
    the spine - it gets quarantined instead)."""
    try:
        from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE

        return frozenset(REQUIRED_HISTORY_UNIVERSE)
    except Exception:  # noqa: BLE001 - operator lane: fail safe = everything is core
        return frozenset(path.stem for path in HISTORY_DIR.glob("*.csv"))


def _quarantine_probation(symbol: str, reason: str) -> None:
    try:
        from dopey_universe.universe_registry import load_registry, quarantine, save_registry

        registry = load_registry()
        if registry.get("symbols", {}).get(symbol, {}).get("tier") == "probation":
            save_registry(quarantine(registry, symbol, reason))
            print(f"{symbol}: PROBATION QUARANTINED ({reason}) - spine frontier protected", flush=True)
    except Exception as error:  # noqa: BLE001
        print(f"{symbol}: quarantine bookkeeping failed {type(error).__name__}", flush=True)


def main() -> int:
    completed_session = latest_completed_market_session(datetime.now(timezone.utc))
    print(
        f"latest completed XNYS session eligible for staging: {completed_session.isoformat()}",
        flush=True,
    )
    symbols = sorted(path.stem for path in HISTORY_DIR.glob("*.csv"))
    core = _core_symbols()
    pending: dict[str, tuple[str, list[tuple[str, str]]]] = {}
    core_failures = 0
    for symbol in symbols:
        try:
            pending[symbol] = collect_new_rows(symbol, completed_session)
            time.sleep(0.35)
        except Exception as error:  # noqa: BLE001 - operator lane: report and continue
            print(f"{symbol}: FAILED {type(error).__name__}: {error}", flush=True)
            if symbol in core:
                core_failures += 1
            else:
                # non-core (probation) death never freezes the spine: exclude
                # from the frontier computation and quarantine in the registry
                _quarantine_probation(symbol, f"fetch_failed_{type(error).__name__}")
    if core_failures == len([s for s in symbols if s in core]):
        print("ALL CORE OHLCV FETCHES FAILED - spine untouched", flush=True)
        return 1
    if core_failures > 0:
        # a CORE symbol we could not fetch pins the frontier at its staged
        # date; advancing without it would trip the validator's stale_symbol
        print(f"{core_failures} core symbols unfetchable - spine frontier held (uniform-advance invariant)", flush=True)
        return 1
    # UNIFORM-ADVANCE INVARIANT: the validator requires every symbol to reach the
    # dataset end date, so the spine only advances to the newest date every CORE
    # symbol can reach (a lagging ^VIX row holds the whole frontier for a day).
    # Probation names must keep up or be quarantined - they never hold it back.
    frontier = min(
        max((day for day, _ in rows), default=last_date)
        for symbol, (last_date, rows) in pending.items()
        if symbol in core
    )
    for symbol, (last_date, rows) in sorted(pending.items()):
        if symbol in core:
            continue
        reach = max((day for day, _ in rows), default=last_date)
        if reach < frontier:
            _quarantine_probation(symbol, f"frontier_lag_reach_{reach}_vs_{frontier}")
            pending.pop(symbol, None)
    touched_rows: dict[str, list[str]] = {}
    for symbol, (last_date, rows) in sorted(pending.items()):
        eligible = [line for day, line in rows if day <= frontier]
        if eligible:
            touched_rows[symbol] = eligible
            print(f"{symbol}: +{len(eligible)} bars (to {frontier})", flush=True)
    validation = publish_refresh_transaction(
        touched_rows,
        date.fromisoformat(frontier),
        datetime.now(timezone.utc),
    )
    if touched_rows:
        print(
            f"spine advanced to {frontier}: {len(touched_rows)} symbols, "
            "copies/manifests transactionally published",
            flush=True,
        )
    else:
        print(f"spine already current at frontier {frontier} (no uniform advance available)", flush=True)
    print(
        "full post-write history validation passed: "
        f"dataset_status={validation['dataset_status']}, "
        f"row_count={validation['validation']['row_count']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
