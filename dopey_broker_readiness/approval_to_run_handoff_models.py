"""Deterministic models for the read-only detector approval-to-run handoff gate."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


APPROVAL_TO_RUN_HANDOFF_GATE_VERSION = "dopey-read-only-detector-approval-to-run-handoff-gate-v1"
APPROVAL_TO_RUN_NEXT_GATE = "separate_explicitly_approved_read_only_detector_run_bundle"
ALLOWED_HANDOFF_GATE_STATUSES: frozenset[str] = frozenset({
    "eligible_future_bundle_only",
    "blocked_missing_valid_approval",
    "blocked_terminal_incident",
    "manual_review_required",
    "blocked_audit_or_export_failure",
    "blocked_runtime_permission_leak",
    "blocked_scope_expansion",
    "blocked_timeout_misclassified_as_pass",
})


def _require_paper_live_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("approval-to-run handoff records require paper_only=true and live_blocked=true")


def _require_no_runtime_permissions(values: tuple[bool, ...]) -> None:
    if any(values):
        raise ValueError("approval-to-run handoff records cannot grant runtime permissions")


@dataclass(frozen=True)
class ApprovalToRunHandoffInput:
    handoff_input_id: str
    source_manual_approval_packet_summary_hash: str
    source_dry_run_summary_hash: str
    source_approval_intake_summary_hash: str
    source_broker_readiness_summary_hash: str
    source_incident_summary_hash: str
    source_lifecycle_summary_hash: str
    source_audit_summary_hash: str
    source_export_summary_hash: str
    source_review_summary_hash: str
    exact_valid_fixture_approval_available: bool
    source_future_detector_eligible_count: int
    source_manual_review_count: int
    source_terminal_block_count: int
    source_active_forbidden_live_decisions: int
    source_credential_findings: int
    source_full_suite_status: str
    source_full_suite_timeout_recorded_as_pass: bool
    terminal_incident_in_handoff_path: bool
    runtime_permission_leak_attempted: bool
    scope_expansion_detected: bool
    case_group: str
    case_name: str
    paper_only: bool
    live_blocked: bool
    input_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        required_hashes = (
            self.source_manual_approval_packet_summary_hash,
            self.source_dry_run_summary_hash,
            self.source_approval_intake_summary_hash,
            self.source_broker_readiness_summary_hash,
            self.source_incident_summary_hash,
            self.source_lifecycle_summary_hash,
            self.source_audit_summary_hash,
            self.source_export_summary_hash,
            self.source_review_summary_hash,
        )
        if any(not value for value in required_hashes):
            raise ValueError("approval-to-run handoff inputs require all source proof hashes")
        if self.source_future_detector_eligible_count < 0:
            raise ValueError("source_future_detector_eligible_count cannot be negative")
        if self.source_manual_review_count < 0:
            raise ValueError("source_manual_review_count cannot be negative")
        if self.source_terminal_block_count < 0:
            raise ValueError("source_terminal_block_count cannot be negative")
        if self.source_active_forbidden_live_decisions < 0:
            raise ValueError("source_active_forbidden_live_decisions cannot be negative")
        if self.source_credential_findings < 0:
            raise ValueError("source_credential_findings cannot be negative")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ApprovalToRunHandoffInput":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FutureDetectorRunEnvelope:
    envelope_id: str
    handoff_input_id: str
    command_template_id: str
    command_template_enabled: bool
    command_template_allowed_now: bool
    future_bundle_allowed_to_be_prepared: bool
    requires_separate_future_bundle: bool
    requires_explicit_operator_reapproval: bool
    requires_pre_run_safety_scan: bool
    requires_post_run_evidence: bool
    detector_run_allowed_now: bool
    broker_connection_allowed_now: bool
    credential_allowed_now: bool
    live_order_allowed_now: bool
    scheduler_allowed_now: bool
    real_sizing_allowed_now: bool
    paper_only: bool
    live_blocked: bool
    envelope_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        _require_no_runtime_permissions((
            self.command_template_enabled,
            self.command_template_allowed_now,
            self.detector_run_allowed_now,
            self.broker_connection_allowed_now,
            self.credential_allowed_now,
            self.live_order_allowed_now,
            self.scheduler_allowed_now,
            self.real_sizing_allowed_now,
        ))
        required_future_gates = (
            self.requires_separate_future_bundle,
            self.requires_explicit_operator_reapproval,
            self.requires_pre_run_safety_scan,
            self.requires_post_run_evidence,
        )
        if self.future_bundle_allowed_to_be_prepared and not all(required_future_gates):
            raise ValueError("future bundle preparation requires all handoff safety gates")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "FutureDetectorRunEnvelope":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalToRunGateDecision:
    gate_decision_id: str
    handoff_input_id: str
    envelope_id: str
    gate_status: str
    reason_codes: list[str]
    future_bundle_eligible: bool
    detector_run_blocked_now: bool
    detector_run_allowed_now: bool
    broker_connection_allowed_now: bool
    credential_allowed_now: bool
    live_order_allowed_now: bool
    scheduler_allowed_now: bool
    real_sizing_allowed_now: bool
    requires_separate_future_bundle: bool
    requires_explicit_operator_reapproval: bool
    requires_pre_run_safety_scan: bool
    requires_post_run_evidence: bool
    incident_escalation: bool
    next_required_gate: str
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.gate_status not in ALLOWED_HANDOFF_GATE_STATUSES:
            raise ValueError(f"unsupported handoff gate_status: {self.gate_status}")
        _require_no_runtime_permissions((
            self.detector_run_allowed_now,
            self.broker_connection_allowed_now,
            self.credential_allowed_now,
            self.live_order_allowed_now,
            self.scheduler_allowed_now,
            self.real_sizing_allowed_now,
        ))
        if self.detector_run_blocked_now is not True:
            raise ValueError("approval-to-run handoff decisions must block detector_run_now")
        required_future_gates = (
            self.requires_separate_future_bundle,
            self.requires_explicit_operator_reapproval,
            self.requires_pre_run_safety_scan,
            self.requires_post_run_evidence,
        )
        if not all(required_future_gates):
            raise ValueError("approval-to-run handoff decisions require all future-bundle gates")
        if self.future_bundle_eligible and self.gate_status != "eligible_future_bundle_only":
            raise ValueError("future_bundle_eligible requires gate_status=eligible_future_bundle_only")
        if self.gate_status == "eligible_future_bundle_only" and not self.future_bundle_eligible:
            raise ValueError("eligible_future_bundle_only requires future_bundle_eligible=true")
        if self.next_required_gate != APPROVAL_TO_RUN_NEXT_GATE:
            raise ValueError("approval-to-run handoff decisions require the separate future detector bundle gate")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ApprovalToRunGateDecision":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def approval_to_run_handoff_input_hash(record: ApprovalToRunHandoffInput) -> str:
    payload = asdict(record)
    payload["input_hash"] = ""
    return stable_hash(payload)


def future_detector_run_envelope_hash(record: FutureDetectorRunEnvelope) -> str:
    payload = asdict(record)
    payload["envelope_hash"] = ""
    return stable_hash(payload)


def approval_to_run_gate_decision_hash(record: ApprovalToRunGateDecision) -> str:
    payload = asdict(record)
    payload["decision_hash"] = ""
    return stable_hash(payload)
