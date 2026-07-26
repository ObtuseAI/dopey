"""Deterministic offline 0DTE adversarial fixture records."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ADVERSARIAL_CASE_FAMILIES: frozenset[str] = frozenset({
    "approved_candidate_stress",
    "blocked_candidate_validation",
    "blocked_maybe_overstrict",
    "throttled_candidate_stress",
    "later_expiry_alternative",
    "special_close_stress",
    "expiry_management_stress",
    "gamma_theta_adversarial",
    "liquidity_spread_adversarial",
    "iv_event_adversarial",
    "regime_reversal_adversarial",
    "policy_loophole_adversarial",
})

ADVERSARIAL_RISK_VECTORS: frozenset[str] = frozenset({
    "liquidity_decay",
    "spread_explosion",
    "slippage_spike",
    "gamma_reversal",
    "theta_bleed",
    "iv_crush",
    "iv_overpayment",
    "event_shock",
    "macro_reversal",
    "false_breakout",
    "false_breakdown",
    "pin_risk",
    "late_day_liquidity_collapse",
    "missing_thesis",
    "missing_exit_plan",
    "same_day_churn_attempt",
    "unsupported_structure_attempt",
    "live_path_attempt",
})

FORBIDDEN_LIVE_MARKET_TOKENS: frozenset[str] = frozenset({
    "polygon",
    "iex",
    "yfinance",
    "real_quote",
    "broker_quote",
    "live_quote",
    "robinhood_quote",
    "alpaca_quote",
    "tradier_quote",
})


@dataclass(frozen=True)
class ZeroDTEAdversarialFixtureCase:
    case_id: str
    case_family: str
    adversarial_theme: str
    underlying: str
    option_type: str
    candidate_type: str
    baseline_expected_decision: str
    adversarial_expected_outcome: str
    primary_risk_vector: str
    secondary_risk_vectors: list[str]
    proof_stress_type: str
    liquidity_stress_type: str
    greeks_stress_type: str
    iv_stress_type: str
    event_stress_type: str
    regime_stress_type: str
    expected_threshold_feedback: list[str]
    expected_optimizer_effect: str
    paper_only: bool
    live_blocked: bool
    fixture_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_adversarial_fixture_case(self)
        payload = asdict(self)
        payload["fixture_hash"] = zero_dte_adversarial_fixture_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEAdversarialFixtureCase":
        case = cls(
            case_id=_string_value(data, "case_id"),
            case_family=_string_value(data, "case_family"),
            adversarial_theme=_string_value(data, "adversarial_theme"),
            underlying=_string_value(data, "underlying"),
            option_type=_string_value(data, "option_type"),
            candidate_type=_string_value(data, "candidate_type"),
            baseline_expected_decision=_string_value(data, "baseline_expected_decision"),
            adversarial_expected_outcome=_string_value(data, "adversarial_expected_outcome"),
            primary_risk_vector=_string_value(data, "primary_risk_vector"),
            secondary_risk_vectors=_string_list_value(data, "secondary_risk_vectors"),
            proof_stress_type=_string_value(data, "proof_stress_type"),
            liquidity_stress_type=_string_value(data, "liquidity_stress_type"),
            greeks_stress_type=_string_value(data, "greeks_stress_type"),
            iv_stress_type=_string_value(data, "iv_stress_type"),
            event_stress_type=_string_value(data, "event_stress_type"),
            regime_stress_type=_string_value(data, "regime_stress_type"),
            expected_threshold_feedback=_string_list_value(data, "expected_threshold_feedback"),
            expected_optimizer_effect=_string_value(data, "expected_optimizer_effect"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            fixture_hash=_string_or_empty(data, "fixture_hash"),
        )
        validate_adversarial_fixture_case(case)
        return case


def validate_adversarial_fixture_case(case: ZeroDTEAdversarialFixtureCase) -> None:
    if case.case_family not in ADVERSARIAL_CASE_FAMILIES:
        raise ValueError(f"unsupported adversarial case family: {case.case_family}")
    if case.primary_risk_vector not in ADVERSARIAL_RISK_VECTORS:
        raise ValueError(f"unsupported primary risk vector: {case.primary_risk_vector}")
    unknown_secondary = [risk for risk in case.secondary_risk_vectors if risk not in ADVERSARIAL_RISK_VECTORS]
    if unknown_secondary:
        raise ValueError(f"unsupported secondary risk vectors: {unknown_secondary}")
    if case.option_type not in {"call", "put"}:
        raise ValueError(f"unsupported option type: {case.option_type}")
    if case.paper_only is not True or case.live_blocked is not True:
        raise ValueError("adversarial fixtures must be paper_only=true and live_blocked=true")
    encoded = json.dumps(asdict(case), sort_keys=True, ensure_ascii=False).lower()
    if any(token in encoded for token in FORBIDDEN_LIVE_MARKET_TOKENS):
        raise ValueError(f"adversarial fixture contains forbidden live market reference: {case.case_id}")


def zero_dte_adversarial_fixture_hash(case: ZeroDTEAdversarialFixtureCase) -> str:
    payload = asdict(case)
    payload["fixture_hash"] = ""
    return stable_adversarial_hash(payload)


def stable_adversarial_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_value(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty str")
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


def _string_list_value(data: dict[str, Any], key: str) -> list[str]:
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be list[str]")
    return list(value)
