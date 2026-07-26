"""Deterministic manual-approval packet records for future read-only detection."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


MANUAL_APPROVAL_PACKET_VERSION = "dopey-read-only-detector-manual-approval-packet-v1"
REQUIRED_OPERATOR_ACKNOWLEDGEMENT = (
    "I APPROVE DOPEY READ-ONLY BROKER CAPABILITY DETECTOR ONLY. "
    "NO CREDENTIAL STORAGE. NO LIVE ORDERS. NO ORDER PLACEMENT. "
    "NO ORDER CANCELLATION. NO SCHEDULER. NO AUTONOMOUS LIVE TRADING. "
    "NO REAL SIZING. READ-ONLY DETECTION ONLY."
)
EXPLICIT_MANUAL_APPROVAL_GATE = "explicit_human_approval_for_read_only_broker_capability_detector_only"

ALLOWED_FUTURE_OPERATIONS: tuple[str, ...] = (
    "simulated_capability_discovery",
    "read_only_capability_discovery_after_manual_approval",
    "read_only_options_tool_inventory_after_manual_approval",
    "read_only_account_metadata_shape_after_manual_approval",
    "read_only_option_chain_shape_after_manual_approval",
    "read_only_option_quote_shape_after_manual_approval",
    "read_only_position_shape_after_manual_approval",
    "read_only_order_status_shape_after_manual_approval",
)
FORBIDDEN_OPERATIONS: tuple[str, ...] = (
    "credential_request",
    "credential_storage",
    "env_file_creation",
    "live_order_review",
    "live_order_placement",
    "order_cancellation",
    "broker_write",
    "broker_execute",
    "real_account_balance_use",
    "real_buying_power_use",
    "real_sizing",
    "scheduler_creation",
    "autonomous_live_loop",
    "network_market_data_scrape",
    "live_trading_enable",
)
ALLOWED_DATA_CLASSES: tuple[str, ...] = (
    "simulated_capability_schema",
    "read_only_broker_metadata_shape",
    "read_only_options_tool_inventory_shape",
    "read_only_option_chain_schema_shape",
    "read_only_option_quote_schema_shape",
    "read_only_position_schema_shape",
    "read_only_order_status_schema_shape",
)
FORBIDDEN_DATA_CLASSES: tuple[str, ...] = (
    "credentials",
    "tokens",
    "env_files",
    "real_account_balance",
    "real_buying_power",
    "real_market_data_values",
    "order_payload_for_execution",
    "order_cancellation_payload",
    "scheduler_state",
    "robinhood_mcp_session",
)
ALLOWED_GATE_STATUSES: frozenset[str] = frozenset({
    "not_requested",
    "packet_ready",
    "approval_missing",
    "approval_invalid",
    "approval_valid_for_read_only_detector_only",
    "expired",
    "revoked",
})
ALLOWED_READINESS_STATUSES: frozenset[str] = frozenset({
    "approval_packet_ready",
    "approval_missing",
    "read_only_detector_not_approved",
    "blocked_safety_failure",
    "blocked_credential_boundary",
    "blocked_broker_boundary",
    "blocked_scheduler_boundary",
    "blocked_network_boundary",
    "blocked_live_execution_boundary",
})


def _validate_paper_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("manual approval records require paper_only=true and live_blocked=true")


@dataclass(frozen=True)
class ReadOnlyDetectorScope:
    scope_id: str
    scope_version: str
    allowed_future_operations: list[str]
    forbidden_operations: list[str]
    allowed_data_classes: list[str]
    forbidden_data_classes: list[str]
    requires_manual_approval: bool
    approval_phrase_required: str
    paper_only: bool
    live_blocked: bool
    scope_hash: str

    def __post_init__(self) -> None:
        _validate_paper_boundary(self.paper_only, self.live_blocked)
        if self.requires_manual_approval is not True:
            raise ValueError("read-only detector scope must require manual approval")
        if self.approval_phrase_required != REQUIRED_OPERATOR_ACKNOWLEDGEMENT:
            raise ValueError("read-only detector scope requires the exact operator acknowledgement")
        missing = set(FORBIDDEN_OPERATIONS).difference(self.forbidden_operations)
        if missing:
            raise ValueError(f"read-only detector scope is missing forbidden operations: {sorted(missing)}")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyDetectorScope":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ManualApprovalGate:
    gate_id: str
    gate_name: str
    gate_status: str
    required_approval_text: str
    approval_present: bool
    approval_valid: bool
    approval_scope: str
    allowed_after_approval: list[str]
    still_forbidden_after_approval: list[str]
    expiration_policy: str
    revocation_policy: str
    paper_only: bool
    live_blocked: bool
    gate_hash: str

    def __post_init__(self) -> None:
        _validate_paper_boundary(self.paper_only, self.live_blocked)
        if self.gate_status not in ALLOWED_GATE_STATUSES:
            raise ValueError(f"unsupported manual approval gate_status: {self.gate_status}")
        if self.required_approval_text != REQUIRED_OPERATOR_ACKNOWLEDGEMENT:
            raise ValueError("manual approval gate requires exact acknowledgement text")
        if self.approval_valid and not self.approval_present:
            raise ValueError("manual approval gate cannot be valid without approval_present=true")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ManualApprovalGate":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadOnlyDetectorApprovalPacket:
    packet_id: str
    packet_version: str
    source_preflight_run_id: str
    scope_id: str
    manual_gate_id: str
    preconditions: list[str]
    blocking_conditions: list[str]
    allowed_future_command_templates: list[str]
    forbidden_command_templates: list[str]
    required_artifacts_before_run: list[str]
    required_artifacts_after_run: list[str]
    operator_acknowledgement_text: str
    readiness_status: str
    next_gate: str
    paper_only: bool
    live_blocked: bool
    packet_hash: str

    def __post_init__(self) -> None:
        _validate_paper_boundary(self.paper_only, self.live_blocked)
        if self.readiness_status not in ALLOWED_READINESS_STATUSES:
            raise ValueError(f"unsupported approval packet readiness_status: {self.readiness_status}")
        if self.next_gate != EXPLICIT_MANUAL_APPROVAL_GATE:
            raise ValueError("approval packet next gate must remain explicit manual approval")
        if self.operator_acknowledgement_text != REQUIRED_OPERATOR_ACKNOWLEDGEMENT:
            raise ValueError("approval packet must carry exact acknowledgement text")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyDetectorApprovalPacket":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def scope_hash(scope: ReadOnlyDetectorScope) -> str:
    payload = asdict(scope)
    payload["scope_hash"] = ""
    return stable_hash(payload)


def gate_hash(gate: ManualApprovalGate) -> str:
    payload = asdict(gate)
    payload["gate_hash"] = ""
    return stable_hash(payload)


def packet_hash(packet: ReadOnlyDetectorApprovalPacket) -> str:
    payload = asdict(packet)
    payload["packet_hash"] = ""
    return stable_hash(payload)


def make_read_only_detector_scope() -> ReadOnlyDetectorScope:
    seed = ReadOnlyDetectorScope(
        scope_id="read-only-detector-scope-v1",
        scope_version=MANUAL_APPROVAL_PACKET_VERSION,
        allowed_future_operations=list(ALLOWED_FUTURE_OPERATIONS),
        forbidden_operations=list(FORBIDDEN_OPERATIONS),
        allowed_data_classes=list(ALLOWED_DATA_CLASSES),
        forbidden_data_classes=list(FORBIDDEN_DATA_CLASSES),
        requires_manual_approval=True,
        approval_phrase_required=REQUIRED_OPERATOR_ACKNOWLEDGEMENT,
        paper_only=True,
        live_blocked=True,
        scope_hash="",
    )
    return ReadOnlyDetectorScope(**{**seed.to_dict(), "scope_hash": scope_hash(seed)})


def make_manual_approval_gate() -> ManualApprovalGate:
    seed = ManualApprovalGate(
        gate_id="manual-approval-gate-read-only-detector-v1",
        gate_name="future_read_only_broker_capability_detector_manual_approval",
        gate_status="packet_ready",
        required_approval_text=REQUIRED_OPERATOR_ACKNOWLEDGEMENT,
        approval_present=False,
        approval_valid=False,
        approval_scope="read_only_broker_capability_detector_only",
        allowed_after_approval=[
            "read_only_capability_shape_detection_only",
            "read_only_options_tool_inventory_shape_detection_only",
            "read_only_metadata_schema_shape_detection_only",
        ],
        still_forbidden_after_approval=list(FORBIDDEN_OPERATIONS),
        expiration_policy="approval_expires_after_single_future_bundle_and_must_be_reconfirmed",
        revocation_policy="any safety drift, scope expansion, or operator revocation resets approval to revoked",
        paper_only=True,
        live_blocked=True,
        gate_hash="",
    )
    return ManualApprovalGate(**{**seed.to_dict(), "gate_hash": gate_hash(seed)})


def make_read_only_detector_approval_packet(source_preflight_run_id: str, scope: ReadOnlyDetectorScope, gate: ManualApprovalGate) -> ReadOnlyDetectorApprovalPacket:
    seed = ReadOnlyDetectorApprovalPacket(
        packet_id="read-only-detector-approval-packet-v1",
        packet_version=MANUAL_APPROVAL_PACKET_VERSION,
        source_preflight_run_id=source_preflight_run_id,
        scope_id=scope.scope_id,
        manual_gate_id=gate.gate_id,
        preconditions=[
            "broker_readiness_preflight_summary_exists",
            "read_only_boundary_simulation_exists",
            "incident_response_terminal_blocks_exist",
            "active_lifecycle_proof_exists",
            "audit_export_review_evidence_exists",
            "operator_acknowledgement_exact_match_required_in_future_bundle",
        ],
        blocking_conditions=[
            "approval_missing",
            "detector_not_approved_now",
            "credentials_forbidden",
            "broker_connection_forbidden",
            "network_market_data_forbidden",
            "scheduler_forbidden",
            "live_order_review_forbidden",
            "order_placement_forbidden",
            "order_cancellation_forbidden",
            "real_sizing_forbidden",
            "robinhood_mcp_forbidden",
        ],
        allowed_future_command_templates=[
            "read_only_capability_detector_requires_approval",
            "read_only_capability_detector_fixture_only_dry_run",
        ],
        forbidden_command_templates=[
            "credentials_or_token_path",
            "env_file",
            "live_execution",
            "order_placement",
            "order_cancellation",
            "scheduler",
            "network_market_data",
            "broker_connection",
        ],
        required_artifacts_before_run=[
            "read_only_detector_scope",
            "manual_approval_gate",
            "read_only_detector_approval_packet",
            "manual_gate_validation_results",
            "manual_approval_boundary_blocks",
            "audit_export_review_pass",
        ],
        required_artifacts_after_run=[
            "detector_scope_used",
            "read_only_detector_run_summary",
            "read_only_detector_no_credentials_proof",
            "read_only_detector_no_write_execute_proof",
            "read_only_detector_no_scheduler_proof",
            "read_only_detector_no_real_sizing_proof",
            "audit_export_review_after_detector",
        ],
        operator_acknowledgement_text=REQUIRED_OPERATOR_ACKNOWLEDGEMENT,
        readiness_status="approval_packet_ready",
        next_gate=EXPLICIT_MANUAL_APPROVAL_GATE,
        paper_only=True,
        live_blocked=True,
        packet_hash="",
    )
    return ReadOnlyDetectorApprovalPacket(**{**seed.to_dict(), "packet_hash": packet_hash(seed)})
