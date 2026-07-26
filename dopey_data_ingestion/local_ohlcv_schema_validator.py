"""Schema validation for manually staged local OHLCV files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .local_ohlcv_file_inventory import LocalOhlcvParsedFile, read_local_ohlcv_file, repo_relative_path
from .local_ohlcv_import_models import LOCAL_OHLCV_IMPORT_VERSION, LocalOhlcvSchemaResult, stable_local_ohlcv_hash


REQUIRED_DAILY_OHLCV_COLUMNS: tuple[str, ...] = ("date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume")
OPTIONAL_DAILY_OHLCV_COLUMNS: tuple[str, ...] = ("source", "dividend", "split_factor", "sample_only", "not_real_data")
REQUIRED_MARKET_CONTEXT_COLUMNS: tuple[str, ...] = REQUIRED_DAILY_OHLCV_COLUMNS
REQUIRED_CORPORATE_ACTION_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "action_type",
    "split_ratio",
    "dividend_amount",
    "source",
    "provider_record_id",
)
ACCEPTED_FILE_FORMATS: frozenset[str] = frozenset({".csv", ".jsonl"})


def validate_schema_records(parsed_files: list[LocalOhlcvParsedFile]) -> list[dict[str, Any]]:
    return [validate_parsed_schema(parsed).to_dict() for parsed in parsed_files]


def validate_schema_path(path: Path, dataset_family: str) -> dict[str, Any]:
    return validate_parsed_schema(read_local_ohlcv_file(path, dataset_family)).to_dict()


def validate_parsed_schema(parsed: LocalOhlcvParsedFile) -> LocalOhlcvSchemaResult:
    required = required_columns_for_family(parsed.dataset_family)
    accepted = set(required) | set(optional_columns_for_family(parsed.dataset_family))
    headers = set(parsed.header_columns)
    missing = [column for column in required if column not in headers]
    extra = sorted(column for column in headers if column not in accepted)
    reasons: list[str] = []
    if parsed.path.suffix.lower() not in ACCEPTED_FILE_FORMATS:
        reasons.append("unsupported_file_format")
    if missing:
        reasons.append("missing_required_columns")
    if parsed.malformed_rows > 0:
        reasons.append("malformed_rows")
    if not parsed.header_columns:
        reasons.append("missing_header")
    schema_pass = not reasons
    relative = repo_relative_path(parsed.path)
    return LocalOhlcvSchemaResult(
        artifact_type="local_ohlcv_schema_results",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        result_id=f"schema-{stable_local_ohlcv_hash({'path': relative})[:12]}",
        dataset_family=parsed.dataset_family,
        local_file_path=relative,
        required_columns_present=not missing,
        missing_columns=missing,
        extra_columns=extra,
        parseable_rows=len(parsed.rows),
        malformed_rows=parsed.malformed_rows,
        schema_pass=schema_pass,
        reason_codes=reasons,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        schema_hash="",
    )


def required_columns_for_family(dataset_family: str) -> tuple[str, ...]:
    if dataset_family == "corporate_actions":
        return REQUIRED_CORPORATE_ACTION_COLUMNS
    if dataset_family == "market_context":
        return REQUIRED_MARKET_CONTEXT_COLUMNS
    return REQUIRED_DAILY_OHLCV_COLUMNS


def optional_columns_for_family(dataset_family: str) -> tuple[str, ...]:
    if dataset_family == "corporate_actions":
        return tuple()
    return OPTIONAL_DAILY_OHLCV_COLUMNS
