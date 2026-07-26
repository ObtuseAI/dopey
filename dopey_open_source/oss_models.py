"""Hash-stable records for DOPEY open-source candidate gates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


OSS_STACK_VERSION = "dopey-open-source-quant-stack-and-free-data-path-v1"
ALLOWED_IMPORT_MODES: frozenset[str] = frozenset({"reference_only", "sandbox_candidate", "adapter_candidate", "rejected"})
ALLOWED_GATE_STATUSES: frozenset[str] = frozenset({
    "reference_only_allowed",
    "sandbox_import_candidate",
    "adapter_candidate_manual_review",
    "manual_review_required",
    "rejected",
    "terminal_block",
})
HASH_FIELDS: frozenset[str] = frozenset({
    "candidate_hash",
    "gate_hash",
    "plan_hash",
    "capability_hash",
    "adapter_hash",
    "summary_hash",
    "proof_hash",
    "flag_hash",
})


@dataclass(frozen=True)
class OssCandidate:
    artifact_type: str
    oss_stack_version: str
    candidate_id: str
    repo_name: str
    repo_url: str
    category: str
    license_name: str
    license_review_status: str
    maintenance_status: str
    dependency_risk: str
    live_trading_risk: str
    broker_integration_risk: str
    network_fetch_risk: str
    credential_risk: str
    dopey_value_score: float
    import_mode: str
    approval_required: bool
    not_imported: bool
    not_executed: bool
    paper_only: bool
    live_blocked: bool
    candidate_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["oss_stack_version"] = OSS_STACK_VERSION
        record["import_mode"] = validate_import_mode(str(record["import_mode"]))
        _force_candidate_safety(record)
        record["candidate_hash"] = stable_oss_hash(record)
        return record


@dataclass(frozen=True)
class OssLicenseSecurityResult:
    artifact_type: str
    oss_stack_version: str
    candidate_id: str
    gate_status: str
    license_compatible: bool
    unknown_license_block: bool
    copyleft_manual_review: bool
    stale_repo_manual_review: bool
    dangerous_dependencies_manual_review: bool
    broker_live_trading_manual_review: bool
    credential_handling_manual_review: bool
    network_fetching_manual_review: bool
    import_isolation_required: bool
    sandbox_test_required: bool
    no_direct_promotion_authority: bool
    no_direct_broker_authority: bool
    no_direct_scheduler_authority: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    gate_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["oss_stack_version"] = OSS_STACK_VERSION
        record["gate_status"] = validate_gate_status(str(record["gate_status"]))
        record["no_direct_promotion_authority"] = True
        record["no_direct_broker_authority"] = True
        record["no_direct_scheduler_authority"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["reason_codes"] = sorted(str(code) for code in record["reason_codes"])
        record["gate_hash"] = stable_oss_hash(record)
        return record


@dataclass(frozen=True)
class OssSandboxImportPlan:
    artifact_type: str
    oss_stack_version: str
    plan_id: str
    reference_only_folder: str
    sandbox_candidates_folder: str
    adapter_candidates_folder: str
    manifests_folder: str
    manifest_template_path: str
    repo_cloned_count: int
    dependency_installed_count: int
    external_code_imported_count: int
    external_code_executed_count: int
    approval_required: bool
    paper_only: bool
    live_blocked: bool
    plan_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["oss_stack_version"] = OSS_STACK_VERSION
        record["repo_cloned_count"] = 0
        record["dependency_installed_count"] = 0
        record["external_code_imported_count"] = 0
        record["external_code_executed_count"] = 0
        record["approval_required"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["plan_hash"] = stable_oss_hash(record)
        return record


@dataclass(frozen=True)
class OssCapabilityExtractionPlan:
    artifact_type: str
    oss_stack_version: str
    capability_id: str
    capability_category: str
    extraction_mode: str
    allowed_output: str
    no_external_execution_required: bool
    approval_required: bool
    paper_only: bool
    live_blocked: bool
    capability_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["oss_stack_version"] = OSS_STACK_VERSION
        record["no_external_execution_required"] = True
        record["approval_required"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["capability_hash"] = stable_oss_hash(record)
        return record


@dataclass(frozen=True)
class OssAdapterContract:
    artifact_type: str
    oss_stack_version: str
    adapter_id: str
    candidate_id: str
    external_component_cannot_call_broker: bool
    external_component_cannot_fetch_network_data_unless_approved: bool
    external_component_cannot_place_orders: bool
    external_component_cannot_write_credentials: bool
    external_component_cannot_modify_promotion_gates: bool
    external_component_cannot_override_statistical_truth_or_fitness_gates: bool
    output_authority: str
    paper_only: bool
    live_blocked: bool
    adapter_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["oss_stack_version"] = OSS_STACK_VERSION
        record["external_component_cannot_call_broker"] = True
        record["external_component_cannot_fetch_network_data_unless_approved"] = True
        record["external_component_cannot_place_orders"] = True
        record["external_component_cannot_write_credentials"] = True
        record["external_component_cannot_modify_promotion_gates"] = True
        record["external_component_cannot_override_statistical_truth_or_fitness_gates"] = True
        record["output_authority"] = "candidate_signal_or_diagnostic_only"
        record["paper_only"] = True
        record["live_blocked"] = True
        record["adapter_hash"] = stable_oss_hash(record)
        return record


def stable_oss_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_strip_hash_fields(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_import_mode(import_mode: str) -> str:
    if import_mode not in ALLOWED_IMPORT_MODES:
        raise ValueError(f"unsupported import_mode: {import_mode}")
    return import_mode


def validate_gate_status(status: str) -> str:
    if status not in ALLOWED_GATE_STATUSES:
        raise ValueError(f"unsupported oss gate status: {status}")
    return status


def _force_candidate_safety(record: dict[str, Any]) -> None:
    record["approval_required"] = True
    record["not_imported"] = True
    record["not_executed"] = True
    record["paper_only"] = True
    record["live_blocked"] = True


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_hash_fields(item) for key, item in value.items() if key not in HASH_FIELDS}
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
