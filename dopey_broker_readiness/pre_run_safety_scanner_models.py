"""Deterministic models for the read-only detector pre-run safety scanner."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


PRE_RUN_SAFETY_SCANNER_VERSION = "dopey-read-only-detector-pre-run-safety-scanner-v1"
PRE_RUN_NEXT_REQUIRED_GATE = "human_approved_read_only_broker_capability_detector_bundle"
ALLOWED_PRE_RUN_BOUNDARY_STATUSES: frozenset[str] = frozenset({
    "clean",
    "manual_review_required",
    "terminal_block",
})
ALLOWED_PRE_RUN_DECISIONS: frozenset[str] = frozenset({
    "future_bundle_preparation_allowed",
    "manual_review_required",
    "terminal_block",
    "blocked_missing_handoff",
    "blocked_missing_approval_eligibility",
    "blocked_permission_leak",
    "blocked_safety_finding",
    "blocked_credential_finding",
    "blocked_detector_runtime_present",
    "blocked_broker_connection_present",
    "blocked_timeout_misclassified",
})


def _require_paper_live_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("pre-run safety scanner records require paper_only=true and live_blocked=true")


def _require_no_runtime_permissions(values: tuple[bool, ...]) -> None:
    if any(values):
        raise ValueError("pre-run safety scanner records cannot grant runtime permissions")


@dataclass(frozen=True)
class PreRunSafetyScanInput:
    scan_input_id: str
    source_handoff_summary_id: str
    source_approval_intake_summary_id: str
    source_dry_run_summary_id: str
    source_manual_packet_id: str
    source_preflight_id: str
    source_audit_id: str
    source_export_id: str
    source_export_review_id: str
    future_bundle_eligible_count: int
    detector_run_allowed_now_count: int
    broker_connection_allowed_now_count: int
    credential_allowed_now_count: int
    live_order_allowed_now_count: int
    scheduler_allowed_now_count: int
    real_sizing_allowed_now_count: int
    paper_only: bool
    live_blocked: bool
    input_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        required_ids = (
            self.source_handoff_summary_id,
            self.source_approval_intake_summary_id,
            self.source_dry_run_summary_id,
            self.source_manual_packet_id,
            self.source_preflight_id,
            self.source_audit_id,
            self.source_export_id,
            self.source_export_review_id,
        )
        if any(not value for value in required_ids):
            raise ValueError("pre-run scan inputs require all source proof identifiers")
        counts = (
            self.future_bundle_eligible_count,
            self.detector_run_allowed_now_count,
            self.broker_connection_allowed_now_count,
            self.credential_allowed_now_count,
            self.live_order_allowed_now_count,
            self.scheduler_allowed_now_count,
            self.real_sizing_allowed_now_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("pre-run scan input counts cannot be negative")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PreRunSafetyScanInput":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreRunBoundaryScanResult:
    boundary_scan_id: str
    scan_input_id: str
    command_templates_disabled: bool
    separate_future_bundle_required: bool
    explicit_reapproval_required: bool
    pre_run_safety_scan_required: bool
    post_run_evidence_required: bool
    broker_connection_absent: bool
    credential_absent: bool
    env_absent: bool
    network_market_data_absent: bool
    live_order_absent: bool
    order_placement_absent: bool
    order_cancellation_absent: bool
    scheduler_absent: bool
    real_sizing_absent: bool
    buying_power_absent: bool
    account_balance_absent: bool
    robinhood_mcp_absent: bool
    detector_runtime_absent: bool
    forbidden_reference_count: int
    boundary_status: str
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    scan_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.boundary_status not in ALLOWED_PRE_RUN_BOUNDARY_STATUSES:
            raise ValueError(f"unsupported pre-run boundary_status: {self.boundary_status}")
        if self.forbidden_reference_count < 0:
            raise ValueError("forbidden_reference_count cannot be negative")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PreRunBoundaryScanResult":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreRunSafetyDecision:
    decision_id: str
    scan_input_id: str
    boundary_scan_id: str
    decision: str
    future_detector_bundle_preparation_allowed: bool
    detector_run_allowed_now: bool
    broker_connection_allowed_now: bool
    credential_allowed_now: bool
    live_order_allowed_now: bool
    scheduler_allowed_now: bool
    real_sizing_allowed_now: bool
    requires_separate_future_bundle: bool
    requires_explicit_reapproval: bool
    requires_pre_run_safety_scan: bool
    requires_post_run_evidence: bool
    reason_codes: list[str]
    incident_escalation: str
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.decision not in ALLOWED_PRE_RUN_DECISIONS:
            raise ValueError(f"unsupported pre-run safety decision: {self.decision}")
        _require_no_runtime_permissions((
            self.detector_run_allowed_now,
            self.broker_connection_allowed_now,
            self.credential_allowed_now,
            self.live_order_allowed_now,
            self.scheduler_allowed_now,
            self.real_sizing_allowed_now,
        ))
        required_gates = (
            self.requires_separate_future_bundle,
            self.requires_explicit_reapproval,
            self.requires_pre_run_safety_scan,
            self.requires_post_run_evidence,
        )
        if not all(required_gates):
            raise ValueError("pre-run safety decisions require all future-bundle gates")
        if self.future_detector_bundle_preparation_allowed and self.decision != "future_bundle_preparation_allowed":
            raise ValueError("future detector bundle preparation requires the clean allowed decision")
        if self.decision == "future_bundle_preparation_allowed" and self.future_detector_bundle_preparation_allowed is not True:
            raise ValueError("future_bundle_preparation_allowed decision requires preparation_allowed=true")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PreRunSafetyDecision":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def pre_run_safety_scan_input_hash(record: PreRunSafetyScanInput) -> str:
    payload = asdict(record)
    payload["input_hash"] = ""
    return stable_hash(payload)


def pre_run_boundary_scan_result_hash(record: PreRunBoundaryScanResult) -> str:
    payload = asdict(record)
    payload["scan_hash"] = ""
    return stable_hash(payload)


def pre_run_safety_decision_hash(record: PreRunSafetyDecision) -> str:
    payload = asdict(record)
    payload["decision_hash"] = ""
    return stable_hash(payload)
