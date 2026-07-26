"""Protected cross-domain promotion gate for cognitive methods."""

from __future__ import annotations

from typing import Any, Final

from dopey.protocols.identity import canonical_hash

from .schema import CognitiveMethodEvidence, CognitiveMethodThresholds, CognitivePromotionState


COGNITIVE_METHOD_THRESHOLDS: Final[CognitiveMethodThresholds] = {
    "threshold_version": "dopey-cognitive-method-thresholds-v1",
    "min_visible_samples": 40,
    "min_private_samples": 40,
    "min_external_samples": 30,
    "min_real_task_samples": 20,
    "min_domains": 3,
    "min_replications": 5,
    "min_effect_size": 0.03,
    "min_transfer_score": 0.67,
    "min_efficiency_score": 0.55,
    "max_complexity_score": 0.35,
}


def _validate_evidence(evidence: CognitiveMethodEvidence) -> None:
    if not evidence["method_id"].strip():
        raise ValueError("cognitive method evidence requires method_id")
    count_fields = (
        "visible_samples",
        "private_samples",
        "external_samples",
        "real_task_samples",
        "domain_count",
        "replication_count",
    )
    for field in count_fields:
        if evidence[field] < 0:
            raise ValueError(
                f"cognitive method evidence count cannot be negative: field={field}, value={evidence[field]}"
            )
    for field in (
        "calibration_improvement",
        "transfer_score",
        "efficiency_score",
        "complexity_score",
    ):
        value = float(evidence[field])
        if not -1.0 <= value <= 1.0:
            raise ValueError(
                f"cognitive method evidence score must be within [-1, 1]: field={field}, value={value}"
            )


def _decision(
    evidence: CognitiveMethodEvidence,
    state: CognitivePromotionState,
    failures: list[str],
    activation_allowed: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "artifact_type": "protected_cognitive_method_evaluation",
        "evaluation_version": "dopey-cognitive-method-evaluator-v1",
        "method_id": evidence["method_id"],
        "promotion_state": state.value,
        "failed_thresholds": sorted(set(failures)),
        "threshold_version": COGNITIVE_METHOD_THRESHOLDS["threshold_version"],
        "automatic_cognitive_method_activation_allowed": activation_allowed,
        "human_review_required": False,
        "candidate_may_grade_itself": False,
        "candidate_may_modify_evaluator": False,
        "authority_effect": "none",
        "permission_effect": "none",
        "truth_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "evaluation_hash": canonical_hash(body)}


def evaluate_cognitive_method(evidence: CognitiveMethodEvidence) -> dict[str, Any]:
    _validate_evidence(evidence)
    unsafe: list[str] = []
    if evidence["reward_hacking_detected"]:
        unsafe.append("reward_hacking_detected")
    if evidence["constitutional_violation"]:
        unsafe.append("constitutional_violation")
    if not evidence["deterministic"]:
        unsafe.append("deterministic")
    if not evidence["evaluator_independent"]:
        unsafe.append("evaluator_independent")
    if unsafe:
        return _decision(evidence, CognitivePromotionState.QUARANTINED, unsafe, False)
    thresholds = COGNITIVE_METHOD_THRESHOLDS
    if evidence["visible_samples"] < thresholds["min_visible_samples"]:
        return _decision(evidence, CognitivePromotionState.EXPERIMENTAL, ["visible_samples"], False)
    if evidence["private_samples"] < thresholds["min_private_samples"]:
        return _decision(evidence, CognitivePromotionState.REPLAY_VALIDATED, ["private_samples"], False)
    if evidence["external_samples"] < thresholds["min_external_samples"]:
        return _decision(evidence, CognitivePromotionState.PRIVATE_VALIDATED, ["external_samples"], False)
    if evidence["real_task_samples"] < thresholds["min_real_task_samples"]:
        return _decision(evidence, CognitivePromotionState.EXTERNAL_VALIDATED, ["real_task_samples"], False)
    failures = [
        name
        for name, passed in (
            ("domain_count", evidence["domain_count"] >= thresholds["min_domains"]),
            ("replication_count", evidence["replication_count"] >= thresholds["min_replications"]),
            ("effect_size", evidence["effect_size"] >= thresholds["min_effect_size"]),
            ("effect_interval_lower", evidence["effect_interval_lower"] > 0.0),
            ("calibration_improvement", evidence["calibration_improvement"] >= 0.0),
            ("transfer_score", evidence["transfer_score"] >= thresholds["min_transfer_score"]),
            ("efficiency_score", evidence["efficiency_score"] >= thresholds["min_efficiency_score"]),
            ("complexity_score", evidence["complexity_score"] <= thresholds["max_complexity_score"]),
        )
        if not passed
    ]
    state = CognitivePromotionState.THEORY_CANDIDATE if not failures else CognitivePromotionState.REAL_TASK_VALIDATED
    return _decision(evidence, state, failures, not failures)
