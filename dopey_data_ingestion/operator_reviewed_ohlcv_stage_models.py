"""Hash-stable models for operator-reviewed OHLCV stage reruns."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


OPERATOR_REVIEWED_OHLCV_STAGE_VERSION = "dopey-operator-reviewed-ohlcv-stage-rerun-v1"
ALLOWED_OPERATOR_STAGE_STATUSES: frozenset[str] = frozenset({
    "operator_files_missing",
    "operator_review_packet_missing",
    "operator_review_packet_incomplete",
    "operator_review_packet_valid",
    "staged_files_detected",
    "staged_files_preflight_failed",
    "staged_files_validator_failed",
    "staged_files_validator_passed",
    "history_activation_blocked",
    "history_activation_passed",
    "real_signal_validation_blocked",
    "real_signal_validation_passed_no_promotion",
    "terminal_block",
})
ALLOWED_OPERATOR_STAGE_DECISIONS: frozenset[str] = frozenset({
    "operator_must_stage_reviewed_files",
    "operator_must_complete_source_review_packet",
    "operator_must_complete_final_manifest",
    "operator_must_fix_preflight",
    "operator_must_fix_validator_errors",
    "operator_must_fix_history_activation_errors",
    "operator_must_fix_real_signal_validation_errors",
    "ready_for_local_ohlcv_validator",
    "ready_for_history_activation",
    "ready_for_real_signal_validation",
    "real_ohlcv_signal_evidence_ready_no_promotion",
    "terminal_block",
})
HASH_FIELDS: frozenset[str] = frozenset({
    "input_hash",
    "review_hash",
    "inventory_hash",
    "candidate_hash",
    "step_hash",
    "decision_hash",
    "boundary_hash",
    "packet_hash",
    "flag_hash",
    "proof_hash",
    "summary_hash",
    "record_hash",
    "case_hash",
})


@dataclass(frozen=True)
class OperatorReviewedOhlcvStageInput:
    artifact_type: str
    stage_version: str
    input_id: str
    source_review_path: str
    daily_ohlcv_folder: str
    market_context_folder: str
    corporate_actions_folder: str
    final_manifest_path: str
    candidate_manifest_path: str
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["input_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvSourceReview:
    artifact_type: str
    stage_version: str
    review_id: str
    status: str
    source_review_valid: bool
    evidence_allowed: bool
    missing_fields: list[str]
    blocking_fields: list[str]
    license_status: str
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    review_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["status"] = validate_operator_stage_status(str(record["status"]))
        record["review_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvStagedFileInventory:
    artifact_type: str
    stage_version: str
    inventory_id: str
    local_file_path: str
    dataset_family: str
    file_extension: str
    byte_size: int
    sha256: str
    row_count: int
    header: list[str]
    source_column_present: bool
    symbol_count_candidate: int
    date_range_candidate: dict[str, str]
    template_sample_contamination: bool
    sample_only_symbol_detected: bool
    sample_only_row_detected: bool
    not_real_data_row_detected: bool
    credential_token_pattern_detected: bool
    broker_live_order_scheduler_real_sizing_pattern_detected: bool
    unsupported_file_type: bool
    symlink_or_outside_repo_attempt: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    inventory_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["inventory_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvManifestCandidate:
    artifact_type: str
    stage_version: str
    candidate_id: str
    manifest_candidate_status: str
    staged_file_count: int
    source_review_status: str
    candidate_manifest_is_evidence: bool
    final_manifest_required: bool
    operator_must_approve_final_manifest: bool
    local_file_paths: list[str]
    file_hashes: dict[str, str]
    row_counts: dict[str, int]
    symbol_counts: dict[str, int]
    date_ranges: dict[str, dict[str, str]]
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    candidate_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["candidate_manifest_is_evidence"] = False
        record["final_manifest_required"] = True
        record["operator_must_approve_final_manifest"] = True
        record["candidate_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvRerunStep:
    artifact_type: str
    stage_version: str
    step_id: str
    step_name: str
    status: str
    decision: str
    artifact_paths: dict[str, str]
    terminal_block: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    step_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["step_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvValidationDecision:
    artifact_type: str
    stage_version: str
    decision_id: str
    operator_reviewed_stage_status: str
    operator_reviewed_stage_decision: str
    reason_codes: list[str]
    next_recommended_target: str
    real_data_files_present: bool
    valid_real_dataset: bool
    real_history_used: bool
    real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["operator_reviewed_stage_status"] = validate_operator_stage_status(str(record["operator_reviewed_stage_status"]))
        record["operator_reviewed_stage_decision"] = validate_operator_stage_decision(str(record["operator_reviewed_stage_decision"]))
        record["decision_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvEvidenceBoundary:
    artifact_type: str
    stage_version: str
    boundary_id: str
    ohlcv_evidence_possible_only_after_validator_pass: bool
    history_activation_required_for_real_history: bool
    real_signal_validation_required_for_signal_evidence: bool
    not_options_evidence: bool
    not_options_quote_evidence: bool
    not_quote_priced_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    not_strategy_promotion: bool
    paper_only: bool
    live_blocked: bool
    broker_connection_used: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    boundary_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["ohlcv_evidence_possible_only_after_validator_pass"] = True
        record["history_activation_required_for_real_history"] = True
        record["real_signal_validation_required_for_signal_evidence"] = True
        record["not_options_quote_evidence"] = True
        record["not_quote_priced_backtest_evidence"] = True
        record["not_strategy_promotion"] = True
        record["boundary_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvActionPacket:
    artifact_type: str
    stage_version: str
    packet_id: str
    packet_status: str
    operator_reviewed_stage_decision: str
    required_actions: list[str]
    blocked_items: list[str]
    repair_groups: dict[str, list[str]]
    run_command: str
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    packet_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["operator_reviewed_stage_decision"] = validate_operator_stage_decision(str(record["operator_reviewed_stage_decision"]))
        record["packet_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvQualityFlag:
    artifact_type: str
    stage_version: str
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
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["flag_hash"] = stable_operator_stage_hash(record)
        return record


@dataclass(frozen=True)
class OperatorReviewedOhlcvProofRecord:
    artifact_type: str
    stage_version: str
    proof_id: str
    operator_reviewed_stage_status: str
    operator_reviewed_stage_decision: str
    source_review_status: str
    staged_file_count: int
    manifest_candidate_status: str
    final_manifest_status: str
    local_ohlcv_status: str
    history_spine_activation_status: str
    real_signal_validation_status: str
    real_data_files_present: bool
    valid_real_dataset: bool
    real_history_used: bool
    real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    network_fetch_performed: bool
    credentials_created: bool
    env_created: bool
    broker_connection_used: bool
    strategy_promotion_allowed: bool
    not_options_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    proof_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        _force_safety(record)
        record["stage_version"] = OPERATOR_REVIEWED_OHLCV_STAGE_VERSION
        record["operator_reviewed_stage_status"] = validate_operator_stage_status(str(record["operator_reviewed_stage_status"]))
        record["operator_reviewed_stage_decision"] = validate_operator_stage_decision(str(record["operator_reviewed_stage_decision"]))
        record["proof_hash"] = stable_operator_stage_hash(record)
        return record


def stable_operator_stage_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_strip_hash_fields(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_operator_stage_status(status: str) -> str:
    if status not in ALLOWED_OPERATOR_STAGE_STATUSES:
        raise ValueError(f"unsupported operator reviewed OHLCV stage status: {status}")
    return status


def validate_operator_stage_decision(decision: str) -> str:
    if decision not in ALLOWED_OPERATOR_STAGE_DECISIONS:
        raise ValueError(f"unsupported operator reviewed OHLCV stage decision: {decision}")
    return decision


def _force_safety(record: dict[str, Any]) -> None:
    record["paper_only"] = True
    record["live_blocked"] = True
    record["network_fetch_performed"] = False
    record["credentials_created"] = False
    record["env_created"] = False
    record["broker_connection_used"] = False
    record["strategy_promotion_allowed"] = False
    record["not_options_evidence"] = True
    record["not_profitability_claim"] = True
    record["not_live_ready"] = True


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_hash_fields(item) for key, item in value.items() if key not in HASH_FIELDS}
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
