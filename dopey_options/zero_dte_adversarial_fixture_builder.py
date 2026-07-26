"""Build deterministic offline 0DTE adversarial fixture cases."""
from __future__ import annotations

from collections import Counter

from .zero_dte_adversarial_fixture_models import (
    ADVERSARIAL_RISK_VECTORS,
    ZeroDTEAdversarialFixtureCase,
    zero_dte_adversarial_fixture_hash,
)


CASE_DISTRIBUTION: dict[str, int] = {
    "approved_candidate_stress": 16,
    "blocked_candidate_validation": 16,
    "blocked_maybe_overstrict": 12,
    "throttled_candidate_stress": 10,
    "later_expiry_alternative": 10,
    "special_close_stress": 10,
    "expiry_management_stress": 8,
    "gamma_theta_adversarial": 8,
    "liquidity_spread_adversarial": 1,
    "iv_event_adversarial": 1,
    "regime_reversal_adversarial": 1,
    "policy_loophole_adversarial": 6,
}


def build_zero_dte_adversarial_fixture_cases() -> list[ZeroDTEAdversarialFixtureCase]:
    cases: list[ZeroDTEAdversarialFixtureCase] = []
    risk_vectors = sorted(ADVERSARIAL_RISK_VECTORS)
    index = 0
    for family, count in CASE_DISTRIBUTION.items():
        for family_index in range(count):
            index += 1
            primary = _primary_risk_vector(family, family_index, risk_vectors)
            secondary = _secondary_risks(primary, family_index, risk_vectors)
            candidate_type = _candidate_type(family)
            expected_outcome = _expected_outcome(family, primary, family_index)
            expected_feedback = _expected_feedback(primary, family)
            draft = ZeroDTEAdversarialFixtureCase(
                case_id=f"adv-0dte-{index:03d}",
                case_family=family,
                adversarial_theme=_theme(family, primary, family_index),
                underlying=_underlying(index),
                option_type="call" if index % 2 else "put",
                candidate_type=candidate_type,
                baseline_expected_decision=_baseline_decision(candidate_type),
                adversarial_expected_outcome=expected_outcome,
                primary_risk_vector=primary,
                secondary_risk_vectors=secondary,
                proof_stress_type=_proof_stress(primary, family),
                liquidity_stress_type=_liquidity_stress(primary),
                greeks_stress_type=_greeks_stress(primary),
                iv_stress_type=_iv_stress(primary),
                event_stress_type=_event_stress(primary),
                regime_stress_type=_regime_stress(primary),
                expected_threshold_feedback=expected_feedback,
                expected_optimizer_effect=_optimizer_effect(family, primary, expected_outcome),
                paper_only=True,
                live_blocked=True,
                fixture_hash="",
            )
            cases.append(ZeroDTEAdversarialFixtureCase(
                **{**draft.__dict__, "fixture_hash": zero_dte_adversarial_fixture_hash(draft)}
            ))
    return cases


def case_family_distribution(cases: list[ZeroDTEAdversarialFixtureCase]) -> dict[str, int]:
    return dict(sorted(Counter(case.case_family for case in cases).items()))


