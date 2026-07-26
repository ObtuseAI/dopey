"""Coverage scoring for the deterministic 0DTE adversarial corpus."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .zero_dte_adversarial_fixture_models import (
    ADVERSARIAL_CASE_FAMILIES,
    ADVERSARIAL_RISK_VECTORS,
    ZeroDTEAdversarialFixtureCase,
)


def score_zero_dte_adversarial_coverage(cases: list[ZeroDTEAdversarialFixtureCase]) -> dict[str, Any]:
    family_counts = Counter(case.case_family for case in cases)
    primary_risk_counts = Counter(case.primary_risk_vector for case in cases)
    option_counts = Counter(case.option_type for case in cases)
    candidate_counts = Counter(case.candidate_type for case in cases)
    special_close_count = family_counts.get("special_close_stress", 0)
    expiry_count = family_counts.get("expiry_management_stress", 0)
    loophole_count = family_counts.get("policy_loophole_adversarial", 0)
    missing_families = sorted(ADVERSARIAL_CASE_FAMILIES - set(family_counts))
    missing_risks = sorted(ADVERSARIAL_RISK_VECTORS - set(primary_risk_counts))
    family_score = _fraction(len(ADVERSARIAL_CASE_FAMILIES) - len(missing_families), len(ADVERSARIAL_CASE_FAMILIES))
    risk_score = _fraction(len(ADVERSARIAL_RISK_VECTORS) - len(missing_risks), len(ADVERSARIAL_RISK_VECTORS))
    option_score = _fraction(len({kind for kind in {"call", "put"} if option_counts.get(kind, 0) > 0}), 2)
    candidate_score = _fraction(len({kind for kind in {"approved", "blocked", "throttled", "later_expiry"} if candidate_counts.get(kind, 0) > 0}), 4)
    policy_loophole_score = min(1.0, loophole_count / 6.0)
    special_close_score = min(1.0, special_close_count / 10.0)
    expiry_management_score = min(1.0, expiry_count / 8.0)
    optimizer_profile_score = 1.0 if any("gamma_theta_profile" in case.expected_optimizer_effect for case in cases) else 0.75
    overfit_pressure_score = round(min(1.0, (
        primary_risk_counts.get("gamma_reversal", 0)
        + primary_risk_counts.get("theta_bleed", 0)
        + primary_risk_counts.get("iv_overpayment", 0)
        + family_counts.get("blocked_maybe_overstrict", 0)
    ) / 24.0), 6)
    completeness = round(sum([
        family_score,
        risk_score,
        option_score,
        candidate_score,
        policy_loophole_score,
        special_close_score,
        expiry_management_score,
        optimizer_profile_score,
    ]) / 8.0, 6)
    undercovered = []
    if missing_families:
        undercovered.extend(missing_families)
    if missing_risks:
        undercovered.extend(missing_risks)
    if special_close_count < 10:
        undercovered.append("special_close_stress_depth")
    if expiry_count < 8:
        undercovered.append("expiry_management_depth")
    recommendations = [
        "add cross-underlying regime families",
        "add paired call/put reversals around macro shocks",
        "add more overstrict blocked replay variants before research-default promotion",
    ]
    return {
        "artifact_type": "zero_dte_adversarial_coverage_summary",
        "coverage_completeness_score": completeness,
        "case_family_coverage_score": family_score,
        "risk_vector_coverage_score": risk_score,
        "option_type_coverage_score": option_score,
        "bullish_bearish_coverage_score": option_score,
        "approval_block_throttle_coverage_score": candidate_score,
        "special_close_coverage_score": special_close_score,
        "expiry_management_coverage_score": expiry_management_score,
        "policy_loophole_coverage_score": policy_loophole_score,
        "optimizer_profile_coverage_score": optimizer_profile_score,
        "overfit_pressure_score": overfit_pressure_score,
        "case_family_distribution": dict(sorted(family_counts.items())),
        "risk_vector_distribution": dict(sorted(primary_risk_counts.items())),
        "option_type_distribution": dict(sorted(option_counts.items())),
        "candidate_type_distribution": dict(sorted(candidate_counts.items())),
        "missing_coverage_areas": undercovered,
        "highest_risk_undercovered_areas": undercovered[:5],
        "recommended_next_fixture_additions": recommendations,
        "paper_only": True,
        "live_blocked": True,
    }


def _fraction(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
