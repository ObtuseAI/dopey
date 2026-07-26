"""Deterministic offline 0DTE risk model records.

The model is fixture-only and paper-only. It does not fetch quotes, connect to
brokers, place orders, or approve live trading.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ZERO_DTE_RISK_MODEL_VERSION = "dopey-zero-dte-special-lifecycle-risk-model-v1"

ZERO_DTE_ALLOWED_OPTION_TYPES: frozenset[str] = frozenset({"call", "put"})
ZERO_DTE_OPEN_APPROVAL_DECISIONS: frozenset[str] = frozenset({
    "approved_for_paper_open",
    "approved_with_throttle",
})
ZERO_DTE_BLOCKING_DECISIONS: frozenset[str] = frozenset({
    "blocked_liquidity",
    "blocked_spread",
    "blocked_slippage",
    "blocked_iv_shock",
    "blocked_theta_decay",
    "blocked_gamma_instability",
    "blocked_event_risk",
    "blocked_weak_thesis",
    "blocked_missing_exit_plan",
    "blocked_missing_proof",
    "blocked_policy_violation",
    "blocked_live_path",
    "rejected",
})
ZERO_DTE_ALLOWED_DECISIONS: frozenset[str] = ZERO_DTE_OPEN_APPROVAL_DECISIONS.union({
    "prefer_non_zero_dte_alternative",
    "expiry_managed_only",
}).union(ZERO_DTE_BLOCKING_DECISIONS)
ZERO_DTE_RISK_TIERS: frozenset[str] = frozenset({
    "low_fixture_risk",
    "moderate_fixture_risk",
    "high_fixture_risk",
    "blocked_fixture_risk",
})


@dataclass(frozen=True)
class ZeroDTERiskInput:
    candidate_id: str
    underlying: str
    option_type: str
    expiry: str
    trade_date: str
    strike: float
    moneyness: float
    bid: float
    ask: float
    mid: float
    spread_pct: float
    volume: int
    open_interest: int
    implied_volatility: float
    iv_rank_fixture: float
    delta: float
    gamma: float
    theta: float
    vega: float
    liquidity_score: float
    slippage_score: float
    event_risk_score: float
    regime_score: float
    trend_score: float
    reversal_score: float
    macro_risk_score: float
    proof_score: float
    signal_confidence: float
    expected_hold_minutes: int
    explicit_thesis: str
    explicit_exit_or_expiry_plan: str
    paper_only: bool
    live_blocked: bool
    order_action: str
    structure_type: str
    defined_risk: bool
    later_expiry_alternative_available: bool
    expiry_managed_only_requested: bool
    special_close_requested: bool
    special_close_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTERiskInput":
        return cls(
            candidate_id=_string_value(data, "candidate_id"),
            underlying=_string_value(data, "underlying"),
            option_type=_string_value(data, "option_type"),
            expiry=_string_value(data, "expiry"),
            trade_date=_string_value(data, "trade_date"),
            strike=_float_value(data, "strike"),
            moneyness=_float_value(data, "moneyness"),
            bid=_float_value(data, "bid"),
            ask=_float_value(data, "ask"),
            mid=_float_value(data, "mid"),
            spread_pct=_float_value(data, "spread_pct"),
            volume=_int_value(data, "volume"),
            open_interest=_int_value(data, "open_interest"),
            implied_volatility=_float_value(data, "implied_volatility"),
            iv_rank_fixture=_float_value(data, "iv_rank_fixture"),
            delta=_float_value(data, "delta"),
            gamma=_float_value(data, "gamma"),
            theta=_float_value(data, "theta"),
            vega=_float_value(data, "vega"),
            liquidity_score=_float_value(data, "liquidity_score"),
            slippage_score=_float_value(data, "slippage_score"),
            event_risk_score=_float_value(data, "event_risk_score"),
            regime_score=_float_value(data, "regime_score"),
            trend_score=_float_value(data, "trend_score"),
            reversal_score=_float_value(data, "reversal_score"),
            macro_risk_score=_float_value(data, "macro_risk_score"),
            proof_score=_float_value(data, "proof_score"),
            signal_confidence=_float_value(data, "signal_confidence"),
            expected_hold_minutes=_int_value(data, "expected_hold_minutes"),
            explicit_thesis=_string_or_empty(data, "explicit_thesis"),
            explicit_exit_or_expiry_plan=_string_or_empty(data, "explicit_exit_or_expiry_plan"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            order_action=_string_value(data, "order_action"),
            structure_type=_string_value(data, "structure_type"),
            defined_risk=_bool_value(data, "defined_risk"),
            later_expiry_alternative_available=_bool_value(data, "later_expiry_alternative_available"),
            expiry_managed_only_requested=_bool_value(data, "expiry_managed_only_requested"),
            special_close_requested=_bool_value(data, "special_close_requested"),
            special_close_reason=_string_or_empty(data, "special_close_reason"),
        )


@dataclass(frozen=True)
class ZeroDTERiskDecision:
    candidate_id: str
    decision: str
    approval_status: str
    risk_score: float
    risk_tier: str
    required_controls: list[str]
    failed_controls: list[str]
    max_paper_premium_at_risk: float
    max_contracts_paper: int
    expiry_handling_plan: str
    special_close_allowed: bool
    special_close_reason_required: bool
    audit_required: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    decision_hash: str
    threshold_version: str
    score_components: dict[str, float]
    candidate_input: dict[str, Any]
    model_version: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_hash"] = zero_dte_decision_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTERiskDecision":
        return cls(
            candidate_id=_string_value(data, "candidate_id"),
            decision=_string_value(data, "decision"),
            approval_status=_string_value(data, "approval_status"),
            risk_score=_float_value(data, "risk_score"),
            risk_tier=_string_value(data, "risk_tier"),
            required_controls=_string_list_value(data, "required_controls"),
            failed_controls=_string_list_value(data, "failed_controls"),
            max_paper_premium_at_risk=_float_value(data, "max_paper_premium_at_risk"),
            max_contracts_paper=_int_value(data, "max_contracts_paper"),
            expiry_handling_plan=_string_value(data, "expiry_handling_plan"),
            special_close_allowed=_bool_value(data, "special_close_allowed"),
            special_close_reason_required=_bool_value(data, "special_close_reason_required"),
            audit_required=_bool_value(data, "audit_required"),
            reason_codes=_string_list_value(data, "reason_codes"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            decision_hash=_string_or_empty(data, "decision_hash"),
            threshold_version=_string_value(data, "threshold_version"),
            score_components=_float_dict_value(data, "score_components"),
            candidate_input=_dict_value(data, "candidate_input"),
            model_version=_string_value(data, "model_version"),
        )


def zero_dte_decision_hash(decision: ZeroDTERiskDecision) -> str:
    payload = asdict(decision)
    payload["decision_hash"] = ""
    return stable_zero_dte_hash(payload)


def stable_zero_dte_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def zero_dte_decision_from_dict(data: dict[str, Any]) -> ZeroDTERiskDecision:
    return ZeroDTERiskDecision.from_dict(data)


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


def _float_dict_value(data: dict[str, Any], key: str) -> dict[str, float]:
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be dict[str, float]")
    output: dict[str, float] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str):
            raise TypeError(f"{key} keys must be str")
        if isinstance(item_value, bool) or not isinstance(item_value, int | float):
            raise TypeError(f"{key} values must be numeric")
        output[item_key] = float(item_value)
    return output
