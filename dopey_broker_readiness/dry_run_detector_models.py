"""Fixture-only schemas for a future read-only detector dry run."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


DRY_RUN_VALIDATOR_VERSION = "dopey-read-only-detector-dry-run-fixture-validator-v1"
ALLOWED_SIMULATED_BROKERS: frozenset[str] = frozenset({
    "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS",
    "SIMULATED_GENERIC_OPTIONS_BROKER",
})
ALLOWED_CAPABILITY_FAMILIES: frozenset[str] = frozenset({
    "capability_discovery",
    "account_metadata_shape",
    "option_chain_shape",
    "option_quote_shape",
    "option_position_shape",
    "option_order_status_shape",
    "option_order_review_shape_simulated",
    "order_placement_block",
    "order_cancellation_block",
    "credential_block",
    "scheduler_block",
    "live_execution_block",
})
ALLOWED_DRY_RUN_STATUSES: frozenset[str] = frozenset({
    "dry_run_fixture_validated",
    "approval_missing_detector_not_run",
    "blocked_detector_run_attempt",
    "blocked_broker_connection_attempt",
    "blocked_credential_attempt",
    "blocked_live_execution_attempt",
    "blocked_schema_violation",
})
ALLOWED_READ_ONLY_REQUEST_CLASSES: tuple[str, ...] = (
    "capability_discovery",
    "tool_inventory_shape_discovery",
    "account_metadata_shape_discovery",
    "option_chain_shape_discovery",
    "option_quote_shape_discovery",
    "option_position_shape_discovery",
    "option_order_status_shape_discovery",
    "option_order_review_shape_simulated_fixture_only",
)
FORBIDDEN_REQUEST_CLASSES: tuple[str, ...] = (
    "credential_read",
    "token_read",
    "env_file_access",
    "broker_connection",
    "network_market_data",
    "live_order_review",
    "order_placement",
    "order_cancellation",
    "real_account_balance",
    "real_buying_power",
    "real_sizing",
    "scheduler_creation",
    "autonomous_live_loop",
    "broker_write",
    "broker_execute",
)
FORBIDDEN_SHAPE_FIELDS: tuple[str, ...] = (
    "credential",
    "credentials",
    "token",
    "api_key",
    "env",
    ".env",
    "broker_connection",
    "connection_handle",
    "network_url",
    "live_execution",
    "order_payload",
    "cancel_payload",
    "real_order_id",
    "account_balance",
    "buying_power",
    "real_sizing",
    "scheduler",
)


def _require_paper_live_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("dry-run detector records require paper_only=true and live_blocked=true")


@dataclass(frozen=True)
class ReadOnlyDetectorDryRunInput:
    dry_run_id: str
    source_approval_packet_id: str
    approval_status: str
    detector_approved: bool
    simulated_broker_name: str
    simulated_request_classes: list[str]
    forbidden_request_classes: list[str]
    manual_gate_required: bool
    paper_only: bool
    live_blocked: bool
    input_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.approval_status != "approval_missing":
            raise ValueError("dry-run inputs must keep approval_status=approval_missing")
        if self.detector_approved is not False:
            raise ValueError("dry-run inputs must keep detector_approved=false")
        if self.manual_gate_required is not True:
            raise ValueError("dry-run inputs must require the manual gate")
        if self.simulated_broker_name not in ALLOWED_SIMULATED_BROKERS:
            raise ValueError(f"unsupported simulated broker: {self.simulated_broker_name}")
        unsupported = set(self.simulated_request_classes).difference(ALLOWED_READ_ONLY_REQUEST_CLASSES)
        if unsupported:
            raise ValueError(f"unsupported read-only request classes: {sorted(unsupported)}")
        missing = set(FORBIDDEN_REQUEST_CLASSES).difference(self.forbidden_request_classes)
        if missing:
            raise ValueError(f"missing forbidden request classes: {sorted(missing)}")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyDetectorDryRunInput":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulatedBrokerCapabilityResponse:
    response_id: str
    simulated_broker_name: str
    capability_family: str
    capability_name: str
    read_only_shape_available: bool
    write_or_execute_shape_blocked: bool
    requires_manual_approval: bool
    simulated_schema: dict[str, Any]
    forbidden_fields: list[str]
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    response_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.simulated_broker_name not in ALLOWED_SIMULATED_BROKERS:
            raise ValueError(f"unsupported simulated broker: {self.simulated_broker_name}")
        if self.capability_family not in ALLOWED_CAPABILITY_FAMILIES:
            raise ValueError(f"unsupported capability family: {self.capability_family}")
        if self.requires_manual_approval is not True:
            raise ValueError("simulated responses must still require future manual approval")
        forbidden = set(FORBIDDEN_SHAPE_FIELDS).intersection(self.simulated_schema)
        if forbidden:
            raise ValueError(f"simulated schema contains forbidden fields: {sorted(forbidden)}")
        if self.capability_family.endswith("_block") or self.capability_family in {"order_placement_block", "order_cancellation_block"}:
            if self.write_or_execute_shape_blocked is not True:
                raise ValueError("block capability families must block write/execute shapes")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "SimulatedBrokerCapabilityResponse":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadOnlyDetectorDryRunResult:
    dry_run_id: str
    inputs_validated: int
    schemas_validated: int
    simulated_responses_validated: int
    allowed_read_only_shapes: int
    blocked_write_execute_shapes: int
    credential_blocks: int
    scheduler_blocks: int
    network_blocks: int
    live_execution_blocks: int
    approval_required: bool
    approval_present: bool
    detector_run_attempted: bool
    broker_connection_attempted: bool
    credential_access_attempted: bool
    network_access_attempted: bool
    live_order_attempted: bool
    dry_run_status: str
    paper_only: bool
    live_blocked: bool
    result_hash: str

    def __post_init__(self) -> None:
        _require_paper_live_boundary(self.paper_only, self.live_blocked)
        if self.dry_run_status not in ALLOWED_DRY_RUN_STATUSES:
            raise ValueError(f"unsupported dry-run status: {self.dry_run_status}")
        if self.approval_required is not True or self.approval_present is not False:
            raise ValueError("dry-run results must keep approval required and absent")
        attempted = [
            self.detector_run_attempted,
            self.broker_connection_attempted,
            self.credential_access_attempted,
            self.network_access_attempted,
            self.live_order_attempted,
        ]
        if any(attempted) and not self.dry_run_status.startswith("blocked_"):
            raise ValueError("attempted unsafe actions require blocked dry-run status")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyDetectorDryRunResult":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dry_run_input_hash(record: ReadOnlyDetectorDryRunInput) -> str:
    payload = asdict(record)
    payload["input_hash"] = ""
    return stable_hash(payload)


def simulated_response_hash(record: SimulatedBrokerCapabilityResponse) -> str:
    payload = asdict(record)
    payload["response_hash"] = ""
    return stable_hash(payload)


def dry_run_result_hash(record: ReadOnlyDetectorDryRunResult) -> str:
    payload = asdict(record)
    payload["result_hash"] = ""
    return stable_hash(payload)
