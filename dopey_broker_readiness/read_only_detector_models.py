"""Deterministic models for the human-approved read-only detector."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


READ_ONLY_DETECTOR_VERSION = "dopey-human-approved-read-only-broker-capability-detector-v1"
READ_ONLY_DETECTOR_NEXT_GATE = "read_only_detector_post_run_evidence_review_before_any_future_broker_work"

ALLOWED_CAPABILITY_FAMILIES: frozenset[str] = frozenset({
    "tool_inventory",
    "account_metadata_shape",
    "option_chain_shape",
    "option_quote_shape",
    "option_position_shape",
    "option_order_status_shape",
    "option_error_shape",
    "option_order_review_blocked",
    "option_order_placement_blocked",
    "option_order_cancellation_blocked",
    "credential_block",
    "scheduler_block",
    "live_execution_block",
})

ALLOWED_DETECTOR_STATUSES: frozenset[str] = frozenset({
    "not_run_approval_missing",
    "not_run_pre_run_blocked",
    "not_run_manual_review_required",
    "not_run_terminal_block",
    "read_only_detector_fixture_completed",
    "read_only_detector_real_read_only_completed",
    "blocked_scope_violation",
    "blocked_boundary_violation",
})

NOT_RUN_STATUSES: frozenset[str] = frozenset({
    "not_run_approval_missing",
    "not_run_pre_run_blocked",
    "not_run_manual_review_required",
    "not_run_terminal_block",
})


def _require_paper_live_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("read-only detector records require paper_only=true and live_blocked=true")


@dataclass(frozen=True)
class ReadOnlyDetectorRunRequest:
    request_id: str
    source_approval_intake_id: str
    source_handoff_gate_id: str
    source_pre_run_safety_scan_id: str
    approval_valid: bool
    pre_run_clean: bool
    requested_broker_fixture: str
    requested_scope: list[str]
    dry_run_first: bool
    paper_only: bool
    live_blocked: bool
    request_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.dry_run_first is not True:
            raise ValueError("read-only detector requests require dry_run_first=true")
        if not self.requested_scope:
            raise ValueError("read-only detector requests require requested_scope")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyDetectorRunRequest":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadOnlyCapabilityRecord:
    capability_id: str
    broker_name: str
    capability_family: str
    capability_name: str
    read_only: bool
    write_or_execute: bool
    available: bool
    unavailable_reason: str
    schema_shape: dict[str, Any]
    forbidden_fields: list[str]
    allowed_now: bool
    blocked_now: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    record_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.capability_family not in ALLOWED_CAPABILITY_FAMILIES:
            raise ValueError(f"unsupported read-only detector capability_family: {self.capability_family}")
        if self.write_or_execute and self.allowed_now:
            raise ValueError("write/execute capability records cannot be allowed_now")
        if self.write_or_execute and self.blocked_now is not True:
            raise ValueError("write/execute capability records must be blocked_now")
        if any(field in self.schema_shape for field in self.forbidden_fields):
            raise ValueError("capability schema_shape cannot expose forbidden fields")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyCapabilityRecord":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadOnlyDetectorRunResult:
    run_id: str
    request_id: str
    approval_status: str
    pre_run_status: str
    detector_status: str
    broker_connection_attempted: bool
    credential_access_attempted: bool
    network_access_attempted: bool
    live_order_attempted: bool
    order_placement_attempted: bool
    order_cancellation_attempted: bool
    scheduler_attempted: bool
    real_sizing_attempted: bool
    capability_records_total: int
    read_only_records_total: int
    write_execute_blocks_total: int
    credential_blocks_total: int
    scheduler_blocks_total: int
    live_execution_blocks_total: int
    post_run_evidence_written: bool
    paper_only: bool
    live_blocked: bool
    result_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.detector_status not in ALLOWED_DETECTOR_STATUSES:
            raise ValueError(f"unsupported detector_status: {self.detector_status}")
        if any((
            self.credential_access_attempted,
            self.live_order_attempted,
            self.order_placement_attempted,
            self.order_cancellation_attempted,
            self.scheduler_attempted,
            self.real_sizing_attempted,
        )):
            raise ValueError("read-only detector result cannot contain forbidden runtime attempts")
        if self.detector_status in NOT_RUN_STATUSES and self.capability_records_total != 0:
            raise ValueError("not-run detector results cannot contain capability records")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyDetectorRunResult":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_only_detector_run_request_hash(record: ReadOnlyDetectorRunRequest) -> str:
    payload = asdict(record)
    payload["request_hash"] = ""
    return stable_hash(payload)


def read_only_capability_record_hash(record: ReadOnlyCapabilityRecord) -> str:
    payload = asdict(record)
    payload["record_hash"] = ""
    return stable_hash(payload)


def read_only_detector_run_result_hash(record: ReadOnlyDetectorRunResult) -> str:
    payload = asdict(record)
    payload["result_hash"] = ""
    return stable_hash(payload)
