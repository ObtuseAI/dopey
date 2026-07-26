"""Hash-stable records for local free/public OHLCV validation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


LOCAL_OHLCV_IMPORT_VERSION = "dopey-local-free-ohlcv-import-validator-history-activation-v1"
ALLOWED_LOCAL_OHLCV_STATUSES: frozenset[str] = frozenset({
    "missing_local_ohlcv_files",
    "local_ohlcv_validation_pass",
    "local_ohlcv_validation_fail",
    "manual_review_required",
    "terminal_block",
})
ALLOWED_IMPORT_DECISIONS: frozenset[str] = frozenset({
    "blocked_missing_local_ohlcv",
    "blocked_schema_errors",
    "blocked_quality_errors",
    "blocked_missing_license",
    "blocked_missing_provenance",
    "blocked_sample_template_contamination",
    "blocked_credential_or_token_contamination",
    "manual_review_required",
    "valid_local_ohlcv_ready_for_history_spine",
    "terminal_block",
})
ALLOWED_QUALITY_STATUSES: frozenset[str] = frozenset({
    "quality_pass",
    "quality_fail",
    "manual_review_required",
    "terminal_block",
})
ALLOWED_PROVENANCE_STATUSES: frozenset[str] = frozenset({
    "provenance_pass",
    "blocked_missing_manifest",
    "blocked_missing_license",
    "blocked_missing_provenance",
    "manual_review_required",
    "terminal_block",
})
HASH_FIELDS: frozenset[str] = frozenset({
    "input_hash",
    "file_hash",
    "schema_hash",
    "quality_hash",
    "license_hash",
    "decision_hash",
    "advice_hash",
    "flag_hash",
    "summary_hash",
    "proof_hash",
    "record_hash",
})


@dataclass(frozen=True)
class LocalOhlcvImportInput:
    artifact_type: str
    validator_version: str
    input_id: str
    daily_ohlcv_folder: str
    market_context_folder: str
    corporate_actions_folder: str
    manifest_path: str
    network_fetch_performed: bool
    broker_connection_used: bool
    credentials_created: bool
    env_created: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["network_fetch_performed"] = False
        record["broker_connection_used"] = False
        record["credentials_created"] = False
        record["env_created"] = False
        record["input_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvFileInventoryRecord:
    artifact_type: str
    validator_version: str
    file_id: str
    dataset_family: str
    local_file_path: str
    file_extension: str
    byte_size: int
    sha256: str
    row_count: int
    header_columns: list[str]
    sample_only_detected: bool
    fake_symbol_detected: bool
    credential_token_pattern_detected: bool
    future_date_candidate_detected: bool
    manifest_referenced: bool
    source_provenance_fields_present: bool
    license_fields_present: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    file_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["file_present"] = True
        record["file_sha256"] = record["sha256"]
        record["symbol_count"] = int(record.get("symbol_count", 0))
        record["date_range"] = record.get("date_range", {})
        record["file_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvSchemaResult:
    artifact_type: str
    validator_version: str
    result_id: str
    dataset_family: str
    local_file_path: str
    required_columns_present: bool
    missing_columns: list[str]
    extra_columns: list[str]
    parseable_rows: int
    malformed_rows: int
    schema_pass: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    schema_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["status"] = "local_ohlcv_validation_pass" if record["schema_pass"] else "local_ohlcv_validation_fail"
        record["duplicate_primary_key_count"] = 0
        record["valid_date_parse"] = record["schema_pass"] or "invalid_date" not in record["reason_codes"]
        record["valid_symbol_parse"] = record["schema_pass"] or "missing_symbol" not in record["reason_codes"]
        record["schema_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvQualityResult:
    artifact_type: str
    validator_version: str
    result_id: str
    dataset_family: str
    local_file_path: str
    status: str
    positive_ohlc: bool
    high_low_consistent: bool
    adjusted_close_positive: bool
    volume_nonnegative: bool
    duplicate_symbol_date_count: int
    row_count: int
    date_range: dict[str, str]
    symbol_coverage: list[str]
    missing_day_count: int
    stale_symbol_count: int
    future_date_count: int
    sample_only_row_count: int
    fake_symbol_count: int
    not_real_data_row_count: int
    credential_token_found: bool
    broker_live_order_scheduler_real_sizing_found: bool
    source_field_missing_count: int
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    quality_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["status"] = validate_quality_status(str(record["status"]))
        record["quality_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvLicenseProvenanceResult:
    artifact_type: str
    validator_version: str
    result_id: str
    dataset_family: str
    local_file_path: str
    status: str
    provider_name_present: bool
    source_present: bool
    license_status_present: bool
    license_status_accepted: bool
    provider_terms_reviewed: bool
    redistribution_allowed_recorded: bool
    file_hash_recorded: bool
    file_hash_matches_manifest: bool
    provenance_complete: bool
    manifest_template_only: bool
    manifest_missing_required_fields: list[str]
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    license_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["status"] = validate_provenance_status(str(record["status"]))
        record["license_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvImportDecision:
    artifact_type: str
    validator_version: str
    decision_id: str
    local_ohlcv_status: str
    valid_real_dataset: bool
    real_data_imported: bool
    history_spine_upgrade_allowed: bool
    terminal_block: bool
    manual_review_required: bool
    real_data_files_present: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["local_ohlcv_status"] = validate_local_ohlcv_status(str(record["local_ohlcv_status"]))
        record["local_ohlcv_import_decision"] = infer_import_decision(record)
        record["real_data_imported"] = False
        record["real_history_used"] = bool(record["valid_real_dataset"] and record["history_spine_upgrade_allowed"])
        record["decision_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvImportFixAdvice:
    artifact_type: str
    validator_version: str
    local_ohlcv_status: str
    local_ohlcv_import_decision: str
    fix_advice_status: str
    advice_groups: dict[str, list[str]]
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    advice_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["local_ohlcv_status"] = validate_local_ohlcv_status(str(record["local_ohlcv_status"]))
        record["local_ohlcv_import_decision"] = validate_import_decision(str(record["local_ohlcv_import_decision"]))
        record["advice_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvImportQualityFlag:
    artifact_type: str
    validator_version: str
    flag_id: str
    severity: str
    reason_code: str
    message: str
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["flag_hash"] = stable_local_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class LocalOhlcvImportProofRecord:
    artifact_type: str
    validator_version: str
    proof_id: str
    local_ohlcv_status: str
    valid_real_dataset: bool
    real_data_imported: bool
    history_spine_upgrade_allowed: bool
    network_fetch_performed: bool
    broker_connection_used: bool
    credentials_created: bool
    env_created: bool
    no_scheduler: bool
    no_real_sizing: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    proof_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["validator_version"] = LOCAL_OHLCV_IMPORT_VERSION
        record["local_ohlcv_status"] = validate_local_ohlcv_status(str(record["local_ohlcv_status"]))
        record["real_data_imported"] = False
        record["network_fetch_performed"] = False
        record["broker_connection_used"] = False
        record["credentials_created"] = False
        record["env_created"] = False
        record["no_scheduler"] = True
        record["no_real_sizing"] = True
        record["proof_hash"] = stable_local_ohlcv_hash(record)
        return record


LocalOhlcvFileInventory = LocalOhlcvFileInventoryRecord
LocalOhlcvImportProof = LocalOhlcvImportProofRecord


def stable_local_ohlcv_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_strip_hash_fields(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_local_ohlcv_status(status: str) -> str:
    if status not in ALLOWED_LOCAL_OHLCV_STATUSES:
        raise ValueError(f"unsupported local_ohlcv_status: {status}")
    return status


def validate_import_decision(decision: str) -> str:
    if decision not in ALLOWED_IMPORT_DECISIONS:
        raise ValueError(f"unsupported local_ohlcv_import_decision: {decision}")
    return decision


def validate_quality_status(status: str) -> str:
    if status not in ALLOWED_QUALITY_STATUSES:
        raise ValueError(f"unsupported quality status: {status}")
    return status


def validate_provenance_status(status: str) -> str:
    if status not in ALLOWED_PROVENANCE_STATUSES:
        raise ValueError(f"unsupported provenance status: {status}")
    return status


def infer_import_decision(record: dict[str, Any]) -> str:
    existing = record.get("local_ohlcv_import_decision")
    if isinstance(existing, str) and existing:
        return validate_import_decision(existing)
    status = str(record["local_ohlcv_status"])
    reasons = set(str(item) for item in record.get("reason_codes", []))
    if status == "missing_local_ohlcv_files":
        return "blocked_missing_local_ohlcv"
    if status == "terminal_block":
        return "terminal_block"
    if status == "manual_review_required":
        return "manual_review_required"
    if status == "local_ohlcv_validation_pass":
        return "valid_local_ohlcv_ready_for_history_spine"
    if "sample_template_contamination" in reasons:
        return "blocked_sample_template_contamination"
    if "credential_or_token_contamination" in reasons:
        return "blocked_credential_or_token_contamination"
    if "missing_license" in reasons:
        return "blocked_missing_license"
    if "missing_provenance" in reasons:
        return "blocked_missing_provenance"
    if "schema_errors" in reasons:
        return "blocked_schema_errors"
    return "blocked_quality_errors"


def _force_safety(record: dict[str, Any]) -> None:
    record["paper_only"] = True
    record["live_blocked"] = True
    record["not_live_data"] = True
    record["not_broker_data"] = True
    record["not_strategy_promotion"] = True
    record["not_real_data_ingested"] = True


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_hash_fields(item) for key, item in value.items() if key not in HASH_FIELDS}
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
