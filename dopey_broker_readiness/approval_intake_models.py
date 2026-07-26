"""Deterministic models for read-only detector approval intake."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


APPROVAL_INTAKE_VALIDATOR_VERSION = "dopey-read-only-detector-approval-intake-validator-v1"
APPROVAL_INTAKE_NEXT_GATE = "separate_explicitly_approved_read_only_detector_run_bundle"
ALLOWED_APPROVAL_CHANNELS: frozenset[str] = frozenset({
    "fixture",
    "manual_text_fixture",
    "absent",
    "invalid_fixture",
    "future_operator_input_placeholder",
})
ALLOWED_VALIDATION_STATUSES: frozenset[str] = frozenset({
    "missing",
    "invalid",
    "valid_exact_read_only_detector_only_fixture",
    "manual_review_required",
    "terminal_block",
})


def _require_paper_live_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("approval-intake records require paper_only=true and live_blocked=true")


@dataclass(frozen=True)
class ApprovalIntakeRequest:
    request_id: str
    source_packet_id: str
    source_required_acknowledgement_hash: str
    operator_text: str
    operator_text_present: bool
    approval_channel: str
    approval_timestamp_label: str
    scope_claims: list[str]
    paper_only: bool
    live_blocked: bool
    request_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.approval_channel not in ALLOWED_APPROVAL_CHANNELS:
            raise ValueError(f"unsupported approval_channel: {self.approval_channel}")
        if self.approval_channel in {"absent", "future_operator_input_placeholder"} and self.operator_text_present:
            raise ValueError("absent and placeholder approval channels cannot carry operator text")
        if not self.source_required_acknowledgement_hash:
            raise ValueError("approval-intake request requires source_required_acknowledgement_hash")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ApprovalIntakeRequest":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalScopeValidation:
    validation_id: str
    request_id: str
    exact_text_match: bool
    missing_approval: bool
    partial_approval: bool
    extra_scope_detected: bool
    forbidden_terms_detected: list[str]
    allowed_scope_only: bool
    read_only_detector_only: bool
    credential_scope_detected: bool
    live_trading_scope_detected: bool
    order_placement_scope_detected: bool
    order_cancellation_scope_detected: bool
    scheduler_scope_detected: bool
    autonomous_loop_scope_detected: bool
    real_sizing_scope_detected: bool
    broker_execute_scope_detected: bool
    validation_status: str
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    validation_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.validation_status not in ALLOWED_VALIDATION_STATUSES:
            raise ValueError(f"unsupported approval validation_status: {self.validation_status}")
        if self.validation_status == "valid_exact_read_only_detector_only_fixture":
            if self.exact_text_match is not True or self.allowed_scope_only is not True:
                raise ValueError("valid approval-intake fixtures require exact text and allowed_scope_only=true")
            if self.forbidden_terms_detected:
                raise ValueError("valid approval-intake fixtures cannot contain forbidden terms")
        if self.validation_status == "missing" and self.missing_approval is not True:
            raise ValueError("missing validation_status requires missing_approval=true")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ApprovalScopeValidation":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalIntakeResult:
    result_id: str
    request_id: str
    validation_id: str
    approval_valid: bool
    approval_effective_now: bool
    future_detector_eligible_for_next_bundle: bool
    detector_run_allowed_now: bool
    broker_connection_allowed_now: bool
    credential_allowed_now: bool
    live_order_allowed_now: bool
    scheduler_allowed_now: bool
    real_sizing_allowed_now: bool
    next_required_gate: str
    incident_escalation: bool
    paper_only: bool
    live_blocked: bool
    result_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        forbidden_runtime_permissions = [
            self.approval_effective_now,
            self.detector_run_allowed_now,
            self.broker_connection_allowed_now,
            self.credential_allowed_now,
            self.live_order_allowed_now,
            self.scheduler_allowed_now,
            self.real_sizing_allowed_now,
        ]
        if any(forbidden_runtime_permissions):
            raise ValueError("approval-intake results cannot grant runtime permissions in this bundle")
        if self.future_detector_eligible_for_next_bundle and not self.approval_valid:
            raise ValueError("future detector eligibility requires an exact valid fixture approval")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ApprovalIntakeResult":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def approval_intake_request_hash(record: ApprovalIntakeRequest) -> str:
    payload = asdict(record)
    payload["request_hash"] = ""
    return stable_hash(payload)


def approval_scope_validation_hash(record: ApprovalScopeValidation) -> str:
    payload = asdict(record)
    payload["validation_hash"] = ""
    return stable_hash(payload)


def approval_intake_result_hash(record: ApprovalIntakeResult) -> str:
    payload = asdict(record)
    payload["result_hash"] = ""
    return stable_hash(payload)


def make_absent_approval_intake_request(source_packet_id: str, acknowledgement_hash: str) -> ApprovalIntakeRequest:
    seed = ApprovalIntakeRequest(
        request_id="approval-intake-default-absent",
        source_packet_id=source_packet_id,
        source_required_acknowledgement_hash=acknowledgement_hash,
        operator_text="",
        operator_text_present=False,
        approval_channel="absent",
        approval_timestamp_label="absent",
        scope_claims=["approval_missing"],
        paper_only=True,
        live_blocked=True,
        request_hash="",
    )
    return ApprovalIntakeRequest(**{**seed.to_dict(), "request_hash": approval_intake_request_hash(seed)})
