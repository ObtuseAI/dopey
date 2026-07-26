"""Cross-underlying deterministic 0DTE fixture case records."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .zero_dte_adversarial_fixture_models import ADVERSARIAL_CASE_FAMILIES, ADVERSARIAL_RISK_VECTORS, FORBIDDEN_LIVE_MARKET_TOKENS
from .zero_dte_underlying_family_models import SYNTHETIC_SYMBOLS_BY_FAMILY, stable_cross_underlying_hash


CROSS_UNDERLYING_REGIME_FAMILIES: frozenset[str] = frozenset({
    "bull_trend",
    "bear_trend",
    "chop_decay",
    "false_breakout",
    "false_breakdown",
    "gap_and_fade",
    "gap_and_go",
    "iv_expansion",
    "iv_crush",
    "macro_shock",
    "event_whipsaw",
    "late_day_liquidity_decay",
    "pin_near_strike",
    "mean_reversion",
    "trend_persistence",
    "range_bound",
})


@dataclass(frozen=True)
class ZeroDTECrossUnderlyingRegimeCase:
    case_id: str
    underlying_family_id: str
    synthetic_underlying_symbol: str
    regime_family: str
    option_type: str
    candidate_type: str
    case_family: str
    risk_vectors: list[str]
    liquidity_profile: str
    spread_profile: str
    gamma_theta_profile: str
    iv_profile: str
    event_profile: str
    macro_profile: str
    expected_risk_decision: str
    expected_replay_outcome: str
    expected_threshold_feedback: list[str]
    expected_optimizer_effect: str
    expected_policy_result: str
    paper_only: bool
    live_blocked: bool
    case_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_cross_underlying_case(self)
        payload = asdict(self)
        payload["case_hash"] = zero_dte_cross_underlying_case_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTECrossUnderlyingRegimeCase":
        case = cls(
            case_id=_string_value(data, "case_id"),
            underlying_family_id=_string_value(data, "underlying_family_id"),
            synthetic_underlying_symbol=_string_value(data, "synthetic_underlying_symbol"),
            regime_family=_string_value(data, "regime_family"),
            option_type=_string_value(data, "option_type"),
            candidate_type=_string_value(data, "candidate_type"),
            case_family=_string_value(data, "case_family"),
            risk_vectors=_string_list_value(data, "risk_vectors"),
            liquidity_profile=_string_value(data, "liquidity_profile"),
            spread_profile=_string_value(data, "spread_profile"),
            gamma_theta_profile=_string_value(data, "gamma_theta_profile"),
            iv_profile=_string_value(data, "iv_profile"),
            event_profile=_string_value(data, "event_profile"),
            macro_profile=_string_value(data, "macro_profile"),
            expected_risk_decision=_string_value(data, "expected_risk_decision"),
            expected_replay_outcome=_string_value(data, "expected_replay_outcome"),
            expected_threshold_feedback=_string_list_value(data, "expected_threshold_feedback"),
            expected_optimizer_effect=_string_value(data, "expected_optimizer_effect"),
            expected_policy_result=_string_value(data, "expected_policy_result"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            case_hash=_string_or_empty(data, "case_hash"),
        )
        validate_cross_underlying_case(case)
        return case


def validate_cross_underlying_case(case: ZeroDTECrossUnderlyingRegimeCase) -> None:
    if case.synthetic_underlying_symbol not in set(SYNTHETIC_SYMBOLS_BY_FAMILY.values()):
        raise ValueError(f"cross-underlying case must use synthetic fixture symbols only: {case.case_id}")
    if case.regime_family not in CROSS_UNDERLYING_REGIME_FAMILIES:
        raise ValueError(f"unsupported regime family: {case.regime_family}")
    if case.option_type not in {"call", "put"}:
        raise ValueError(f"unsupported option type: {case.option_type}")
    if case.case_family not in ADVERSARIAL_CASE_FAMILIES:
        raise ValueError(f"unsupported case family: {case.case_family}")
    if not case.expected_policy_result:
        raise ValueError("expected_policy_result must not be empty")
    if not case.expected_optimizer_effect:
        raise ValueError("expected_optimizer_effect must not be empty")
    unknown_risks = [risk for risk in case.risk_vectors if risk not in ADVERSARIAL_RISK_VECTORS]
    if unknown_risks:
        raise ValueError(f"unsupported risk vectors: {unknown_risks}")
    if case.paper_only is not True or case.live_blocked is not True:
        raise ValueError("cross-underlying cases must be paper_only=true and live_blocked=true")
    encoded = json.dumps(asdict(case), sort_keys=True, ensure_ascii=False).lower()
    if any(token in encoded for token in FORBIDDEN_LIVE_MARKET_TOKENS):
        raise ValueError(f"cross-underlying case contains forbidden live market reference: {case.case_id}")


def zero_dte_cross_underlying_case_hash(case: ZeroDTECrossUnderlyingRegimeCase) -> str:
    payload = asdict(case)
    payload["case_hash"] = ""
    return stable_cross_underlying_hash(payload)


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
