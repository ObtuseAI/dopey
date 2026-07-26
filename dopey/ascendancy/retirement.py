"""Automatic quarantine and retirement decisions for degrading paper candidates."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from .identity import JsonValue, canonical_hash, parse_utc, require_sha256, require_utc_iso


ENVIRONMENT_ID = "dopey-options-paper-v1"
RETIREMENT_EVALUATOR_ID = "ascendancy-retirement-evaluator-v1"
RETIREMENT_EVALUATOR_VERSION = "ascendancy-stage-proof-v1"
RETIREMENT_STATE_MAX_AGE_SECONDS = 3600.0
RETIREMENT_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "environment_id",
        "proof_type",
        "evidence_id",
        "candidate_id",
        "candidate_author_id",
        "frozen_specification_hash",
        "experiment_id",
        "evaluator_id",
        "evaluator_version",
        "evaluated_at",
        "valid_until",
        "monitoring_state",
        "retirement_policy",
        "retirement_state",
        "reason_codes",
        "passed",
        "paper_only",
        "live_blocked",
    }
)
MONITORING_STATE_FIELDS = frozenset(
    {
        "calibration_error",
        "execution_degradation",
        "drawdown_fraction",
        "specification_deviations",
        "unsettled_fraction",
        "protected_manifest_valid",
        "expected_edge_exceeds_costs",
        "liquidity_policy_valid",
    }
)
RETIREMENT_POLICY_FIELDS = frozenset(
    {
        "maximum_calibration_error",
        "maximum_execution_degradation",
        "maximum_drawdown_fraction",
        "maximum_specification_deviations",
        "maximum_unsettled_fraction",
    }
)


@dataclass(frozen=True, slots=True)
class RetirementPolicy:
    maximum_calibration_error: float
    maximum_execution_degradation: float
    maximum_drawdown_fraction: float
    maximum_specification_deviations: int
    maximum_unsettled_fraction: float


@dataclass(frozen=True, slots=True)
class CandidateMonitoringState:
    calibration_error: float
    execution_degradation: float
    drawdown_fraction: float
    specification_deviations: int
    unsettled_fraction: float
    protected_manifest_valid: bool
    expected_edge_exceeds_costs: bool
    liquidity_policy_valid: bool


@dataclass(frozen=True, slots=True)
class RetirementDecision:
    state: Literal["CONTINUE_PAPER", "QUARANTINED", "RETIRED"]
    reason_codes: tuple[str, ...]
    live_blocked: bool


def v1_retirement_policy() -> RetirementPolicy:
    return RetirementPolicy(0.10, 0.25, 0.10, 0, 0.05)


def _finite_nonnegative_number(value: object, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(
            f"retirement artifact requires a finite nonnegative number: field={field_name}"
        )
    return float(value)


def _nonnegative_integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(
            f"retirement artifact requires a nonnegative integer: field={field_name}"
        )
    return value


def _monitoring_state_from_mapping(value: object) -> CandidateMonitoringState:
    if not isinstance(value, Mapping) or set(value) != MONITORING_STATE_FIELDS:
        raise ValueError("retirement monitoring state differs from the exact v1 schema")
    for field_name in (
        "protected_manifest_valid",
        "expected_edge_exceeds_costs",
        "liquidity_policy_valid",
    ):
        if not isinstance(value[field_name], bool):
            raise ValueError(
                f"retirement monitoring state requires a boolean: field={field_name}"
            )
    return CandidateMonitoringState(
        _finite_nonnegative_number(value["calibration_error"], "calibration_error"),
        _finite_nonnegative_number(
            value["execution_degradation"],
            "execution_degradation",
        ),
        _finite_nonnegative_number(value["drawdown_fraction"], "drawdown_fraction"),
        _nonnegative_integer(
            value["specification_deviations"],
            "specification_deviations",
        ),
        _finite_nonnegative_number(value["unsettled_fraction"], "unsettled_fraction"),
        value["protected_manifest_valid"],
        value["expected_edge_exceeds_costs"],
        value["liquidity_policy_valid"],
    )


def _retirement_policy_from_mapping(value: object) -> RetirementPolicy:
    if not isinstance(value, Mapping) or set(value) != RETIREMENT_POLICY_FIELDS:
        raise ValueError("retirement policy differs from the exact v1 schema")
    return RetirementPolicy(
        _finite_nonnegative_number(
            value["maximum_calibration_error"],
            "maximum_calibration_error",
        ),
        _finite_nonnegative_number(
            value["maximum_execution_degradation"],
            "maximum_execution_degradation",
        ),
        _finite_nonnegative_number(
            value["maximum_drawdown_fraction"],
            "maximum_drawdown_fraction",
        ),
        _nonnegative_integer(
            value["maximum_specification_deviations"],
            "maximum_specification_deviations",
        ),
        _finite_nonnegative_number(
            value["maximum_unsettled_fraction"],
            "maximum_unsettled_fraction",
        ),
    )


def validate_canonical_retirement_artifact(
    artifact: Mapping[str, JsonValue],
    candidate_id: str,
    candidate_author_id: str,
    frozen_specification_hash: str,
    evidence_id: str,
    evaluated_at: str,
) -> RetirementDecision:
    if set(artifact) != RETIREMENT_ARTIFACT_FIELDS:
        raise ValueError("retirement artifact differs from the exact v1 schema")
    require_sha256(frozen_specification_hash, "frozen_specification_hash")
    require_utc_iso(evaluated_at)
    expected_identity: dict[str, JsonValue] = {
        "artifact_type": "candidate_retirement_state",
        "schema_version": "dopey-candidate-retirement-state-v1",
        "environment_id": ENVIRONMENT_ID,
        "proof_type": "retirement_state",
        "evidence_id": evidence_id,
        "candidate_id": candidate_id,
        "candidate_author_id": candidate_author_id,
        "frozen_specification_hash": frozen_specification_hash,
        "evaluator_id": RETIREMENT_EVALUATOR_ID,
        "evaluator_version": RETIREMENT_EVALUATOR_VERSION,
        "evaluated_at": evaluated_at,
        "paper_only": True,
        "live_blocked": True,
    }
    if any(artifact.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("retirement artifact identity or authority is invalid")
    experiment_id = artifact.get("experiment_id")
    valid_until = artifact.get("valid_until")
    if not isinstance(experiment_id, str) or not experiment_id:
        raise ValueError("retirement artifact requires an experiment identity")
    if not isinstance(valid_until, str):
        raise ValueError("retirement artifact requires a validity deadline")
    require_utc_iso(valid_until)
    expected_valid_until = (
        parse_utc(evaluated_at) + timedelta(seconds=RETIREMENT_STATE_MAX_AGE_SECONDS)
    ).isoformat().replace("+00:00", "Z")
    if valid_until != expected_valid_until:
        raise ValueError("retirement artifact validity is not derived from frozen v1 policy")
    monitoring_state = _monitoring_state_from_mapping(artifact.get("monitoring_state"))
    retirement_policy = _retirement_policy_from_mapping(artifact.get("retirement_policy"))
    if retirement_policy != v1_retirement_policy():
        raise ValueError("retirement artifact policy differs from frozen v1 policy")
    decision = evaluate_retirement(monitoring_state, retirement_policy)
    reason_codes = artifact.get("reason_codes")
    if (
        not isinstance(reason_codes, list)
        or any(not isinstance(reason, str) or not reason for reason in reason_codes)
        or reason_codes != sorted(set(reason_codes))
    ):
        raise ValueError("retirement artifact reason codes are invalid")
    expected_passed = decision.state == "CONTINUE_PAPER"
    if (
        artifact.get("retirement_state") != decision.state
        or reason_codes != list(decision.reason_codes)
        or artifact.get("passed") is not expected_passed
    ):
        raise ValueError("retirement artifact decision is not measurement-derived")
    return decision


def retirement_artifact_hash(artifact: Mapping[str, JsonValue]) -> str:
    return canonical_hash(dict(artifact))


def evaluate_retirement(
    state: CandidateMonitoringState,
    policy: RetirementPolicy,
) -> RetirementDecision:
    numeric_state = (
        state.calibration_error,
        state.execution_degradation,
        state.drawdown_fraction,
        state.unsettled_fraction,
    )
    numeric_policy = (
        policy.maximum_calibration_error,
        policy.maximum_execution_degradation,
        policy.maximum_drawdown_fraction,
        policy.maximum_unsettled_fraction,
    )
    if any(not math.isfinite(value) or value < 0.0 for value in (*numeric_state, *numeric_policy)):
        raise ValueError("retirement measurements and limits must be finite and nonnegative")
    if state.specification_deviations < 0 or policy.maximum_specification_deviations < 0:
        raise ValueError("retirement deviation counts cannot be negative")
    hard_reasons: list[str] = []
    if not state.protected_manifest_valid:
        hard_reasons.append("protected_manifest_invalid")
    if state.drawdown_fraction > policy.maximum_drawdown_fraction:
        hard_reasons.append("drawdown_outside_failure_envelope")
    if state.specification_deviations > policy.maximum_specification_deviations:
        hard_reasons.append("specification_divergence")
    if not state.expected_edge_exceeds_costs:
        hard_reasons.append("expected_edge_below_costs")
    if not state.liquidity_policy_valid:
        hard_reasons.append("liquidity_policy_broken")
    if hard_reasons:
        return RetirementDecision("RETIRED", tuple(sorted(hard_reasons)), True)
    quarantine_reasons: list[str] = []
    if state.calibration_error > policy.maximum_calibration_error:
        quarantine_reasons.append("calibration_degraded")
    if state.execution_degradation > policy.maximum_execution_degradation:
        quarantine_reasons.append("execution_quality_degraded")
    if state.unsettled_fraction > policy.maximum_unsettled_fraction:
        quarantine_reasons.append("settlement_completion_degraded")
    if quarantine_reasons:
        return RetirementDecision("QUARANTINED", tuple(sorted(quarantine_reasons)), True)
    return RetirementDecision("CONTINUE_PAPER", (), True)
