"""Validate hash-pinned offline daily OHLCV history datasets."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dopey_core.market_calendar import is_trading_day

from .history_models import (
    ALLOWED_HISTORY_FORMATS,
    HISTORY_DATASET_VERSION,
    HISTORY_VALIDATOR_VERSION,
    OPTIONAL_HISTORY_COLUMNS,
    REQUIRED_HISTORY_COLUMNS,
    REQUIRED_HISTORY_UNIVERSE,
    HistoryBar,
    HistoryDatasetManifest,
    HistoryDatasetValidation,
    HistoryLoaderProof,
    HistoryQualityFlag,
    HistorySymbolCoverage,
    history_manifest_hash,
    normalize_history_symbol,
    stable_history_hash,
)
from .history_store import (
    HISTORY_MANIFEST_PATH,
    HISTORY_RAW_DIR,
    HistoryDatasetError,
    file_sha256,
    load_history_manifest,
    load_raw_history_records,
    resolve_history_data_file_path,
)


REAL_DATA_STATUSES: tuple[str, ...] = ("valid_real_dataset", "invalid_real_dataset", "missing_real_dataset")


def placeholder_history_manifest_record(raw_dir: Path | str) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    record: dict[str, Any] = {
        "artifact_type": "history_dataset_manifest",
        "history_dataset_manifest_version": HISTORY_DATASET_VERSION,
        "dataset_id": "dopey-offline-daily-ohlcv-history-v1",
        "dataset_status": "missing_real_dataset",
        "raw_data_directory": raw_path.as_posix(),
        "required_universe": list(REQUIRED_HISTORY_UNIVERSE),
        "required_columns": list(REQUIRED_HISTORY_COLUMNS),
        "optional_columns": list(OPTIONAL_HISTORY_COLUMNS),
        "allowed_formats": list(ALLOWED_HISTORY_FORMATS),
        "data_files": [],
        "generated_real_data": False,
        "network_fetch_performed": False,
        "credential_required": False,
        "paper_only": True,
        "live_blocked": True,
        "manifest_reproducibility_hash": "",
    }
    record["manifest_reproducibility_hash"] = history_manifest_hash(record)
    return record


def write_placeholder_history_manifest(manifest_path: Path | str, raw_dir: Path | str) -> Path:
    target = Path(manifest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    record = placeholder_history_manifest_record(raw_dir)
    target.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def validate_history_dataset(
    manifest_path: Path | str,
    raw_dir: Path | str,
    write_placeholder_manifest_if_missing: bool,
) -> dict[str, Any]:
    manifest_target = Path(manifest_path)
    raw_target = Path(raw_dir)
    if write_placeholder_manifest_if_missing:
        raw_target.mkdir(parents=True, exist_ok=True)
        if not manifest_target.exists():
            write_placeholder_history_manifest(manifest_target, raw_target)
    flags: list[HistoryQualityFlag] = []
    file_hashes: dict[str, str] = {}
    bars: list[HistoryBar] = []
    duplicate_count = 0
    manifest_record = placeholder_history_manifest_record(raw_target)
    manifest: HistoryDatasetManifest | None = None
    manifest_loaded = False
    file_missing_count = 0
    data_file_count = 0

    if not manifest_target.exists():
        flags.append(_flag("manifest_missing", "error", "", "", str(manifest_target), 0, "manifest_missing", "expected history dataset manifest is missing"))
    else:
        try:
            manifest = load_history_manifest(manifest_target)
            manifest_record = manifest.to_dict()
            manifest_loaded = True
        except (HistoryDatasetError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            flags.append(_flag("manifest_parse_error", "error", "", "", str(manifest_target), 0, "manifest_parse_error", str(exc)))

    if manifest is not None:
        data_file_count = len(manifest.data_files)
        flags.extend(_manifest_safety_flags(manifest, str(manifest_target)))
        if not manifest.data_files:
            flags.append(_flag("data_files_missing", "error", "", "", str(manifest_target), 0, "data_files_missing", "manifest contains no hash-pinned data files"))
        for file_ref in manifest.data_files:
            try:
                path = resolve_history_data_file_path(
                    manifest_target,
                    manifest,
                    file_ref,
                )
            except HistoryDatasetError as exc:
                flags.append(
                    _flag(
                        f"manifest_path_containment_{len(flags)}",
                        "error",
                        "",
                        "",
                        file_ref.path,
                        0,
                        "manifest_path_containment",
                        str(exc),
                    )
                )
                continue
            if file_ref.format not in ALLOWED_HISTORY_FORMATS:
                flags.append(_flag(f"unsupported_format_{len(flags)}", "error", "", "", str(path), 0, "unsupported_format", file_ref.format))
                continue
            if not path.exists():
                file_missing_count += 1
                flags.append(_flag(f"data_file_missing_{len(flags)}", "error", "", "", str(path), 0, "data_file_missing", "manifest data file is missing"))
                continue
            actual_hash = file_sha256(path)
            file_hashes[str(path)] = actual_hash
            if not file_ref.sha256:
                flags.append(_flag(f"missing_hash_pin_{len(flags)}", "error", "", "", str(path), 0, "missing_hash_pin", "manifest data file has no sha256 pin"))
            elif actual_hash.lower() != file_ref.sha256.lower():
                flags.append(_flag(f"hash_mismatch_{len(flags)}", "error", "", "", str(path), 0, "hash_mismatch", "manifest sha256 does not match data file"))
            try:
                records = load_raw_history_records(path, file_ref.format)
            except (HistoryDatasetError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                flags.append(_flag(f"data_file_parse_error_{len(flags)}", "error", "", "", str(path), 0, "data_file_parse_error", str(exc)))
                continue
            parsed_bars, record_flags = _parse_records(path, records)
            bars.extend(parsed_bars)
            flags.extend(record_flags)

    duplicate_count = _append_duplicate_flags(bars, flags)
    coverage_records = _build_coverage_records(bars, list(REQUIRED_HISTORY_UNIVERSE))
    flags.extend(_coverage_flags(coverage_records))
    status = _dataset_status(manifest_loaded, data_file_count, file_missing_count, bars, flags)
    validation_record = _build_validation_record(status, manifest_record, bars, coverage_records, flags, duplicate_count, data_file_count, file_hashes, manifest_target, raw_target)
    proof_record = _build_loader_proof(status, validation_record, coverage_records, manifest_target, raw_target)
    summary_record = _build_summary_record(status, validation_record, coverage_records, flags)
    return {
        "dataset_status": status,
        "manifest": manifest_record,
        "validation": validation_record,
        "coverage_records": [record.to_dict() for record in coverage_records],
        "quality_flags": [flag.to_dict() for flag in flags],
        "loader_proof": [proof_record],
        "summary": summary_record,
        "bars_loaded": [bar.to_dict() for bar in bars],
    }


def validate_default_history_dataset() -> dict[str, Any]:
    return validate_history_dataset(HISTORY_MANIFEST_PATH, HISTORY_RAW_DIR, True)


def _parse_records(path: Path, records: list[dict[str, Any]]) -> tuple[list[HistoryBar], list[HistoryQualityFlag]]:
    bars: list[HistoryBar] = []
    flags: list[HistoryQualityFlag] = []
    for index, record in enumerate(records, start=2):
        missing_columns = [column for column in REQUIRED_HISTORY_COLUMNS if column not in record]
        if missing_columns:
            flags.append(_flag(f"missing_required_column_{len(flags)}", "error", "", "", str(path), index, "missing_required_column", ",".join(missing_columns)))
            continue
        try:
            bar = HistoryBar.from_dict(record)
        except (KeyError, TypeError, ValueError) as exc:
            flags.append(_flag(f"record_parse_error_{len(flags)}", "error", str(record.get("symbol", "")), str(record.get("date", "")), str(path), index, "record_parse_error", str(exc)))
            continue
        row_flags = _bar_quality_flags(bar, path, index)
        if row_flags:
            flags.extend(row_flags)
            continue
        bars.append(bar)
    return bars, flags


def _bar_quality_flags(bar: HistoryBar, path: Path, row_number: int) -> list[HistoryQualityFlag]:
    flags: list[HistoryQualityFlag] = []
    named_values = {
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "adjusted_close": bar.adjusted_close,
    }
    nonfinite_fields = sorted(
        field for field, value in named_values.items() if not math.isfinite(value)
    )
    if nonfinite_fields:
        flags.append(
            _flag(
                f"ohlcv_nonfinite_{row_number}",
                "error",
                bar.symbol,
                bar.date,
                str(path),
                row_number,
                "ohlcv_nonfinite",
                f"OHLCV price fields must be finite: {','.join(nonfinite_fields)}",
            )
        )
        return flags
    values = [bar.open, bar.high, bar.low, bar.close]
    if any(value <= 0 for value in values):
        flags.append(_flag(f"ohlc_nonpositive_{row_number}", "error", bar.symbol, bar.date, str(path), row_number, "ohlc_nonpositive", "OHLC values must be positive"))
    if bar.adjusted_close <= 0:
        flags.append(_flag(f"adjusted_close_nonpositive_{row_number}", "error", bar.symbol, bar.date, str(path), row_number, "adjusted_close_nonpositive", "adjusted_close must be positive"))
    if bar.high < max(bar.open, bar.close, bar.low):
        flags.append(_flag(f"high_below_ohlc_{row_number}", "error", bar.symbol, bar.date, str(path), row_number, "high_below_ohlc", "high must be >= open, close, and low"))
    if bar.low > min(bar.open, bar.close, bar.high):
        flags.append(_flag(f"low_above_ohlc_{row_number}", "error", bar.symbol, bar.date, str(path), row_number, "low_above_ohlc", "low must be <= open, close, and high"))
    if bar.volume < 0:
        flags.append(_flag(f"volume_negative_{row_number}", "error", bar.symbol, bar.date, str(path), row_number, "volume_negative", "volume must be nonnegative"))
    if _declares_placeholder_source(bar.source):
        flags.append(_flag(f"placeholder_source_{row_number}", "error", bar.symbol, bar.date, str(path), row_number, "source_declares_fixture_or_synthetic", "history row source is fixture, synthetic, sample, or placeholder"))
    return flags


def _append_duplicate_flags(bars: list[HistoryBar], flags: list[HistoryQualityFlag]) -> int:
    seen: set[tuple[str, str]] = set()
    duplicate_count = 0
    for bar in bars:
        key = (bar.symbol, bar.date)
        if key in seen:
            duplicate_count += 1
            flags.append(_flag(f"duplicate_symbol_date_{duplicate_count}", "error", bar.symbol, bar.date, "", 0, "duplicate_symbol_date", "duplicate symbol/date row"))
        seen.add(key)
    return duplicate_count


def _build_coverage_records(bars: list[HistoryBar], required_symbols: list[str]) -> list[HistorySymbolCoverage]:
    by_symbol: dict[str, list[HistoryBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[normalize_history_symbol(bar.symbol)].append(bar)
    all_dates = [date.fromisoformat(bar.date) for bar in bars]
    dataset_end = max(all_dates).isoformat() if all_dates else ""
    records: list[HistorySymbolCoverage] = []
    for symbol in required_symbols:
        symbol_bars = by_symbol.get(symbol, [])
        dates = sorted({date.fromisoformat(bar.date) for bar in symbol_bars})
        first_date = dates[0].isoformat() if dates else ""
        last_date = dates[-1].isoformat() if dates else ""
        expected_sessions = _trading_days_between(dates[0], dates[-1]) if dates else []
        observed_dates = set(dates)
        missing_dates = [
            item.isoformat()
            for item in expected_sessions
            if item not in observed_dates
        ]
        missing = not bool(symbol_bars)
        stale = bool(dataset_end and last_date and last_date < dataset_end)
        if missing:
            coverage_status = "missing_symbol"
        elif stale:
            coverage_status = "stale_symbol"
        elif missing_dates:
            coverage_status = "missing_days"
        else:
            coverage_status = "covered"
        records.append(HistorySymbolCoverage(
            artifact_type="history_symbol_coverage",
            symbol=symbol,
            row_count=len(symbol_bars),
            first_date=first_date,
            last_date=last_date,
            date_coverage_count=len(dates),
            expected_weekday_count=len(expected_sessions),
            missing_weekday_count=len(missing_dates),
            missing_dates=missing_dates,
            stale=stale,
            missing=missing,
            coverage_status=coverage_status,
            coverage_hash="",
        ))
    return records


def _coverage_flags(coverage_records: list[HistorySymbolCoverage]) -> list[HistoryQualityFlag]:
    flags: list[HistoryQualityFlag] = []
    for record in coverage_records:
        if record.missing:
            flags.append(_flag(f"missing_symbol_{record.symbol}", "error", record.symbol, "", "", 0, "missing_symbol", "required history symbol is missing"))
        elif record.stale:
            flags.append(_flag(f"stale_symbol_{record.symbol}", "error", record.symbol, record.last_date, "", 0, "stale_symbol", "symbol ends before dataset end date"))
        if record.missing_weekday_count > 0:
            flags.append(
                _flag(
                    f"missing_trading_sessions_{record.symbol}",
                    "error",
                    record.symbol,
                    "",
                    "",
                    0,
                    "missing_trading_sessions",
                    f"{record.missing_weekday_count} XNYS sessions missing inside symbol date range",
                )
            )
    return flags


def _dataset_status(
    manifest_loaded: bool,
    data_file_count: int,
    file_missing_count: int,
    bars: list[HistoryBar],
    flags: list[HistoryQualityFlag],
) -> str:
    invalid_manifest_codes = {
        "manifest_parse_error",
        "generated_real_data_forbidden",
        "network_fetch_forbidden",
        "source_declares_fixture_or_synthetic",
    }
    if any(flag.reason_code in invalid_manifest_codes for flag in flags):
        return "invalid_real_dataset"
    if not manifest_loaded or data_file_count == 0:
        return "missing_real_dataset"
    if file_missing_count == data_file_count and not bars:
        return "missing_real_dataset"
    has_errors = any(flag.severity == "error" for flag in flags)
    return "invalid_real_dataset" if has_errors else "valid_real_dataset"


def _build_validation_record(
    status: str,
    manifest_record: dict[str, Any],
    bars: list[HistoryBar],
    coverage_records: list[HistorySymbolCoverage],
    flags: list[HistoryQualityFlag],
    duplicate_count: int,
    data_file_count: int,
    file_hashes: dict[str, str],
    manifest_path: Path,
    raw_dir: Path,
) -> dict[str, Any]:
    unique_dates = sorted({bar.date for bar in bars})
    missing_symbols = [record for record in coverage_records if record.missing]
    stale_symbols = [record for record in coverage_records if record.stale]
    validation = HistoryDatasetValidation(
        artifact_type="history_dataset_validation",
        history_validator_version=HISTORY_VALIDATOR_VERSION,
        dataset_status=status,
        row_count=len(bars),
        required_symbol_count=len(REQUIRED_HISTORY_UNIVERSE),
        covered_symbol_count=sum(1 for record in coverage_records if not record.missing),
        date_coverage_count=len(unique_dates),
        start_date=unique_dates[0] if unique_dates else "",
        end_date=unique_dates[-1] if unique_dates else "",
        missing_symbol_count=len(missing_symbols),
        stale_symbol_count=len(stale_symbols),
        duplicate_count=duplicate_count,
        quality_flag_count=len(flags),
        data_file_count=data_file_count,
        file_hashes=file_hashes,
        manifest_reproducibility_hash=str(manifest_record.get("manifest_reproducibility_hash", "")),
        validation_reproducibility_hash="",
        expected_raw_directory=str(raw_dir),
        expected_manifest_path=str(manifest_path),
        paper_only=True,
        live_blocked=True,
        no_broker=True,
        no_scheduler=True,
        no_real_sizing=True,
    )
    return validation.to_dict()


def _build_loader_proof(
    status: str,
    validation_record: dict[str, Any],
    coverage_records: list[HistorySymbolCoverage],
    manifest_path: Path,
    raw_dir: Path,
) -> dict[str, Any]:
    missing_symbols = [record.symbol for record in coverage_records if record.missing]
    invalid_symbols = [record.symbol for record in coverage_records if record.coverage_status not in {"covered", "missing_symbol"}]
    proof = HistoryLoaderProof(
        artifact_type="history_loader_proof",
        proof_id=f"history-loader-proof-{stable_history_hash(validation_record)[:12]}",
        dataset_status=status,
        manifest_path=str(manifest_path),
        raw_data_directory=str(raw_dir),
        data_file_count=int(validation_record["data_file_count"]),
        rows_loaded=int(validation_record["row_count"]),
        file_hashes=dict(validation_record["file_hashes"]),
        missing_symbols=missing_symbols,
        invalid_symbols=invalid_symbols,
        paper_only=True,
        live_blocked=True,
        no_broker=True,
        no_scheduler=True,
        no_real_sizing=True,
        proof_hash="",
    )
    return proof.to_dict()


def _build_summary_record(
    status: str,
    validation_record: dict[str, Any],
    coverage_records: list[HistorySymbolCoverage],
    flags: list[HistoryQualityFlag],
) -> dict[str, Any]:
    summary = {
        "artifact_type": "history_spine_summary",
        "history_spine_version": HISTORY_DATASET_VERSION,
        "dataset_status": status,
        "real_local_data_found": status != "missing_real_dataset",
        "row_count": validation_record["row_count"],
        "symbols_covered": [record.symbol for record in coverage_records if not record.missing],
        "symbols_missing": [record.symbol for record in coverage_records if record.missing],
        "symbols_stale": [record.symbol for record in coverage_records if record.stale],
        "date_range": {
            "start_date": validation_record["start_date"],
            "end_date": validation_record["end_date"],
        },
        "quality_flags": sorted({flag.reason_code for flag in flags}),
        "manifest_path": validation_record["expected_manifest_path"],
        "artifact_paths": {
            "history_dataset_manifest": "artifacts/dopey/history/history_dataset_manifest.json",
            "history_dataset_validation": "artifacts/dopey/history/history_dataset_validation.json",
            "history_symbol_coverage": "artifacts/dopey/history/history_symbol_coverage.jsonl",
            "history_quality_flags": "artifacts/dopey/history/history_quality_flags.jsonl",
            "history_loader_proof": "artifacts/dopey/history/history_loader_proof.jsonl",
            "history_spine_summary": "artifacts/dopey/history/history_spine_summary.json",
        },
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "next_recommended_target": "DOPEY_MODEL_REPRICER_V1",
    }
    summary["reproducibility_hash"] = stable_history_hash(summary)
    return summary


def _manifest_safety_flags(manifest: HistoryDatasetManifest, manifest_path: str) -> list[HistoryQualityFlag]:
    flags: list[HistoryQualityFlag] = []
    if manifest.generated_real_data:
        flags.append(_flag("generated_real_data_forbidden", "error", "", "", manifest_path, 0, "generated_real_data_forbidden", "manifest declares generated real data"))
    if manifest.network_fetch_performed:
        flags.append(_flag("network_fetch_forbidden", "error", "", "", manifest_path, 0, "network_fetch_forbidden", "history bundle only supports local offline files"))
    for file_ref in manifest.data_files:
        if _declares_placeholder_source(file_ref.source) or _declares_placeholder_source(file_ref.path):
            flags.append(_flag(f"placeholder_file_source_{len(flags)}", "error", "", "", file_ref.path, 0, "source_declares_fixture_or_synthetic", "manifest data file source is fixture, synthetic, sample, or placeholder"))
    return flags


def _declares_placeholder_source(value: str) -> bool:
    lowered = value.lower()
    tokens = ("synthetic", "fixture", "sample", "placeholder", "fake")
    return any(token in lowered for token in tokens)


def _trading_days_between(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if is_trading_day(cursor):
            days.append(cursor)
        cursor = cursor + timedelta(days=1)
    return days


def _flag(
    flag_id: str,
    severity: str,
    symbol: str,
    flag_date: str,
    path: str,
    row_number: int,
    reason_code: str,
    message: str,
) -> HistoryQualityFlag:
    return HistoryQualityFlag(
        artifact_type="history_quality_flag",
        flag_id=flag_id,
        severity=severity,
        symbol=normalize_history_symbol(symbol) if symbol else "",
        date=flag_date,
        path=path,
        row_number=row_number,
        reason_code=reason_code,
        message=message,
        flag_hash="",
    )