def risk_vector_distribution(cases: list[ZeroDTEAdversarialFixtureCase]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for case in cases:
        counter[case.primary_risk_vector] += 1
        counter.update(case.secondary_risk_vectors)
    return dict(sorted(counter.items()))


def _primary_risk_vector(family: str, index: int, risk_vectors: list[str]) -> str:
    family_overrides = {
        "approved_candidate_stress": [
            "theta_bleed", "gamma_reversal", "spread_explosion", "iv_crush",
            "late_day_liquidity_collapse", "slippage_spike", "pin_risk", "missing_exit_plan",
            "missing_thesis", "false_breakdown", "liquidity_decay", "iv_overpayment",
            "macro_reversal", "false_breakout", "event_shock", "gamma_reversal",
        ],
        "blocked_candidate_validation": [
            "liquidity_decay", "spread_explosion", "slippage_spike", "gamma_reversal",
            "theta_bleed", "iv_overpayment", "event_shock", "missing_thesis",
            "missing_exit_plan", "unsupported_structure_attempt", "unsupported_structure_attempt",
            "live_path_attempt", "unsupported_structure_attempt", "missing_exit_plan",
            "liquidity_decay", "same_day_churn_attempt",
        ],
        "policy_loophole_adversarial": [
            "same_day_churn_attempt", "same_day_churn_attempt", "unsupported_structure_attempt",
            "unsupported_structure_attempt", "live_path_attempt", "live_path_attempt",
        ],
        "special_close_stress": [
            "liquidity_decay", "spread_explosion", "missing_exit_plan", "gamma_reversal",
            "iv_crush", "missing_thesis", "liquidity_decay", "pin_risk", "theta_bleed",
            "same_day_churn_attempt",
        ],
    }
    values = family_overrides.get(family)
    if values:
        return values[index]
    return risk_vectors[(index + len(family)) % len(risk_vectors)]


def _secondary_risks(primary: str, index: int, risk_vectors: list[str]) -> list[str]:
    secondary = risk_vectors[(index + 3) % len(risk_vectors)]
    tertiary = risk_vectors[(index + 7) % len(risk_vectors)]
    return [risk for risk in [secondary, tertiary] if risk != primary]


def _candidate_type(family: str) -> str:
    if family.startswith("approved") or family in {"special_close_stress", "expiry_management_stress"}:
        return "approved"
    if family.startswith("throttled"):
        return "throttled"
    if family == "later_expiry_alternative":
        return "later_expiry"
    return "blocked"


def _baseline_decision(candidate_type: str) -> str:
    return {
        "approved": "approved_for_paper_open",
        "throttled": "approved_with_throttle",
        "later_expiry": "prefer_non_zero_dte_alternative",
        "blocked": "blocked_for_paper_open",
    }[candidate_type]


def _expected_outcome(family: str, primary: str, index: int) -> str:
    if family == "policy_loophole_adversarial":
        return "rejected_policy_violation"
    if primary in {"same_day_churn_attempt", "unsupported_structure_attempt", "live_path_attempt"}:
        return "rejected_policy_violation"
    if family == "blocked_candidate_validation":
        return "blocked_correctly"
    if family == "blocked_maybe_overstrict":
        return "blocked_maybe_too_strict"
    if family == "throttled_candidate_stress":
        return "throttled_correctly" if index != 7 else "blocked_correctly"
    if family == "later_expiry_alternative":
        return "prefer_later_expiry_confirmed" if index != 9 else "prefer_later_expiry_missed_opportunity"
    if family == "special_close_stress":
        return "approved_special_close_helped" if index in {0, 1, 2, 3, 4, 8} else "rejected_policy_violation"
    if family == "expiry_management_stress":
        return "approved_expiry_managed_failure" if index in {0, 2, 4, 7} else "approved_expiry_managed_success"
    if primary in {"theta_bleed", "false_breakout", "false_breakdown"}:
        return "approved_decayed"
    if primary in {"gamma_reversal", "macro_reversal"}:
        return "approved_spiked_then_failed"
    if primary in {"spread_explosion", "iv_crush", "late_day_liquidity_collapse", "iv_overpayment"}:
        return "approved_should_have_been_throttled_more"
    return "approved_survived_fixture"


def _expected_feedback(primary: str, family: str) -> list[str]:
    feedback = {
        "liquidity_decay": ["tighten_liquidity_threshold"],
        "spread_explosion": ["tighten_spread_threshold"],
        "slippage_spike": ["tighten_spread_threshold"],
        "gamma_reversal": ["tighten_gamma_instability_threshold"],
        "theta_bleed": ["tighten_theta_decay_threshold"],
        "iv_crush": ["tighten_iv_overpayment_threshold"],
        "iv_overpayment": ["tighten_iv_overpayment_threshold"],
        "event_shock": ["increase_proof_score_requirement"],
        "macro_reversal": ["increase_proof_score_requirement"],
        "false_breakout": ["increase_proof_score_requirement"],
        "false_breakdown": ["increase_proof_score_requirement"],
        "pin_risk": ["prefer_later_expiry_more_often"],
        "late_day_liquidity_collapse": ["tighten_liquidity_threshold"],
        "missing_thesis": ["increase_proof_score_requirement"],
        "missing_exit_plan": ["increase_proof_score_requirement"],
        "same_day_churn_attempt": ["keep_block_reason_validated"],
        "unsupported_structure_attempt": ["keep_block_reason_validated"],
        "live_path_attempt": ["keep_block_reason_validated"],
    }[primary]
    if family in {"blocked_maybe_overstrict", "gamma_theta_adversarial"}:
        feedback.append("mark_inconclusive_needs_more_fixture_coverage")
    return feedback


def _optimizer_effect(family: str, primary: str, outcome: str) -> str:
    if outcome == "rejected_policy_violation":
        return "preserve_rejection_gate"
    if family == "blocked_maybe_overstrict":
        return "needs_more_fixture_coverage"
    if primary in {"gamma_reversal", "theta_bleed"}:
        return "increase_overfit_pressure_on_gamma_theta_profile"
    if primary in {"liquidity_decay", "spread_explosion", "slippage_spike"}:
        return "increase_liquidity_profile_pressure"
    if primary in {"iv_crush", "iv_overpayment"}:
        return "increase_iv_profile_pressure"
    return "retain_paper_shadow_only"


def _theme(family: str, primary: str, index: int) -> str:
    return f"{family}_{primary}_{index + 1:02d}"


def _underlying(index: int) -> str:
    return ["SPY_FIXTURE", "QQQ_FIXTURE", "IWM_FIXTURE", "DIA_FIXTURE"][index % 4]


def _proof_stress(primary: str, family: str) -> str:
    if primary in {"missing_thesis", "missing_exit_plan"}:
        return primary
    return "borderline_proof" if family in {"approved_candidate_stress", "blocked_maybe_overstrict"} else "validated_policy_proof"


def _liquidity_stress(primary: str) -> str:
    return "high" if primary in {"liquidity_decay", "spread_explosion", "slippage_spike", "late_day_liquidity_collapse"} else "normal"


def _greeks_stress(primary: str) -> str:
    return "high" if primary in {"gamma_reversal", "theta_bleed", "pin_risk"} else "normal"


def _iv_stress(primary: str) -> str:
    return "high" if primary in {"iv_crush", "iv_overpayment"} else "normal"


def _event_stress(primary: str) -> str:
    return "high" if primary in {"event_shock", "macro_reversal"} else "none"


def _regime_stress(primary: str) -> str:
    return "reversal" if primary in {"macro_reversal", "false_breakout", "false_breakdown"} else "stable_fixture"
