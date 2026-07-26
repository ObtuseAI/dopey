"""Typed models for DOPEY offline daily OHLCV history datasets."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


HISTORY_DATASET_VERSION = "dopey-real-data-backtest-spine-v1"
HISTORY_VALIDATOR_VERSION = "dopey-history-dataset-validator-v2"
REQUIRED_HISTORY_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)
OPTIONAL_HISTORY_COLUMNS: tuple[str, ...] = ("dividend", "split_factor", "source")
ALLOWED_HISTORY_FORMATS: tuple[str, ...] = ("csv", "jsonl")
REQUIRED_HISTORY_UNIVERSE: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    # crypto-linked listed names (2026-07-10): BTC ETF + treasury company +
    # exchange - among the most liquid high-IV options chains in the market
    "IBIT",
    "MSTR",
    "COIN",
    # short-candidate expansion (2026-07-10): the fundamentals screen's first
    # flagged cohort (EV/quantum/AI/crypto themes, >=3 excess flags, cap>=1e9)
    # staged in-universe so the PUT side can express the screen ex-ante; the
    # screen stays a research flag - entries remain signal+context gated
    "AI",
    "BBAI",
    "CLSK",
    "IONQ",
    "LCID",
    "MARA",
    "PLTR",
    "RIOT",
    "RIVN",
    "SOUN",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMD",
    "TSLA",
    "META",
    "AMZN",
    "GOOGL",
    "NFLX",
    "JPM",
    "BAC",
    "XLF",
    "XLK",
    "XLE",
    "XLY",
    "XLI",
    "XLU",
    "XLP",
    "XLV",
    "VIX",
)


@dataclass(frozen=True)
class HistoryBar:
    date: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
    dividend: float | None
    split_factor: float | None
    source: str
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["record_hash"] = history_bar_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryBar":
        parsed_date = _date_value(data, "date")
        return cls(
            date=parsed_date.isoformat(),
            symbol=normalize_history_symbol(_string_value(data, "symbol")),
            open=_float_value(data, "open"),
            high=_float_value(data, "high"),
            low=_float_value(data, "low"),
            close=_float_value(data, "close"),
            adjusted_close=_float_value(data, "adjusted_close"),
            volume=_int_value(data, "volume"),
            dividend=_optional_float_value(data, "dividend"),
            split_factor=_optional_float_value(data, "split_factor"),
            source=_string_or_empty(data, "source"),
            record_hash=_string_or_empty(data, "record_hash"),
        )


@dataclass(frozen=True)
class HistoryDataFile:
    path: str
    format: str
    symbols: list[str]
    sha256: str
    source: str
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryDataFile":
        file_format = _string_value(data, "format").lower()
        if file_format not in ALLOWED_HISTORY_FORMATS:
            raise ValueError(f"unsupported history file format: {file_format}")
        return cls(
            path=_string_value(data, "path"),
            format=file_format,
            symbols=[normalize_history_symbol(symbol) for symbol in _string_list_value(data, "symbols")],
            sha256=_string_or_empty(data, "sha256"),
            source=_string_or_empty(data, "source"),
            row_count=_optional_int_value(data, "row_count"),
        )


@dataclass(frozen=True)
class HistoryDatasetManifest:
    artifact_type: str
    history_dataset_manifest_version: str
    dataset_id: str
    dataset_status: str
    raw_data_directory: str
    required_universe: list[str]
    required_columns: list[str]
    optional_columns: list[str]
    allowed_formats: list[str]
    data_files: list[HistoryDataFile]
    generated_real_data: bool
    network_fetch_performed: bool
    credential_required: bool
    paper_only: bool
    live_blocked: bool
    manifest_reproducibility_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["data_files"] = [file_ref.to_dict() for file_ref in self.data_files]
        payload["manifest_reproducibility_hash"] = history_manifest_hash(payload)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryDatasetManifest":
        file_records = _dict_list_value(data, "data_files")
        return cls(
            artifact_type=_string_value(data, "artifact_type"),
            history_dataset_manifest_version=_string_value(data, "history_dataset_manifest_version"),
            dataset_id=_string_value(data, "dataset_id"),
            dataset_status=_string_value(data, "dataset_status"),
            raw_data_directory=_string_value(data, "raw_data_directory"),
            required_universe=[normalize_history_symbol(symbol) for symbol in _string_list_value(data, "required_universe")],
            required_columns=_string_list_value(data, "required_columns"),
            optional_columns=_string_list_value(data, "optional_columns"),
            allowed_formats=_string_list_value(data, "allowed_formats"),
            data_files=[HistoryDataFile.from_dict(record) for record in file_records],
            generated_real_data=_bool_value(data, "generated_real_data"),
            network_fetch_performed=_bool_value(data, "network_fetch_performed"),
            credential_required=_bool_value(data, "credential_required"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            manifest_reproducibility_hash=_string_or_empty(data, "manifest_reproducibility_hash"),
        )


@dataclass(frozen=True)
class HistorySymbolCoverage:
    artifact_type: str
    symbol: str
    row_count: int
    first_date: str
    last_date: str
    date_coverage_count: int
    expected_weekday_count: int
    missing_weekday_count: int
    missing_dates: list[str]
    stale: bool
    missing: bool
    coverage_status: str
    coverage_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coverage_hash"] = stable_history_hash({k: v for k, v in payload.items() if k != "coverage_hash"})
        return payload


@dataclass(frozen=True)
class HistoryQualityFlag:
    artifact_type: str
    flag_id: str
    severity: str
    symbol: str
    date: str
    path: str
    row_number: int
    reason_code: str
    message: str
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["flag_hash"] = stable_history_hash({k: v for k, v in payload.items() if k != "flag_hash"})
        return payload


@dataclass(frozen=True)
class HistoryLoaderProof:
    artifact_type: str
    proof_id: str
    dataset_status: str
    manifest_path: str
    raw_data_directory: str
    data_file_count: int
    rows_loaded: int
    file_hashes: dict[str, str]
    missing_symbols: list[str]
    invalid_symbols: list[str]
    paper_only: bool
    live_blocked: bool
    no_broker: bool
    no_scheduler: bool
    no_real_sizing: bool
    proof_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["proof_hash"] = stable_history_hash({k: v for k, v in payload.items() if k != "proof_hash"})
        return payload


@dataclass(frozen=True)
class HistoryDatasetValidation:
    artifact_type: str
    history_validator_version: str
    dataset_status: str
    row_count: int
    required_symbol_count: int
    covered_symbol_count: int
    date_coverage_count: int
    start_date: str
    end_date: str
    missing_symbol_count: int
    stale_symbol_count: int
    duplicate_count: int
    quality_flag_count: int
    data_file_count: int
    file_hashes: dict[str, str]
    manifest_reproducibility_hash: str
    validation_reproducibility_hash: str
    expected_raw_directory: str
    expected_manifest_path: str
    paper_only: bool
    live_blocked: bool
    no_broker: bool
    no_scheduler: bool
    no_real_sizing: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["validation_reproducibility_hash"] = stable_history_hash({
            k: v for k, v in payload.items() if k != "validation_reproducibility_hash"
        })
        return payload


def normalize_history_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    aliases = {
        "^VIX": "VIX",
        "VIXCLS": "VIX",
        "CBOE:VIX": "VIX",
    }
    return aliases.get(normalized, normalized)


def history_bar_hash(bar: HistoryBar) -> str:
    payload = asdict(bar)
    payload["record_hash"] = ""
    return stable_history_hash(payload)


def history_manifest_hash(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload["manifest_reproducibility_hash"] = ""
    payload.pop("reproducibility_hash", None)
    return stable_history_hash(payload)


def stable_history_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _date_value(data: dict[str, Any], key: str) -> date:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must parse as YYYY-MM-DD: {value}") from exc


def _string_value(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    if not value.strip():
        raise ValueError(f"{key} must not be empty")
    return value


def _string_or_empty(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    return value


def _bool_value(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _float_value(data: dict[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool):
        raise TypeError(f"{key} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{key} must be numeric") from exc


def _optional_float_value(data: dict[str, Any], key: str) -> float | None:
    if key not in data or data[key] in {"", None}:
        return None
    return _float_value(data, key)


def _int_value(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    try:
        parsed = int(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise TypeError(f"{key} must be int") from exc
    if str(value).strip() not in {str(parsed), f"{parsed}.0"} and isinstance(value, str):
        raise TypeError(f"{key} must be int")
    return parsed


def _optional_int_value(data: dict[str, Any], key: str) -> int:
    if key not in data or data[key] in {"", None}:
        return 0
    return _int_value(data, key)


def _string_list_value(data: dict[str, Any], key: str) -> list[str]:
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be list[str]")
    return list(value)


def _dict_list_value(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError(f"{key} must be list[dict]")
    return [dict(item) for item in value]
