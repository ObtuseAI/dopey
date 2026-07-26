"""Quality gates for manually staged local OHLCV files."""
from __future__ import annotations

from datetime import date
from typing import Any

from .local_ohlcv_file_inventory import (
    LocalOhlcvParsedFile,
    credential_token_found,
    forbidden_live_marker_found,
    parse_date,
    parse_float,
    repo_relative_path,
    sample_row_is_blocked,
)
from .local_ohlcv_import_models import LOCAL_OHLCV_IMPORT_VERSION, LocalOhlcvQualityResult, stable_local_ohlcv_hash


def validate_quality_records(parsed_files: list[LocalOhlcvParsedFile], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [validate_parsed_quality(parsed, manifest).to_dict() for parsed in parsed_files]


def validate_parsed_quality(parsed: LocalOhlcvParsedFile, manifest: dict[str, Any]) -> LocalOhlcvQualityResult:
    if parsed.dataset_family == "corporate_actions":
        return _corporate_action_quality(parsed)
    rows = parsed.rows
    reasons: list[str] = []
    row_count = len(rows)
    parsed_dates = [parse_date(row.get("date", "")) for row in rows]
    invalid_date_count = sum(1 for item in parsed_dates if item is None)
    future_date_count = sum(1 for item in parsed_dates if item is not None and item > date.today())
    duplicate_count = _duplicate_symbol_date_count(rows)
    sample_count = sum(1 for row in rows if sample_row_is_blocked(row))
    fake_symbol_count = sum(1 for row in rows if row.get("symbol", "").strip().upper() == "SAMPLE_ONLY")
    not_real_data_count = sum(1 for row in rows if row.get("not_real_data", "").strip().lower() == "true")
    positive_ohlc = all(_all_positive(row, ("open", "high", "low", "close")) for row in rows)
    adjusted_positive = all((parse_float(row.get("adjusted_close")) or 0.0) > 0.0 for row in rows)
    volume_nonnegative = all(_volume_value(row) >= 0.0 for row in rows)
    high_low_consistent = all(_high_low_consistent(row) for row in rows)
    symbols = sorted({row.get("symbol", "").strip().upper() for row in rows if row.get("symbol", "").strip()})
    source_missing = _source_missing_count(rows, manifest)
    token_found = credential_token_found(parsed.text)
    live_marker_found = forbidden_live_marker_found(parsed.text)
    if row_count == 0:
        reasons.append("empty_file")
    if invalid_date_count > 0:
        reasons.append("invalid_date")
    if future_date_count > 0:
        reasons.append("future_date")
    if duplicate_count > 0:
        reasons.append("duplicate_date_symbol")
    if any(not row.get("symbol", "").strip() for row in rows):
        reasons.append("missing_symbol")
    if fake_symbol_count > 0:
        reasons.append("sample_only_symbol")
    if sample_count > 0:
        reasons.append("sample_template_contamination")
    if not_real_data_count > 0:
        reasons.append("not_real_data_row")
    if not positive_ohlc:
        reasons.append("nonpositive_ohlc")
    if not adjusted_positive:
        reasons.append("nonpositive_adjusted_close")
    if not volume_nonnegative:
        reasons.append("negative_volume")
    if not high_low_consistent:
        reasons.append("high_low_inconsistency")
    if source_missing > 0:
        reasons.append("missing_source")
    if token_found:
        reasons.append("credential_or_token_contamination")
    if live_marker_found:
        reasons.append("broker_live_order_scheduler_real_sizing_contamination")
    terminal = token_found or live_marker_found
    status = "terminal_block" if terminal else ("quality_pass" if not reasons else "quality_fail")
    dates = sorted(item.isoformat() for item in parsed_dates if item is not None)
    relative = repo_relative_path(parsed.path)
    return LocalOhlcvQualityResult(
        artifact_type="local_ohlcv_quality_results",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        result_id=f"quality-{stable_local_ohlcv_hash({'path': relative})[:12]}",
        dataset_family=parsed.dataset_family,
        local_file_path=relative,
        status=status,
        positive_ohlc=positive_ohlc,
        high_low_consistent=high_low_consistent,
        adjusted_close_positive=adjusted_positive,
        volume_nonnegative=volume_nonnegative,
        duplicate_symbol_date_count=duplicate_count,
        row_count=row_count,
        date_range={"start": dates[0], "end": dates[-1]} if dates else {},
        symbol_coverage=symbols,
        missing_day_count=_missing_day_count(rows),
        stale_symbol_count=0,
        future_date_count=future_date_count,
        sample_only_row_count=sample_count,
        fake_symbol_count=fake_symbol_count,
        not_real_data_row_count=not_real_data_count,
        credential_token_found=token_found,
        broker_live_order_scheduler_real_sizing_found=live_marker_found,
        source_field_missing_count=source_missing,
        reason_codes=reasons,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        quality_hash="",
    )


def _corporate_action_quality(parsed: LocalOhlcvParsedFile) -> LocalOhlcvQualityResult:
    rows = parsed.rows
    reasons: list[str] = []
    invalid_date_count = sum(1 for row in rows if parse_date(row.get("date", "")) is None)
    future_date_count = sum(1 for row in rows if (parse_date(row.get("date", "")) or date.min) > date.today())
    token_found = credential_token_found(parsed.text)
    live_marker_found = forbidden_live_marker_found(parsed.text)
    if not rows:
        reasons.append("empty_file")
    if invalid_date_count:
        reasons.append("invalid_date")
    if future_date_count:
        reasons.append("future_date")
    if any(not row.get("symbol", "").strip() for row in rows):
        reasons.append("missing_symbol")
    if any(not row.get("action_type", "").strip() for row in rows):
        reasons.append("missing_action_type")
    if any(row.get("split_ratio", "").strip() and parse_float(row.get("split_ratio")) is None for row in rows):
        reasons.append("invalid_split_ratio")
    if any(row.get("dividend_amount", "").strip() and parse_float(row.get("dividend_amount")) is None for row in rows):
        reasons.append("invalid_dividend_amount")
    if any(not row.get("source", "").strip() for row in rows):
        reasons.append("missing_source")
    if any(not row.get("provider_record_id", "").strip() for row in rows):
        reasons.append("missing_provider_record_id")
    if token_found:
        reasons.append("credential_or_token_contamination")
    if live_marker_found:
        reasons.append("broker_live_order_scheduler_real_sizing_contamination")
    terminal = token_found or live_marker_found
    relative = repo_relative_path(parsed.path)
    return LocalOhlcvQualityResult(
        artifact_type="local_ohlcv_quality_results",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        result_id=f"quality-{stable_local_ohlcv_hash({'path': relative})[:12]}",
        dataset_family=parsed.dataset_family,
        local_file_path=relative,
        status="terminal_block" if terminal else ("quality_pass" if not reasons else "quality_fail"),
        positive_ohlc=True,
        high_low_consistent=True,
        adjusted_close_positive=True,
        volume_nonnegative=True,
        duplicate_symbol_date_count=0,
        row_count=len(rows),
        date_range={},
        symbol_coverage=sorted({row.get("symbol", "").strip().upper() for row in rows if row.get("symbol", "").strip()}),
        missing_day_count=0,
        stale_symbol_count=0,
        future_date_count=future_date_count,
        sample_only_row_count=sum(1 for row in rows if sample_row_is_blocked(row)),
        fake_symbol_count=sum(1 for row in rows if row.get("symbol", "").strip().upper() == "SAMPLE_ONLY"),
        not_real_data_row_count=sum(1 for row in rows if row.get("not_real_data", "").strip().lower() == "true"),
        credential_token_found=token_found,
        broker_live_order_scheduler_real_sizing_found=live_marker_found,
        source_field_missing_count=sum(1 for row in rows if not row.get("source", "").strip()),
        reason_codes=reasons,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        quality_hash="",
    )


def _volume_value(row: dict[str, str]) -> float:
    parsed = parse_float(row.get("volume"))
    return parsed if parsed is not None else -1.0


def _all_positive(row: dict[str, str], columns: tuple[str, ...]) -> bool:
    values = [parse_float(row.get(column)) for column in columns]
    return all(value is not None and value > 0.0 for value in values)


def _high_low_consistent(row: dict[str, str]) -> bool:
    high = parse_float(row.get("high"))
    low = parse_float(row.get("low"))
    open_value = parse_float(row.get("open"))
    close = parse_float(row.get("close"))
    if high is None or low is None or open_value is None or close is None:
        return False
    return high >= open_value and high >= close and high >= low and low <= open_value and low <= close and low <= high


def _duplicate_symbol_date_count(rows: list[dict[str, str]]) -> int:
    seen: set[tuple[str, str]] = set()
    duplicates = 0
    for row in rows:
        key = (row.get("date", "").strip(), row.get("symbol", "").strip().upper())
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def _missing_day_count(rows: list[dict[str, str]]) -> int:
    by_symbol: dict[str, list[date]] = {}
    for row in rows:
        parsed = parse_date(row.get("date", ""))
        symbol = row.get("symbol", "").strip().upper()
        if parsed is not None and symbol:
            by_symbol.setdefault(symbol, []).append(parsed)
    missing = 0
    for dates in by_symbol.values():
        ordered = sorted(set(dates))
        for earlier, later in zip(ordered, ordered[1:]):
            gap = (later - earlier).days
            if gap > 4:
                missing += gap - 1
    return missing


def _source_missing_count(rows: list[dict[str, str]], manifest: dict[str, Any]) -> int:
    if manifest.get("provider_name") and manifest.get("provider_name") != "TEMPLATE_ONLY":
        return 0
    return sum(1 for row in rows if not row.get("source", "").strip())
