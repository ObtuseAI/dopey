"""Hash-stable manual OHLCV staging records."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


MANUAL_OHLCV_STAGING_VERSION = "dopey-manual-free-ohlcv-staging-local-import-fix-v1"
ALLOWED_STAGING_STATUSES: frozenset[str] = frozenset({
    "manual_staging_required",
    "local_files_detected_repair_required",
    "manifest_draft_ready",
    "local_files_ready_for_validator",
    "validator_pass_ready_for_history_activation",
    "terminal_block",
})
ALLOWED_STAGING_DECISIONS: frozenset[str] = frozenset({
    "operator_must_stage_files",
    "operator_must_complete_manifest",
    "operator_must_fix_schema",
    "operator_must_fix_quality",
    "operator_must_fix_license_provenance",
    "operator_must_remove_sample_or_template_rows",
    "operator_must_remove_credentials_or_live_markers",
    "ready_for_local_ohlcv_validator",
    "ready_for_history_spine_activation_after_validator_pass",
    "terminal_block",
})
HASH_FIELDS: frozenset[str] = frozenset({
    "plan_hash",
    "candidate_hash",
    "checklist_hash",
    "draft_hash",
    "hash_record_hash",
    "hint_hash",
    "decision_hash",
    "flag_hash",
    "proof_hash",
    "summary_hash",
    "record_hash",
    "case_hash",
})


@dataclass(frozen=True)
class ManualOhlcvStagingPlan:
    artifact_type: str
    staging_version: str
    plan_id: str
    manual_staging_status: str
    manual_staging_decision: str
    required_folders: list[str]
    required_daily_ohlcv_columns: list[str]
    required_manifest_fields: list[str]
    blocker_codes: list[str]
    next_recommended_target: str
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    plan_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["manual_staging_status"] = validate_staging_status(str(record["manual_staging_status"]))
        record["manual_staging_decision"] = validate_staging_decision(str(record["manual_staging_decision"]))
        record["plan_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvSourceCandidate:
    artifact_type: str
    staging_version: str
    source_candidate_id: str
    source_name: str
    dataset_family: str
    manual_access_mode: str
    requires_terms_review: bool
    license_status: str
    provenance_status: str
    commercial_use_uncertain: bool
    redistribution_uncertain: bool
    coverage_notes: str
    survivorship_bias_risk: str
    staleness_risk: str
    schema_risk: str
    evidence_allowed: bool
    manual_review_required: bool
    not_fetched_by_dopey: bool
    credentials_required: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    candidate_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["evidence_allowed"] = False
        record["manual_review_required"] = True
        record["not_fetched_by_dopey"] = True
        record["credentials_required"] = False
        record["candidate_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvStagingChecklist:
    artifact_type: str
    staging_version: str
    checklist_id: str
    required_folders: list[str]
    required_daily_ohlcv_columns: list[str]
    recommended_optional_columns: list[str]
    required_manifest_fields: list[str]
    blocker_codes: list[str]
    operator_actions: list[str]
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    checklist_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["checklist_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvManifestDraft:
    artifact_type: str
    staging_version: str
    draft_id: str
    draft_status: str
    real_data_files_present: bool
    hash_record_count: int
    provider_terms_reviewed: bool
    license_status: str
    redistribution_allowed: bool
    local_file_paths: list[str]
    file_hashes: dict[str, str]
    row_counts: dict[str, int]
    symbol_counts: dict[str, int]
    date_ranges: dict[str, dict[str, str]]
    operator_required_fields: list[str]
    manifest_draft_is_import_approval: bool
    manifest_draft_is_evidence: bool
    not_broker_data: bool
    not_credentials: bool
    not_live_data: bool
    not_network_fetched_by_dopey: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    draft_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["draft_status"] = validate_staging_status(str(record["draft_status"]))
        record["provider_terms_reviewed"] = False
        record["license_status"] = "unknown"
        record["redistribution_allowed"] = False
        record["manifest_draft_is_import_approval"] = False
        record["manifest_draft_is_evidence"] = False
        record["not_broker_data"] = True
        record["not_credentials"] = True
        record["not_live_data"] = True
        record["not_network_fetched_by_dopey"] = True
        record["draft_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvHashRecord:
    artifact_type: str
    staging_version: str
    file_id: str
    local_file_path: str
    dataset_family: str
    file_extension: str
    byte_size: int
    sha256: str
    row_count: int
    symbol_count: int
    date_range: dict[str, str]
    source_values: list[str]
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    hash_record_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["hash_record_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvFileRepairHint:
    artifact_type: str
    staging_version: str
    hint_id: str
    fix_group: str
    severity: str
    local_file_path: str
    reason_code: str
    message: str
    operator_action: str
    evidence_claim_allowed: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    hint_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["evidence_claim_allowed"] = False
        record["hint_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvStagingDecision:
    artifact_type: str
    staging_version: str
    decision_id: str
    manual_staging_status: str
    manual_staging_decision: str
    reason_codes: list[str]
    real_data_files_present: bool
    valid_real_dataset: bool
    ready_for_local_ohlcv_validator: bool
    ready_for_history_spine_activation_after_validator_pass: bool
    strategy_promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["manual_staging_status"] = validate_staging_status(str(record["manual_staging_status"]))
        record["manual_staging_decision"] = validate_staging_decision(str(record["manual_staging_decision"]))
        record["strategy_promotion_allowed"] = False
        record["decision_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvStagingQualityFlag:
    artifact_type: str
    staging_version: str
    flag_id: str
    severity: str
    reason_code: str
    message: str
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    not_strategy_promotion: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["flag_hash"] = stable_manual_ohlcv_hash(record)
        return record


@dataclass(frozen=True)
class ManualOhlcvStagingProofRecord:
    artifact_type: str
    staging_version: str
    proof_id: str
    manual_staging_status: str
    manual_staging_decision: str
    source_candidate_count: int
    evidence_allowed_count: int
    hash_record_count: int
    manifest_draft_status: str
    preflight_status: str
    fix_plan_status: str
    local_ohlcv_status: str
    valid_real_dataset: bool
    history_spine_activation_status: str
    real_signal_validation_status: str
    real_signal_evidence: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    not_strategy_promotion: bool
    proof_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_manual_safety(record)
        record["staging_version"] = MANUAL_OHLCV_STAGING_VERSION
        record["manual_staging_status"] = validate_staging_status(str(record["manual_staging_status"]))
        record["manual_staging_decision"] = validate_staging_decision(str(record["manual_staging_decision"]))
        record["strategy_promotion_allowed"] = False
        record["proof_hash"] = stable_manual_ohlcv_hash(record)
        return record


def stable_manual_ohlcv_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_strip_hash_fields(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_staging_status(status: str) -> str:
    if status not in ALLOWED_STAGING_STATUSES:
        raise ValueError(f"unsupported manual staging status: {status}")
    return status


def validate_staging_decision(decision: str) -> str:
    if decision not in ALLOWED_STAGING_DECISIONS:
        raise ValueError(f"unsupported manual staging decision: {decision}")
    return decision


def _force_manual_safety(record: dict[str, Any]) -> None:
    record["paper_only"] = True
    record["live_blocked"] = True
    record["network_fetch_performed"] = False
    record["credentials_created"] = False
    record["env_created"] = False
    record["broker_connection_used"] = False
    record["not_strategy_promotion"] = True


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_hash_fields(item) for key, item in value.items() if key not in HASH_FIELDS}
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
