"""Negative-control evaluation that blocks unexplained apparent edge."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .gates import GateDecision


@dataclass(frozen=True, slots=True)
class NegativeControlResult:
    control_id: str
    evaluator_id: str
    evidence_id: str
    observed_absolute_effect: float
    maximum_expected_absolute_effect: float
    completed: bool
    explanation_evidence_id: str | None


def evaluate_negative_controls(
    results: tuple[NegativeControlResult, ...],
    required_control_ids: frozenset[str],
    candidate_author_id: str,
) -> GateDecision:
    if not required_control_ids:
        raise ValueError("certification requires at least one declared negative control")
    if not candidate_author_id:
        raise ValueError("candidate author identity cannot be empty")
    reasons: list[str] = []
    by_id = {result.control_id: result for result in results}
    missing = sorted(required_control_ids.difference(by_id))
    reasons.extend(f"missing_negative_control:{control_id}" for control_id in missing)
    if len(by_id) != len(results):
        reasons.append("duplicate_negative_control_id")
    for result in results:
        if not result.control_id or not result.evaluator_id:
            reasons.append("negative_control_identity_incomplete")
        if not result.completed:
            reasons.append(f"negative_control_incomplete:{result.control_id}")
        if result.evaluator_id == candidate_author_id:
            reasons.append(f"negative_control_not_independent:{result.control_id}")
        if not result.evidence_id:
            reasons.append(f"negative_control_missing_evidence:{result.control_id}")
        if not math.isfinite(result.observed_absolute_effect) or result.observed_absolute_effect < 0.0:
            reasons.append(f"negative_control_effect_invalid:{result.control_id}")
        if not math.isfinite(result.maximum_expected_absolute_effect) or result.maximum_expected_absolute_effect < 0.0:
            raise ValueError(
                "negative-control tolerance must be finite and nonnegative: "
                f"control_id={result.control_id}"
            )
        anomaly = result.observed_absolute_effect > result.maximum_expected_absolute_effect
        if anomaly:
            reasons.append(f"negative_control_anomaly:{result.control_id}")
            if not result.explanation_evidence_id:
                reasons.append(f"unexplained_negative_control_anomaly:{result.control_id}")
    return GateDecision(
        passed=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
        automatic_effect="promotion_review_allowed" if not reasons else "certification_blocked",
    )
