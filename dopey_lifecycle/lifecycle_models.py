"""Deterministic active option lifecycle records."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ALLOWED_OPTION_TYPES: frozenset[str] = frozenset({"call", "put"})
ALLOWED_STRATEGY_TYPES: frozenset[str] = frozenset({
    "zero_dte_long_call",
    "zero_dte_long_put",
    "swing_long_call",
    "swing_long_put",
    "delayed_rotation_long_call",
    "delayed_rotation_long_put",
})
REQUIRED_LIFECYCLE_STATES: tuple[str, ...] = (
    "signal_detected",
    "candidate_built",
    "policy_validated",
    "risk_validated",
    "allocated_paper",
    "portfolio_checked",
    "stress_checked",
    "incident_checked",
    "paper_open_requested",
    "paper_opened",
    "ledger_recorded",
    "holding",
    "zero_dte_special_lifecycle",
    "zero_dte_expiry_managed",
    "zero_dte_special_close_requested",
    "zero_dte_special_closed",
    "swing_overnight_hold",
    "next_day_close_eligible",
    "rotation_delayed",
    "paper_close_requested",
    "paper_closed",
    "expired_simulated",
    "blocked",
    "rejected",
    "audit_only",
    "terminal_block",
)


def stable_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_option_and_strategy(option_type: str, strategy_type: str) -> None:
    if option_type not in ALLOWED_OPTION_TYPES:
        raise ValueError(f"unsupported lifecycle option_type: {option_type}")
    if strategy_type not in ALLOWED_STRATEGY_TYPES:
        raise ValueError(f"unsupported lifecycle strategy_type: {strategy_type}")


def _validate_paper_flags(paper_only: bool, live_blocked: bool) -> None:
    if paper_only is not True or live_blocked is not True:
        raise ValueError("lifecycle records require paper_only=true and live_blocked=true")


@dataclass(frozen=True)
class LifecycleState:
    state_id: str
    lifecycle_id: str
    state_name: str
    state_rank: int
    trading_day_index: int
    timestamp_label: str
    allowed_next_states: list[str]
    blocked_next_states: list[str]
    state_reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    state_hash: str

    def __post_init__(self) -> None:
        _validate_paper_flags(self.paper_only, self.live_blocked)
        if self.state_name not in REQUIRED_LIFECYCLE_STATES:
            raise ValueError(f"unsupported lifecycle state_name: {self.state_name}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifecycleTransition:
    transition_id: str
    lifecycle_id: str
    from_state: str
    to_state: str
    trading_day_index: int
    transition_allowed: bool
    blocked_reason_codes: list[str]
    required_checks: list[str]
    check_results: dict[str, str]
    paperbroker_result: dict[str, Any]
    account_ledger_result: dict[str, Any]
    no_day_trade_result: dict[str, Any]
    stress_result: dict[str, Any]
    incident_result: dict[str, Any]
    paper_only: bool
    live_blocked: bool
    transition_hash: str

    def __post_init__(self) -> None:
        _validate_paper_flags(self.paper_only, self.live_blocked)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifecycleProofRecord:
    proof_id: str
    lifecycle_id: str
    transition_id: str
    state_id: str
    source_component: str
    proof_type: str
    proof_status: str
    evidence_paths: list[str]
    reason_codes: list[str]
    safety_flags: dict[str, bool]
    paper_only: bool
    live_blocked: bool
    proof_hash: str

    def __post_init__(self) -> None:
        _validate_paper_flags(self.paper_only, self.live_blocked)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActiveOptionLifecycle:
    lifecycle_id: str
    candidate_id: str
    underlying_family_id: str
    synthetic_underlying_symbol: str
    option_type: str
    strategy_type: str
    trade_date: str
    expiry: str
    days_to_expiry: int
    policy_status: str
    allocation_status: str
    portfolio_status: str
    stress_status: str
    incident_status: str
    paperbroker_status: str
    account_ledger_status: str
    current_state: str
    transitions: list[str]
    proof_record_ids: list[str]
    paper_only: bool
    live_blocked: bool
    lifecycle_hash: str

    def __post_init__(self) -> None:
        _validate_option_and_strategy(self.option_type, self.strategy_type)
        _validate_paper_flags(self.paper_only, self.live_blocked)
        if self.current_state not in REQUIRED_LIFECYCLE_STATES:
            raise ValueError(f"unsupported lifecycle current_state: {self.current_state}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def lifecycle_state_hash(state: LifecycleState) -> str:
    payload = asdict(state)
    payload["state_hash"] = ""
    return stable_hash(payload)


def lifecycle_transition_hash(transition: LifecycleTransition) -> str:
    payload = asdict(transition)
    payload["transition_hash"] = ""
    return stable_hash(payload)


def lifecycle_proof_hash(proof: LifecycleProofRecord) -> str:
    payload = asdict(proof)
    payload["proof_hash"] = ""
    return stable_hash(payload)


def active_lifecycle_hash(lifecycle: ActiveOptionLifecycle) -> str:
    payload = asdict(lifecycle)
    payload["lifecycle_hash"] = ""
    return stable_hash(payload)


def make_state(
    state_id: str,
    lifecycle_id: str,
    state_name: str,
    state_rank: int,
    trading_day_index: int,
    reason_codes: list[str],
) -> LifecycleState:
    seed = LifecycleState(
        state_id=state_id,
        lifecycle_id=lifecycle_id,
        state_name=state_name,
        state_rank=state_rank,
        trading_day_index=trading_day_index,
        timestamp_label=f"day-{trading_day_index}-step-{state_rank:02d}",
        allowed_next_states=[],
        blocked_next_states=[],
        state_reason_codes=reason_codes,
        paper_only=True,
        live_blocked=True,
        state_hash="",
    )
    return LifecycleState(**{**seed.to_dict(), "state_hash": lifecycle_state_hash(seed)})


def make_transition(
    transition_id: str,
    lifecycle_id: str,
    from_state: str,
    to_state: str,
    trading_day_index: int,
    transition_allowed: bool,
    blocked_reason_codes: list[str],
    check_results: dict[str, str],
    paperbroker_result: dict[str, Any],
    account_ledger_result: dict[str, Any],
    no_day_trade_result: dict[str, Any],
    stress_result: dict[str, Any],
    incident_result: dict[str, Any],
) -> LifecycleTransition:
    seed = LifecycleTransition(
        transition_id=transition_id,
        lifecycle_id=lifecycle_id,
        from_state=from_state,
        to_state=to_state,
        trading_day_index=trading_day_index,
        transition_allowed=transition_allowed,
        blocked_reason_codes=blocked_reason_codes,
        required_checks=["policy", "allocation", "portfolio", "stress", "incident", "paperbroker", "account_ledger", "no_day_trade"],
        check_results=check_results,
        paperbroker_result=paperbroker_result,
        account_ledger_result=account_ledger_result,
        no_day_trade_result=no_day_trade_result,
        stress_result=stress_result,
        incident_result=incident_result,
        paper_only=True,
        live_blocked=True,
        transition_hash="",
    )
    return LifecycleTransition(**{**seed.to_dict(), "transition_hash": lifecycle_transition_hash(seed)})


def make_proof(
    proof_id: str,
    lifecycle_id: str,
    transition_id: str,
    state_id: str,
    source_component: str,
    proof_type: str,
    proof_status: str,
    evidence_paths: list[str],
    reason_codes: list[str],
) -> LifecycleProofRecord:
    seed = LifecycleProofRecord(
        proof_id=proof_id,
        lifecycle_id=lifecycle_id,
        transition_id=transition_id,
        state_id=state_id,
        source_component=source_component,
        proof_type=proof_type,
        proof_status=proof_status,
        evidence_paths=evidence_paths,
        reason_codes=reason_codes,
        safety_flags={
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
            "no_scheduler": True,
            "no_credentials": True,
        },
        paper_only=True,
        live_blocked=True,
        proof_hash="",
    )
    return LifecycleProofRecord(**{**seed.to_dict(), "proof_hash": lifecycle_proof_hash(seed)})
