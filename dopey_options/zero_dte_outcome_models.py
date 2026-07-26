"""Deterministic offline 0DTE expiry/outcome replay records.

The replay model is fixture-only and advisory. It never fetches market data,
connects to brokers, places orders, or approves live trading.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ZERO_DTE_REPLAY_MODEL_VERSION = "dopey-zero-dte-expiry-outcome-replay-simulator-v1"

ZERO_DTE_REPLAY_ACTIONS: frozenset[str] = frozenset({
    "hold",
    "special_close_simulated",
    "expiry_manage",
    "blocked_close_missing_reason",
    "blocked_close_liquidity",
    "blocked_close_risk_cap",
    "blocked_normal_day_trade",
    "expire_worthless_simulated",
    "expire_intrinsic_value_simulated",
    "prefer_non_zero_dte_alternative",
    "reject_replay",
})

ZERO_DTE_REPLAY_OUTCOME_TYPES: frozenset[str] = frozenset({
    "approved_survived_fixture",
    "approved_decayed",
    "approved_spiked_then_failed",
    "approved_special_close_helped",
    "approved_expiry_managed_success",
    "approved_expiry_managed_failure",
    "approved_should_have_been_throttled_more",
    "throttled_correctly",
    "blocked_correctly",
    "blocked_maybe_too_strict",
    "prefer_later_expiry_confirmed",
    "prefer_later_expiry_missed_opportunity",
    "rejected_policy_violation",
    "inconclusive_fixture",
})

ZERO_DTE_EXPIRY_STATES: frozenset[str] = frozenset({
    "expires_worthless_simulated",
    "expires_itm_intrinsic_value_simulated",
    "pin_risk_simulated",
    "assignment_exercise_risk_flagged_simulated_only",
    "expiry_managed_hold_to_close",
    "expiry_managed_special_close",
    "expiry_manage_blocked",
})

ZERO_DTE_THRESHOLD_FEEDBACK_ACTIONS: frozenset[str] = frozenset({
    "tighten_spread_threshold",
    "loosen_spread_threshold_candidate",
    "tighten_liquidity_threshold",
    "tighten_gamma_instability_threshold",
    "tighten_theta_decay_threshold",
    "tighten_iv_overpayment_threshold",
    "increase_proof_score_requirement",
    "prefer_later_expiry_more_often",
    "allow_throttle_not_full_block",
    "keep_block_reason_validated",
    "mark_inconclusive_needs_more_fixture_coverage",
})


@dataclass(frozen=True)
class ZeroDTEReplayInput:
    replay_id: str
    candidate_id: str
    source_decision_id: str
    underlying: str
    option_type: str
    trade_date: str
    expiry: str
    strike: float
    open_price: float
    max_paper_premium_at_risk: float
    max_contracts_paper: int
    risk_tier: str
    decision: str
    reason_codes: list[str]
    proof_score: float
    signal_confidence: float
    liquidity_score: float
    slippage_score: float
    spread_pct: float
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float
    event_risk_score: float
    regime_score: float
    explicit_thesis: str
    explicit_exit_or_expiry_plan: str
    fixture_path_id: str
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEReplayInput":
        return cls(
            replay_id=_string_value(data, "replay_id"),
            candidate_id=_string_value(data, "candidate_id"),
            source_decision_id=_string_value(data, "source_decision_id"),
            underlying=_string_value(data, "underlying"),
            option_type=_string_value(data, "option_type"),
            trade_date=_string_value(data, "trade_date"),
            expiry=_string_value(data, "expiry"),
            strike=_float_value(data, "strike"),
            open_price=_float_value(data, "open_price"),
            max_paper_premium_at_risk=_float_value(data, "max_paper_premium_at_risk"),
            max_contracts_paper=_int_value(data, "max_contracts_paper"),
            risk_tier=_string_value(data, "risk_tier"),
            decision=_string_value(data, "decision"),
            reason_codes=_string_list_value(data, "reason_codes"),
            proof_score=_float_value(data, "proof_score"),
            signal_confidence=_float_value(data, "signal_confidence"),
            liquidity_score=_float_value(data, "liquidity_score"),
            slippage_score=_float_value(data, "slippage_score"),
            spread_pct=_float_value(data, "spread_pct"),
            delta=_float_value(data, "delta"),
            gamma=_float_value(data, "gamma"),
            theta=_float_value(data, "theta"),
            vega=_float_value(data, "vega"),
            implied_volatility=_float_value(data, "implied_volatility"),
            event_risk_score=_float_value(data, "event_risk_score"),
            regime_score=_float_value(data, "regime_score"),
            explicit_thesis=_string_or_empty(data, "explicit_thesis"),
            explicit_exit_or_expiry_plan=_string_or_empty(data, "explicit_exit_or_expiry_plan"),
            fixture_path_id=_string_value(data, "fixture_path_id"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
        )


@dataclass(frozen=True)
class ZeroDTEIntradayState:
    state_id: str
    minute_index: int
    underlying_price: float
    option_mid: float
    option_bid: float
    option_ask: float
    spread_pct: float
    estimated_slippage: float
    delta: float
    gamma: float
    theta: float
    implied_volatility: float
    liquidity_score: float
    signal_state: str
    risk_event: str
    close_signal: str
    expiry_pressure_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEIntradayState":
        return cls(
            state_id=_string_value(data, "state_id"),
            minute_index=_int_value(data, "minute_index"),
            underlying_price=_float_value(data, "underlying_price"),
            option_mid=_float_value(data, "option_mid"),
            option_bid=_float_value(data, "option_bid"),
            option_ask=_float_value(data, "option_ask"),
            spread_pct=_float_value(data, "spread_pct"),
            estimated_slippage=_float_value(data, "estimated_slippage"),
            delta=_float_value(data, "delta"),
            gamma=_float_value(data, "gamma"),
            theta=_float_value(data, "theta"),
            implied_volatility=_float_value(data, "implied_volatility"),
            liquidity_score=_float_value(data, "liquidity_score"),
            signal_state=_string_value(data, "signal_state"),
            risk_event=_string_or_empty(data, "risk_event"),
            close_signal=_string_or_empty(data, "close_signal"),
            expiry_pressure_score=_float_value(data, "expiry_pressure_score"),
        )


@dataclass(frozen=True)
class ZeroDTEReplayDecisionPoint:
    decision_point_id: str
    minute_index: int
    state_id: str
    action: str
    allowed: bool
    reason_codes: list[str]
    special_close_required: bool
    special_close_allowed: bool
    expiry_manage_allowed: bool
    no_day_trade_exception_type: str
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEReplayDecisionPoint":
        action = _string_value(data, "action")
        if action not in ZERO_DTE_REPLAY_ACTIONS:
            raise ValueError(f"unsupported replay action: {action}")
        return cls(
            decision_point_id=_string_value(data, "decision_point_id"),
            minute_index=_int_value(data, "minute_index"),
            state_id=_string_value(data, "state_id"),
            action=action,
            allowed=_bool_value(data, "allowed"),
            reason_codes=_string_list_value(data, "reason_codes"),
            special_close_required=_bool_value(data, "special_close_required"),
            special_close_allowed=_bool_value(data, "special_close_allowed"),
            expiry_manage_allowed=_bool_value(data, "expiry_manage_allowed"),
            no_day_trade_exception_type=_string_or_empty(data, "no_day_trade_exception_type"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
        )


@dataclass(frozen=True)
class ZeroDTEReplayOutcome:
    replay_id: str
    candidate_id: str
    decision: str
    outcome_type: str
    outcome_score: float
    premium_outcome_pct: float
    max_adverse_excursion_pct: float
    max_favorable_excursion_pct: float
    theta_decay_realized: float
    gamma_opportunity_realized: float
    slippage_realized: float
    expiry_state: str
    special_close_used: bool
    special_close_reason: str
    blocked_reason_codes: list[str]
    risk_model_alignment: str
    threshold_feedback: list[str]
    recursive_improvement_tags: list[str]
    paper_only: bool
    live_blocked: bool
    replay_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["replay_hash"] = zero_dte_replay_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEReplayOutcome":
        outcome_type = _string_value(data, "outcome_type")
        if outcome_type not in ZERO_DTE_REPLAY_OUTCOME_TYPES:
            raise ValueError(f"unsupported replay outcome type: {outcome_type}")
        expiry_state = _string_value(data, "expiry_state")
        if expiry_state not in ZERO_DTE_EXPIRY_STATES:
            raise ValueError(f"unsupported expiry state: {expiry_state}")
        return cls(
            replay_id=_string_value(data, "replay_id"),
            candidate_id=_string_value(data, "candidate_id"),
            decision=_string_value(data, "decision"),
            outcome_type=outcome_type,
            outcome_score=_float_value(data, "outcome_score"),
            premium_outcome_pct=_float_value(data, "premium_outcome_pct"),
            max_adverse_excursion_pct=_float_value(data, "max_adverse_excursion_pct"),
            max_favorable_excursion_pct=_float_value(data, "max_favorable_excursion_pct"),
            theta_decay_realized=_float_value(data, "theta_decay_realized"),
            gamma_opportunity_realized=_float_value(data, "gamma_opportunity_realized"),
            slippage_realized=_float_value(data, "slippage_realized"),
            expiry_state=expiry_state,
            special_close_used=_bool_value(data, "special_close_used"),
            special_close_reason=_string_or_empty(data, "special_close_reason"),
            blocked_reason_codes=_string_list_value(data, "blocked_reason_codes"),
            risk_model_alignment=_string_value(data, "risk_model_alignment"),
            threshold_feedback=_string_list_value(data, "threshold_feedback"),
            recursive_improvement_tags=_string_list_value(data, "recursive_improvement_tags"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            replay_hash=_string_or_empty(data, "replay_hash"),
        )


@dataclass(frozen=True)
class ZeroDTEExpiryManagementRecord:
    replay_id: str
    candidate_id: str
    expiry_state: str
    intrinsic_value_estimate: float
    paper_premium_outcome_pct: float
    risk_flags: list[str]
    special_close_would_reduce_risk: bool
    expiry_managed_only_decision_correct: bool
    broker_instruction: str
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ZeroDTEThresholdFeedbackRecord:
    replay_id: str
    candidate_id: str
    outcome_type: str
    recommendations: list[str]
    rationale_codes: list[str]
    advisory_only: bool
    live_threshold_mutation_allowed: bool
    paper_only: bool
    live_blocked: bool
    feedback_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["feedback_hash"] = stable_zero_dte_replay_hash({**payload, "feedback_hash": ""})
        return payload


def zero_dte_replay_hash(outcome: ZeroDTEReplayOutcome) -> str:
    payload = asdict(outcome)
    payload["replay_hash"] = ""
    return stable_zero_dte_replay_hash(payload)


def stable_zero_dte_replay_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def zero_dte_replay_input_from_risk_decision(
    replay_id: str,
    fixture_path_id: str,
    decision: dict[str, Any],
) -> ZeroDTEReplayInput:
    candidate_input = _dict_value(decision, "candidate_input")
    return ZeroDTEReplayInput(
        replay_id=replay_id,
        candidate_id=_string_value(decision, "candidate_id"),
        source_decision_id=_string_value(decision, "decision_hash"),
        underlying=_string_value(candidate_input, "underlying"),
        option_type=_string_value(candidate_input, "option_type"),
        trade_date=_string_value(candidate_input, "trade_date"),
        expiry=_string_value(candidate_input, "expiry"),
        strike=_float_value(candidate_input, "strike"),
        open_price=_float_value(candidate_input, "mid"),
        max_paper_premium_at_risk=_float_value(decision, "max_paper_premium_at_risk"),
        max_contracts_paper=_int_value(decision, "max_contracts_paper"),
        risk_tier=_string_value(decision, "risk_tier"),
        decision=_string_value(decision, "decision"),
        reason_codes=_string_list_value(decision, "reason_codes"),
        proof_score=_float_value(candidate_input, "proof_score"),
        signal_confidence=_float_value(candidate_input, "signal_confidence"),
        liquidity_score=_float_value(candidate_input, "liquidity_score"),
        slippage_score=_float_value(candidate_input, "slippage_score"),
        spread_pct=_float_value(candidate_input, "spread_pct"),
        delta=_float_value(candidate_input, "delta"),
        gamma=_float_value(candidate_input, "gamma"),
        theta=_float_value(candidate_input, "theta"),
        vega=_float_value(candidate_input, "vega"),
        implied_volatility=_float_value(candidate_input, "implied_volatility"),
        event_risk_score=_float_value(candidate_input, "event_risk_score"),
        regime_score=_float_value(candidate_input, "regime_score"),
        explicit_thesis=_string_or_empty(candidate_input, "explicit_thesis"),
        explicit_exit_or_expiry_plan=_string_or_empty(candidate_input, "explicit_exit_or_expiry_plan"),
        fixture_path_id=fixture_path_id,
        paper_only=True,
        live_blocked=True,
    )


def _string_value(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    if not value:
        raise ValueError(f"{key} must not be empty")
    return value


def _string_or_empty(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    return value


def _bool_value(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _int_value(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _float_value(data: dict[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _dict_value(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be dict")
    return dict(value)


def _string_list_value(data: dict[str, Any], key: str) -> list[str]:
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be list[str]")
    return list(value)
