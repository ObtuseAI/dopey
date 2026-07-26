"""Deterministic evidence contract models for read-only detector post-run proof."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


EVIDENCE_CONTRACT_VERSION = "dopey-read-only-detector-post-run-evidence-contract-v1"

CONTRACT_SECTIONS: tuple[str, ...] = (
    "approval_proof_consumed",
    "handoff_proof_consumed",
    "pre_run_safety_proof_consumed",
    "detector_run_request_proof",
    "provider_identity_proof",
    "capability_inventory_proof",
    "blocked_write_execute_proof",
    "credential_absence_proof",
    "scheduler_absence_proof",
    "real_sizing_absence_proof",
    "live_order_absence_proof",
    "broker_mutation_absence_proof",
    "account_balance_buying_power_absence_proof",
    "post_run_audit_proof",
    "export_review_proof",
    "validation_status_proof",
    "next_gate_recommendation",
)

COMPLETENESS_DIMENSIONS: tuple[str, ...] = (
    "gate_proof_completeness",
    "provider_proof_completeness",
    "capability_proof_completeness",
    "blocked_path_proof_completeness",
    "incident_proof_completeness",
    "audit_export_review_proof_completeness",
    "validation_proof_completeness",
    "safety_boundary_proof_completeness",
)

EVIDENCE_CONTRACT_STATUSES: frozenset[str] = frozenset({
    "evidence_contract_complete",
    "evidence_contract_manual_review",
    "evidence_contract_terminal_block",
    "evidence_contract_incomplete",
})

PROMOTION_DECISIONS: frozenset[str] = frozenset({
    "hold_review_only",
    "eligible_for_simulated_quote_order_review_mirror",
    "manual_review_required",
    "terminal_block",
})


def _require_paper_live_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("evidence contract records require paper_only=true and live_blocked=true")


@dataclass(frozen=True)
class DetectorEvidenceItem:
    item_id: str
    section: str
    source_artifact_type: str
    source_path: str
    present: bool
    parseable: bool
    record_count: int
    content_hash: str
    consumed: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    item_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.section not in CONTRACT_SECTIONS:
            raise ValueError(f"unsupported evidence contract section: {self.section}")
        if self.consumed and (not self.present or not self.parseable):
            raise ValueError("consumed evidence items must be present and parseable")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "DetectorEvidenceItem":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DetectorBoundaryAssertion:
    assertion_id: str
    boundary_name: str
    expected_value: Any
    actual_value: Any
    passed: bool
    severity: str
    terminal_block: bool
    manual_review: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    assertion_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.severity not in {"info", "manual_review", "terminal_block"}:
            raise ValueError(f"unsupported boundary assertion severity: {self.severity}")
        if self.passed and (self.terminal_block or self.manual_review):
            raise ValueError("passed boundary assertions cannot terminal-block or require manual review")
        if self.terminal_block and self.severity != "terminal_block":
            raise ValueError("terminal boundary assertions require severity=terminal_block")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "DetectorBoundaryAssertion":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DetectorEvidenceContract:
    contract_id: str
    source_detector_summary_hash: str
    section_statuses: dict[str, bool]
    completeness_dimensions: dict[str, bool]
    completeness_score: int
    status: str
    next_gate_recommendation: str
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    contract_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.status not in EVIDENCE_CONTRACT_STATUSES:
            raise ValueError(f"unsupported evidence contract status: {self.status}")
        if self.not_live_ready is not True:
            raise ValueError("evidence contract cannot clear not_live_ready")
        if not 0 <= self.completeness_score <= 100:
            raise ValueError("evidence completeness score must be between 0 and 100")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "DetectorEvidenceContract":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DetectorEvidenceValidationResult:
    validation_id: str
    contract_id: str
    status: str
    completeness_score: int
    terminal_block_count: int
    manual_review_count: int
    missing_sections: list[str]
    failed_assertions: list[str]
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    validation_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.status not in EVIDENCE_CONTRACT_STATUSES:
            raise ValueError(f"unsupported evidence validation status: {self.status}")
        if self.terminal_block_count > 0 and self.status != "evidence_contract_terminal_block":
            raise ValueError("terminal blocks require evidence_contract_terminal_block status")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "DetectorEvidenceValidationResult":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DetectorEvidencePromotionDecision:
    decision_id: str
    contract_id: str
    decision: str
    allowed_next_stage: str
    forbidden_next_stages: list[str]
    live_trading_allowed: bool
    broker_connection_allowed: bool
    credential_access_allowed: bool
    scheduler_allowed: bool
    real_sizing_allowed: bool
    order_handling_allowed: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.decision not in PROMOTION_DECISIONS:
            raise ValueError(f"unsupported promotion decision: {self.decision}")
        forbidden_flags = (
            self.live_trading_allowed,
            self.broker_connection_allowed,
            self.credential_access_allowed,
            self.scheduler_allowed,
            self.real_sizing_allowed,
            self.order_handling_allowed,
        )
        if any(forbidden_flags):
            raise ValueError("evidence promotion cannot allow live/broker/credential/scheduler/real-sizing/order handling")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "DetectorEvidencePromotionDecision":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detector_evidence_item_hash(record: DetectorEvidenceItem) -> str:
    payload = asdict(record)
    payload["item_hash"] = ""
    return stable_hash(payload)


def detector_boundary_assertion_hash(record: DetectorBoundaryAssertion) -> str:
    payload = asdict(record)
    payload["assertion_hash"] = ""
    return stable_hash(payload)


def detector_evidence_contract_hash(record: DetectorEvidenceContract) -> str:
    payload = asdict(record)
    payload["contract_hash"] = ""
    return stable_hash(payload)


def detector_evidence_validation_hash(record: DetectorEvidenceValidationResult) -> str:
    payload = asdict(record)
    payload["validation_hash"] = ""
    return stable_hash(payload)


def detector_evidence_promotion_hash(record: DetectorEvidencePromotionDecision) -> str:
    payload = asdict(record)
    payload["decision_hash"] = ""
    return stable_hash(payload)
