"""Deterministic offline 0DTE threshold optimizer records.

These records are fixture-only and advisory. They do not mutate default
thresholds, fetch market data, connect to brokers, or authorize live trading.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ZERO_DTE_THRESHOLD_OPTIMIZER_VERSION = "dopey-zero-dte-threshold-feedback-optimizer-v1"

ZERO_DTE_THRESHOLD_RISK_POSTURES: frozenset[str] = frozenset({
    "stricter",
    "balanced_research",
    "coverage_expansion_only",
    "rejected_too_loose",
    "rejected_overfit",
})

ZERO_DTE_THRESHOLD_PROMOTION_GATES: frozenset[str] = frozenset({
    "reject",
    "advisory_only",
    "paper_shadow_candidate",
    "research_default_candidate",
    "needs_more_fixture_coverage",
})

ZERO_DTE_OPTIMIZATION_DECISIONS: frozenset[str] = frozenset({
    "reject_candidate",
    "hold_advisory_only",
    "needs_more_fixture_coverage",
    "promote_to_paper_shadow_candidate",
    "promote_to_research_default_candidate",
    "retain_current_thresholds",
})


@dataclass(frozen=True)
class ZeroDTEThresholdFeedbackAggregate:
    aggregate_id: str
    source_replay_summary_hash: str
    feedback_records_loaded: int
    outcomes_loaded: int
    approved_count: int
    blocked_count: int
    throttled_count: int
    expiry_managed_count: int
    later_expiry_recommendation_count: int
    feedback_counts_by_type: dict[str, int]
    outcome_counts_by_type: dict[str, int]
    reason_code_counts: dict[str, int]
    validated_blocks: list[dict[str, Any]]
    possible_overstrict_blocks: list[dict[str, Any]]
    approved_failures: list[dict[str, Any]]
    approved_successes: list[dict[str, Any]]
    throttle_validations: list[dict[str, Any]]
    paper_only: bool
    live_blocked: bool
    aggregate_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["aggregate_hash"] = zero_dte_feedback_aggregate_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEThresholdFeedbackAggregate":
        return cls(
            aggregate_id=_string_value(data, "aggregate_id"),
            source_replay_summary_hash=_string_value(data, "source_replay_summary_hash"),
            feedback_records_loaded=_int_value(data, "feedback_records_loaded"),
            outcomes_loaded=_int_value(data, "outcomes_loaded"),
            approved_count=_int_value(data, "approved_count"),
            blocked_count=_int_value(data, "blocked_count"),
            throttled_count=_int_value(data, "throttled_count"),
            expiry_managed_count=_int_value(data, "expiry_managed_count"),
            later_expiry_recommendation_count=_int_value(data, "later_expiry_recommendation_count"),
            feedback_counts_by_type=_int_dict_value(data, "feedback_counts_by_type"),
            outcome_counts_by_type=_int_dict_value(data, "outcome_counts_by_type"),
            reason_code_counts=_int_dict_value(data, "reason_code_counts"),
            validated_blocks=_dict_list_value(data, "validated_blocks"),
            possible_overstrict_blocks=_dict_list_value(data, "possible_overstrict_blocks"),
            approved_failures=_dict_list_value(data, "approved_failures"),
            approved_successes=_dict_list_value(data, "approved_successes"),
            throttle_validations=_dict_list_value(data, "throttle_validations"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            aggregate_hash=_string_or_empty(data, "aggregate_hash"),
        )


@dataclass(frozen=True)
class ZeroDTEThresholdCandidate:
    candidate_threshold_id: str
    base_threshold_version: str
    candidate_version: str
    change_set: dict[str, Any]
    change_rationale: list[str]
    expected_effect: list[str]
    risk_posture: str
    controls_tightened: list[str]
    controls_loosened: list[str]
    controls_unchanged: list[str]
    requires_more_fixture_coverage: list[str]
    promotion_gate: str
    paper_only: bool
    live_blocked: bool
    candidate_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidate_hash"] = zero_dte_threshold_candidate_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEThresholdCandidate":
        risk_posture = _string_value(data, "risk_posture")
        if risk_posture not in ZERO_DTE_THRESHOLD_RISK_POSTURES:
            raise ValueError(f"unsupported 0DTE threshold risk_posture: {risk_posture}")
        promotion_gate = _string_value(data, "promotion_gate")
        if promotion_gate not in ZERO_DTE_THRESHOLD_PROMOTION_GATES:
            raise ValueError(f"unsupported 0DTE threshold promotion_gate: {promotion_gate}")
        return cls(
            candidate_threshold_id=_string_value(data, "candidate_threshold_id"),
            base_threshold_version=_string_value(data, "base_threshold_version"),
            candidate_version=_string_value(data, "candidate_version"),
            change_set=_dict_value(data, "change_set"),
            change_rationale=_string_list_value(data, "change_rationale"),
            expected_effect=_string_list_value(data, "expected_effect"),
            risk_posture=risk_posture,
            controls_tightened=_string_list_value(data, "controls_tightened"),
            controls_loosened=_string_list_value(data, "controls_loosened"),
            controls_unchanged=_string_list_value(data, "controls_unchanged"),
            requires_more_fixture_coverage=_string_list_value(data, "requires_more_fixture_coverage"),
            promotion_gate=promotion_gate,
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            candidate_hash=_string_or_empty(data, "candidate_hash"),
        )


@dataclass(frozen=True)
class ZeroDTEShadowReplayResult:
    shadow_replay_id: str
    candidate_threshold_id: str
    fixture_cases_replayed: int
    decisions_changed: int
    new_approvals: int
    new_blocks: int
    new_throttles: int
    validated_block_preserved_count: int
    unsafe_approval_count: int
    overfit_warning_count: int
    safety_error_count: int
    paper_only: bool
    live_blocked: bool
    shadow_replay_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shadow_replay_hash"] = zero_dte_shadow_replay_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEShadowReplayResult":
        return cls(
            shadow_replay_id=_string_value(data, "shadow_replay_id"),
            candidate_threshold_id=_string_value(data, "candidate_threshold_id"),
            fixture_cases_replayed=_int_value(data, "fixture_cases_replayed"),
            decisions_changed=_int_value(data, "decisions_changed"),
            new_approvals=_int_value(data, "new_approvals"),
            new_blocks=_int_value(data, "new_blocks"),
            new_throttles=_int_value(data, "new_throttles"),
            validated_block_preserved_count=_int_value(data, "validated_block_preserved_count"),
            unsafe_approval_count=_int_value(data, "unsafe_approval_count"),
            overfit_warning_count=_int_value(data, "overfit_warning_count"),
            safety_error_count=_int_value(data, "safety_error_count"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            shadow_replay_hash=_string_or_empty(data, "shadow_replay_hash"),
        )


@dataclass(frozen=True)
class ZeroDTEThresholdOptimizationDecision:
    optimizer_run_id: str
    candidate_threshold_id: str
    decision: str
    decision_reason_codes: list[str]
    safety_status: str
    overfit_status: str
    evidence_status: str
    recommended_next_action: str
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_hash"] = zero_dte_optimization_decision_hash(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTEThresholdOptimizationDecision":
        decision = _string_value(data, "decision")
        if decision not in ZERO_DTE_OPTIMIZATION_DECISIONS:
            raise ValueError(f"unsupported 0DTE threshold optimization decision: {decision}")
        return cls(
            optimizer_run_id=_string_value(data, "optimizer_run_id"),
            candidate_threshold_id=_string_value(data, "candidate_threshold_id"),
            decision=decision,
            decision_reason_codes=_string_list_value(data, "decision_reason_codes"),
            safety_status=_string_value(data, "safety_status"),
            overfit_status=_string_value(data, "overfit_status"),
            evidence_status=_string_value(data, "evidence_status"),
            recommended_next_action=_string_value(data, "recommended_next_action"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            decision_hash=_string_or_empty(data, "decision_hash"),
        )


def zero_dte_feedback_aggregate_hash(aggregate: ZeroDTEThresholdFeedbackAggregate) -> str:
    payload = asdict(aggregate)
    payload["aggregate_hash"] = ""
    return stable_zero_dte_optimizer_hash(payload)


def zero_dte_threshold_candidate_hash(candidate: ZeroDTEThresholdCandidate) -> str:
    payload = asdict(candidate)
    payload["candidate_hash"] = ""
    return stable_zero_dte_optimizer_hash(payload)


def zero_dte_shadow_replay_hash(result: ZeroDTEShadowReplayResult) -> str:
    payload = asdict(result)
    payload["shadow_replay_hash"] = ""
    return stable_zero_dte_optimizer_hash(payload)


def zero_dte_optimization_decision_hash(decision: ZeroDTEThresholdOptimizationDecision) -> str:
    payload = asdict(decision)
    payload["decision_hash"] = ""
    return stable_zero_dte_optimizer_hash(payload)


def stable_zero_dte_optimizer_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _dict_value(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be dict")
    return dict(value)


def _dict_list_value(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError(f"{key} must be list[dict]")
    return [dict(item) for item in value]


def _string_list_value(data: dict[str, Any], key: str) -> list[str]:
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be list[str]")
    return list(value)


def _int_dict_value(data: dict[str, Any], key: str) -> dict[str, int]:
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be dict[str, int]")
    output: dict[str, int] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str):
            raise TypeError(f"{key} keys must be str")
        if isinstance(item_value, bool) or not isinstance(item_value, int):
            raise TypeError(f"{key} values must be int")
        output[item_key] = item_value
    return output
