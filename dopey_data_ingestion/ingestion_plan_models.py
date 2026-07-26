"""Typed, hash-stable records for DOPEY's real-data ingestion plan."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


DATA_INGESTION_PLAN_VERSION = "dopey-real-data-ingestion-plan-v1"
ALLOWED_INGESTION_STATUSES: frozenset[str] = frozenset({
    "real_data_ingestion_plan_ready",
    "missing_provider_selection",
    "missing_local_data",
    "manual_review_required",
    "terminal_block",
})
ALLOWED_IMPORT_READINESS_DECISIONS: frozenset[str] = frozenset({
    "plan_ready_import_not_started",
    "manual_review_required",
    "blocked_missing_license",
    "blocked_missing_provenance",
    "blocked_network_fetch_attempt",
    "blocked_fake_real_data",
    "terminal_block",
})
ALLOWED_GATE_STATUSES: frozenset[str] = frozenset({
    "gate_defined_not_run",
    "gate_pass",
    "gate_fail",
    "manual_review_required",
    "terminal_block",
})
ALLOWED_PROVIDER_STATUSES: frozenset[str] = frozenset({
    "candidate_only_not_integrated",
    "manual_review_required",
    "rejected",
    "approved_for_manual_offline_export_only",
})
HASH_FIELDS: frozenset[str] = frozenset({
    "plan_hash",
    "requirement_hash",
    "provider_hash",
    "staging_hash",
    "schema_hash",
    "license_hash",
    "gate_hash",
    "decision_hash",
    "flag_hash",
    "proof_hash",
})


@dataclass(frozen=True)
class DataIngestionPlan:
    artifact_type: str
    ingestion_plan_version: str
    plan_id: str
    ingestion_status: str
    import_readiness_decision: str
    dataset_requirement_count: int
    provider_candidate_count: int
    schema_contract_count: int
    quality_gate_count: int
    objective: str
    allowed_later_bundles: list[str]
    network_fetch_performed: bool
    broker_connection_used: bool
    credentials_created: bool
    env_created: bool
    real_data_files_present: bool
    real_data_ingested: bool
    real_data_validated: bool
    not_real_evidence: bool
    not_strategy_promotion: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    plan_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        record["ingestion_status"] = validate_ingestion_status(str(record["ingestion_status"]))
        record["import_readiness_decision"] = validate_import_readiness_decision(str(record["import_readiness_decision"]))
        _force_safety(record)
        record["plan_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class DatasetRequirement:
    artifact_type: str
    ingestion_plan_version: str
    requirement_id: str
    dataset_family: str
    purpose: str
    required_for: list[str]
    required_fields: list[str]
    optional_fields: list[str]
    primary_key_fields: list[str]
    target_history: str
    source_universe: str
    acquisition_notes: list[str]
    allowed_import_bundles: list[str]
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    requirement_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        _force_safety(record)
        record["required_fields"] = list(record["required_fields"])
        record["optional_fields"] = list(record["optional_fields"])
        record["requirement_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class ProviderCandidate:
    artifact_type: str
    ingestion_plan_version: str
    provider_name: str
    dataset_families_available: list[str]
    free_or_paid_status: str
    license_terms_review_required: bool
    credential_required: bool
    network_access_required: bool
    redistribution_restrictions: str
    historical_depth: str
    options_data_availability: str
    corporate_actions_availability: str
    fundamental_data_availability: str
    export_format_availability: list[str]
    recommended_use: str
    status: str
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    provider_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        record["status"] = validate_provider_status(str(record["status"]))
        if record["credential_required"]:
            record["status"] = "manual_review_required"
        _force_safety(record)
        record["provider_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class LocalStagingContract:
    artifact_type: str
    ingestion_plan_version: str
    contract_id: str
    raw_folder_contracts: dict[str, str]
    manifest_path: str
    validated_folder: str
    template_folder: str
    required_manifest_fields: list[str]
    folder_contracts_created: bool
    sample_manifest_template_created: bool
    real_data_files_present: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    staging_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        _force_safety(record)
        record["staging_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class DatasetSchemaContract:
    artifact_type: str
    ingestion_plan_version: str
    schema_id: str
    dataset_family: str
    schema_version: str
    template_path: str
    required_columns: list[str]
    optional_columns: list[str]
    primary_key_columns: list[str]
    column_types: dict[str, str]
    accepted_file_formats: list[str]
    sample_template_paths: list[str]
    sample_rows_allowed_as_real: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    schema_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        record["sample_rows_allowed_as_real"] = False
        _force_safety(record)
        record["schema_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class DataLicenseProvenanceRequirement:
    artifact_type: str
    ingestion_plan_version: str
    requirement_id: str
    dataset_family: str
    provider_name_required: bool
    license_status_required: bool
    provider_terms_review_required: bool
    redistribution_allowed_required: bool
    provenance_fields_required: list[str]
    valid_license_statuses: list[str]
    invalid_license_statuses: list[str]
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    license_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        _force_safety(record)
        record["license_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class DataQualityGate:
    artifact_type: str
    ingestion_plan_version: str
    gate_id: str
    dataset_family: str
    gate_name: str
    gate_description: str
    status: str
    terminal_on_failure: bool
    manual_review_on_failure: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    gate_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        record["status"] = validate_gate_status(str(record["status"]))
        _force_safety(record)
        record["gate_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class ImportReadinessDecision:
    artifact_type: str
    ingestion_plan_version: str
    decision_id: str
    ingestion_status: str
    import_readiness_decision: str
    real_data_files_present: bool
    real_data_ingested: bool
    real_data_validated: bool
    manifest_present: bool
    license_provenance_complete: bool
    sample_only_rows_in_real_path: bool
    credential_or_token_found: bool
    broker_live_order_scheduler_or_real_sizing_path_found: bool
    network_fetch_performed: bool
    reason_codes: list[str]
    next_recommended_target: str
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        record["ingestion_status"] = validate_ingestion_status(str(record["ingestion_status"]))
        record["import_readiness_decision"] = validate_import_readiness_decision(str(record["import_readiness_decision"]))
        record["real_data_ingested"] = False
        record["real_data_validated"] = False
        _force_safety(record)
        record["decision_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class IngestionPlanQualityFlag:
    artifact_type: str
    ingestion_plan_version: str
    flag_id: str
    severity: str
    reason_code: str
    message: str
    terminal_block: bool
    manual_review_required: bool
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        _force_safety(record)
        record["flag_hash"] = stable_ingestion_hash(record)
        return record


@dataclass(frozen=True)
class IngestionPlanProofRecord:
    artifact_type: str
    ingestion_plan_version: str
    proof_id: str
    ingestion_status: str
    import_readiness_decision: str
    real_data_files_present: bool
    real_data_ingested: bool
    real_data_validated: bool
    network_fetch_performed: bool
    broker_connection_used: bool
    credentials_created: bool
    env_created: bool
    live_data_used: bool
    no_orders: bool
    no_scheduler: bool
    no_real_sizing: bool
    no_strategy_promotion: bool
    sample_templates_not_real_evidence: bool
    next_recommended_target: str
    paper_only: bool
    live_blocked: bool
    not_real_data_ingested: bool
    proof_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["ingestion_plan_version"] = DATA_INGESTION_PLAN_VERSION
        record["ingestion_status"] = validate_ingestion_status(str(record["ingestion_status"]))
        record["import_readiness_decision"] = validate_import_readiness_decision(str(record["import_readiness_decision"]))
        record["real_data_ingested"] = False
        record["real_data_validated"] = False
        record["network_fetch_performed"] = False
        record["broker_connection_used"] = False
        record["credentials_created"] = False
        record["env_created"] = False
        record["live_data_used"] = False
        record["no_orders"] = True
        record["no_scheduler"] = True
        record["no_real_sizing"] = True
        record["no_strategy_promotion"] = True
        _force_safety(record)
        record["proof_hash"] = stable_ingestion_hash(record)
        return record


def stable_ingestion_hash(payload: dict[str, Any]) -> str:
    normalized = _strip_hash_fields(payload)
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_ingestion_status(status: str) -> str:
    if status not in ALLOWED_INGESTION_STATUSES:
        raise ValueError(f"unsupported ingestion_status: {status}")
    return status


def validate_import_readiness_decision(decision: str) -> str:
    if decision not in ALLOWED_IMPORT_READINESS_DECISIONS:
        raise ValueError(f"unsupported import_readiness_decision: {decision}")
    return decision


def validate_gate_status(status: str) -> str:
    if status not in ALLOWED_GATE_STATUSES:
        raise ValueError(f"unsupported gate_status: {status}")
    return status


def validate_provider_status(status: str) -> str:
    if status not in ALLOWED_PROVIDER_STATUSES:
        raise ValueError(f"unsupported provider_status: {status}")
    return status


def safety_fields() -> dict[str, bool]:
    return {
        "paper_only": True,
        "live_blocked": True,
        "not_real_data_ingested": True,
    }


def _force_safety(record: dict[str, Any]) -> None:
    record["paper_only"] = True
    record["live_blocked"] = True
    record["not_real_data_ingested"] = True


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_hash_fields(item)
            for key, item in value.items()
            if key not in HASH_FIELDS
        }
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
