"""Deterministic broker-readiness records."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ALLOWED_CHECK_CATEGORIES: frozenset[str] = frozenset({
    "active_policy",
    "lifecycle",
    "account_ledger",
    "paperbroker",
    "no_day_trade",
    "zero_dte",
    "allocation",
    "portfolio",
    "stress_ladder",
    "incident_response",
    "audit",
    "export_review",
    "credential_boundary",
    "scheduler_boundary",
    "network_boundary",
    "broker_boundary",
    "real_sizing_boundary",
    "manual_approval_boundary",
})
ALLOWED_BOUNDARY_TYPES: frozenset[str] = frozenset({
    "broker_capability_discovery",
    "account_metadata_read",
    "option_chain_read",
    "option_quote_read",
    "position_read",
    "order_status_read",
    "order_review_simulated",
    "order_place_blocked",
    "order_cancel_blocked",
    "credential_request_blocked",
    "scheduler_request_blocked",
    "network_request_blocked",
    "live_execution_blocked",
})
ALLOWED_BROKER_NAMES: frozenset[str] = frozenset({
    "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS",
    "SIMULATED_BROKER_GENERIC_OPTIONS",
})
ALLOWED_READINESS_STATUSES: frozenset[str] = frozenset({
    "not_broker_ready",
    "read_only_boundary_simulated",
    "read_only_detector_not_yet_approved",
    "blocked_missing_manual_approval",
    "blocked_safety_failure",
    "blocked_credential_boundary",
    "blocked_scheduler_boundary",
    "blocked_network_boundary",
    "blocked_live_execution_boundary",
})


def stable_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_paper_boundary(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("broker-readiness records require paper_only=true and live_blocked=true")


@dataclass(frozen=True)
class BrokerReadinessPreflightCheck:
    check_id: str
    check_category: str
    check_name: str
    required_status: str
    actual_status: str
    passed: bool
    blocking: bool
    evidence_paths: list[str]
    failure_reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    check_hash: str

    def __post_init__(self) -> None:
        _validate_paper_boundary(self.paper_only, self.live_blocked)
        if self.check_category not in ALLOWED_CHECK_CATEGORIES:
            raise ValueError(f"unsupported broker readiness check_category: {self.check_category}")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "BrokerReadinessPreflightCheck":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadOnlyBoundarySimulation:
    simulation_id: str
    boundary_type: str
    simulated_request_type: str
    allowed_read_only: bool
    blocked_write_or_execute: bool
    requires_manual_approval: bool
    simulated_response: str
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    simulation_hash: str

    def __post_init__(self) -> None:
        _validate_paper_boundary(self.paper_only, self.live_blocked)
        if self.boundary_type not in ALLOWED_BOUNDARY_TYPES:
            raise ValueError(f"unsupported read-only boundary_type: {self.boundary_type}")
        if self.simulated_request_type in {"place_option_order_blocked", "cancel_order_blocked", "live_execution_blocked"}:
            if self.blocked_write_or_execute is not True:
                raise ValueError("write/execute broker-readiness simulations must be blocked")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ReadOnlyBoundarySimulation":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerCapabilityFixture:
    fixture_id: str
    broker_name: str
    capability_family: str
    capability_name: str
    simulated_supported: bool
    simulated_read_only: bool
    simulated_write_or_execute: bool
    allowed_now: bool
    blocked_now: bool
    future_manual_approval_required: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    fixture_hash: str

    def __post_init__(self) -> None:
        _validate_paper_boundary(self.paper_only, self.live_blocked)
        if self.broker_name not in ALLOWED_BROKER_NAMES:
            raise ValueError(f"broker capability fixtures must use simulated broker names: {self.broker_name}")
        if self.simulated_write_or_execute and not self.blocked_now:
            raise ValueError("write/execute broker capability fixtures must be blocked now")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "BrokerCapabilityFixture":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerReadinessRunResult:
    run_id: str
    preflight_checks_total: int
    preflight_checks_passed: int
    preflight_checks_failed: int
    blocking_failures: int
    read_only_simulations_total: int
    read_only_allowed_count: int
    write_execute_blocked_count: int
    credential_blocks: int
    scheduler_blocks: int
    network_blocks: int
    broker_blocks: int
    manual_approval_required_count: int
    readiness_status: str
    next_required_gate: str
    paper_only: bool
    live_blocked: bool
    run_hash: str

    def __post_init__(self) -> None:
        _validate_paper_boundary(self.paper_only, self.live_blocked)
        if self.readiness_status not in ALLOWED_READINESS_STATUSES:
            raise ValueError(f"unsupported broker readiness_status: {self.readiness_status}")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "BrokerReadinessRunResult":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def preflight_check_hash(check: BrokerReadinessPreflightCheck) -> str:
    payload = asdict(check)
    payload["check_hash"] = ""
    return stable_hash(payload)


def boundary_simulation_hash(simulation: ReadOnlyBoundarySimulation) -> str:
    payload = asdict(simulation)
    payload["simulation_hash"] = ""
    return stable_hash(payload)


def capability_fixture_hash(fixture: BrokerCapabilityFixture) -> str:
    payload = asdict(fixture)
    payload["fixture_hash"] = ""
    return stable_hash(payload)


def run_result_hash(result: BrokerReadinessRunResult) -> str:
    payload = asdict(result)
    payload["run_hash"] = ""
    return stable_hash(payload)


def make_preflight_check(
    check_id: str,
    check_category: str,
    check_name: str,
    actual_status: str,
    evidence_paths: list[str],
    failure_reason_codes: list[str],
    blocking: bool,
) -> BrokerReadinessPreflightCheck:
    seed = BrokerReadinessPreflightCheck(
        check_id=check_id,
        check_category=check_category,
        check_name=check_name,
        required_status="pass",
        actual_status=actual_status,
        passed=actual_status == "pass",
        blocking=blocking,
        evidence_paths=evidence_paths,
        failure_reason_codes=failure_reason_codes,
        paper_only=True,
        live_blocked=True,
        check_hash="",
    )
    return BrokerReadinessPreflightCheck(**{**seed.to_dict(), "check_hash": preflight_check_hash(seed)})


def make_boundary_simulation(
    simulation_id: str,
    boundary_type: str,
    simulated_request_type: str,
    allowed_read_only: bool,
    blocked_write_or_execute: bool,
    requires_manual_approval: bool,
    reason_codes: list[str],
) -> ReadOnlyBoundarySimulation:
    response = "fixture_read_only_allowed" if allowed_read_only else "blocked_before_broker_or_live_path"
    seed = ReadOnlyBoundarySimulation(
        simulation_id=simulation_id,
        boundary_type=boundary_type,
        simulated_request_type=simulated_request_type,
        allowed_read_only=allowed_read_only,
        blocked_write_or_execute=blocked_write_or_execute,
        requires_manual_approval=requires_manual_approval,
        simulated_response=response,
        reason_codes=reason_codes,
        paper_only=True,
        live_blocked=True,
        simulation_hash="",
    )
    return ReadOnlyBoundarySimulation(**{**seed.to_dict(), "simulation_hash": boundary_simulation_hash(seed)})


def make_capability_fixture(
    fixture_id: str,
    broker_name: str,
    capability_family: str,
    capability_name: str,
    simulated_supported: bool,
    simulated_read_only: bool,
    simulated_write_or_execute: bool,
    allowed_now: bool,
    blocked_now: bool,
    future_manual_approval_required: bool,
    reason_codes: list[str],
) -> BrokerCapabilityFixture:
    seed = BrokerCapabilityFixture(
        fixture_id=fixture_id,
        broker_name=broker_name,
        capability_family=capability_family,
        capability_name=capability_name,
        simulated_supported=simulated_supported,
        simulated_read_only=simulated_read_only,
        simulated_write_or_execute=simulated_write_or_execute,
        allowed_now=allowed_now,
        blocked_now=blocked_now,
        future_manual_approval_required=future_manual_approval_required,
        reason_codes=reason_codes,
        paper_only=True,
        live_blocked=True,
        fixture_hash="",
    )
    return BrokerCapabilityFixture(**{**seed.to_dict(), "fixture_hash": capability_fixture_hash(seed)})


def make_run_result(
    run_id: str,
    checks: list[BrokerReadinessPreflightCheck],
    simulations: list[ReadOnlyBoundarySimulation],
) -> BrokerReadinessRunResult:
    blocking_failures = sum(1 for check in checks if check.blocking and not check.passed)
    seed = BrokerReadinessRunResult(
        run_id=run_id,
        preflight_checks_total=len(checks),
        preflight_checks_passed=sum(1 for check in checks if check.passed),
        preflight_checks_failed=sum(1 for check in checks if not check.passed),
        blocking_failures=blocking_failures,
        read_only_simulations_total=len(simulations),
        read_only_allowed_count=sum(1 for simulation in simulations if simulation.allowed_read_only),
        write_execute_blocked_count=sum(1 for simulation in simulations if simulation.blocked_write_or_execute),
        credential_blocks=sum(1 for simulation in simulations if "credential" in simulation.boundary_type or "credential" in simulation.simulated_request_type),
        scheduler_blocks=sum(1 for simulation in simulations if "scheduler" in simulation.boundary_type or "scheduler" in simulation.simulated_request_type),
        network_blocks=sum(1 for simulation in simulations if "network" in simulation.boundary_type or "network" in simulation.simulated_request_type),
        broker_blocks=sum(1 for simulation in simulations if "broker" in simulation.boundary_type or "broker" in simulation.simulated_request_type or "robinhood" in simulation.simulated_request_type),
        manual_approval_required_count=sum(1 for check in checks if check.check_category == "manual_approval_boundary") + sum(1 for simulation in simulations if simulation.requires_manual_approval),
        readiness_status="read_only_boundary_simulated" if blocking_failures == 0 else "blocked_safety_failure",
        next_required_gate="explicit_human_approval_for_future_read_only_capability_detector_bundle",
        paper_only=True,
        live_blocked=True,
        run_hash="",
    )
    return BrokerReadinessRunResult(**{**seed.to_dict(), "run_hash": run_result_hash(seed)})
