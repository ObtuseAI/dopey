"""Coverage scoring for cross-underlying 0DTE adversarial corpus v2."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .zero_dte_cross_underlying_fixture_models import CROSS_UNDERLYING_REGIME_FAMILIES, ZeroDTECrossUnderlyingRegimeCase
from .zero_dte_underlying_family_models import UNDERLYING_FAMILY_NAMES, ZeroDTEUnderlyingFamily


def score_zero_dte_cross_underlying_coverage(
    families: list[ZeroDTEUnderlyingFamily],
    cases: list[ZeroDTECrossUnderlyingRegimeCase],
) -> dict[str, Any]:
    family_names = {family.family_name for family in families}
    family_id_to_name = {family.underlying_family_id: family.family_name for family in families}
    family_counts = Counter(family_id_to_name[case.underlying_family_id] for case in cases)
    regime_counts = Counter(case.regime_family for case in cases)
    option_counts = Counter(case.option_type for case in cases)
    risk_counts = Counter(risk for case in cases for risk in case.risk_vectors)
    liquidity_counts = Counter(case.liquidity_profile for case in cases)
    spread_counts = Counter(case.spread_profile for case in cases)
    volatility_counts = Counter(case.iv_profile for case in cases)
    gamma_theta_counts = Counter(case.gamma_theta_profile for case in cases)
    event_macro_counts = Counter(f"{case.event_profile}:{case.macro_profile}" for case in cases)
    by_family = _cases_by_family(family_id_to_name, cases)
    policy_by_family = _family_presence(by_family, lambda case: case.expected_policy_result == "blocked_policy_loophole")
    special_by_family = _family_presence(by_family, lambda case: case.case_family == "special_close_stress")
    expiry_by_family = _family_presence(by_family, lambda case: case.case_family == "expiry_management_stress")
    later_by_family = _family_presence(by_family, lambda case: case.candidate_type == "later_expiry")
    per_family_scores = {
        family_name: _per_family_score(rows)
        for family_name, rows in sorted(by_family.items())
    }
    missing_families = sorted(UNDERLYING_FAMILY_NAMES - family_names)
    missing_regimes = sorted(CROSS_UNDERLYING_REGIME_FAMILIES - set(regime_counts))
    family_score = _fraction(len(UNDERLYING_FAMILY_NAMES) - len(missing_families), len(UNDERLYING_FAMILY_NAMES))
    regime_score = _fraction(len(CROSS_UNDERLYING_REGIME_FAMILIES) - len(missing_regimes), len(CROSS_UNDERLYING_REGIME_FAMILIES))
    call_put_balance = _call_put_balance(option_counts)
    per_family_minimum_score = min(per_family_scores.values()) if per_family_scores else 0.0
    completeness = round(sum([
        family_score,
        regime_score,
        call_put_balance,
        _fraction(len(liquidity_counts), 4),
        _fraction(len(spread_counts), 4),
        _fraction(len(volatility_counts), 4),
        _fraction(len(gamma_theta_counts), 4),
        _fraction(len(event_macro_counts), 6),
        per_family_minimum_score,
    ]) / 9.0, 6)
    high_risk = [
        f"{case.underlying_family_id}:{case.regime_family}:{case.risk_vectors[0]}"
        for case in cases
        if case.risk_vectors[0] in {"liquidity_decay", "spread_explosion", "gamma_reversal", "iv_crush", "macro_reversal", "pin_risk", "same_day_churn_attempt"}
    ][:12]
    return {
        "artifact_type": "zero_dte_cross_underlying_coverage_summary",
        "cross_underlying_completeness_score": completeness,
        "underlying_family_coverage_score": family_score,
        "regime_family_coverage_score": regime_score,
        "call_put_balance_score": call_put_balance,
        "liquidity_archetype_coverage": dict(sorted(liquidity_counts.items())),
        "spread_archetype_coverage": dict(sorted(spread_counts.items())),
        "volatility_archetype_coverage": dict(sorted(volatility_counts.items())),
        "gamma_theta_archetype_coverage": dict(sorted(gamma_theta_counts.items())),
        "event_macro_sensitivity_coverage": dict(sorted(event_macro_counts.items())),
        "underlying_family_distribution": dict(sorted(family_counts.items())),
        "regime_family_distribution": dict(sorted(regime_counts.items())),
        "option_type_distribution": dict(sorted(option_counts.items())),
        "risk_vector_distribution": dict(sorted(risk_counts.items())),
        "policy_loophole_coverage_by_family": policy_by_family,
        "special_close_coverage_by_family": special_by_family,
        "expiry_management_coverage_by_family": expiry_by_family,
        "later_expiry_coverage_by_family": later_by_family,
        "optimizer_profile_stress_coverage": {
            "stricter_gamma_theta_profile": sum(1 for case in cases if any(risk in {"gamma_reversal", "theta_bleed", "pin_risk"} for risk in case.risk_vectors)),
            "stricter_liquidity_profile": sum(1 for case in cases if any(risk in {"liquidity_decay", "spread_explosion", "slippage_spike"} for risk in case.risk_vectors)),
            "stricter_iv_overpayment_profile": sum(1 for case in cases if any(risk in {"iv_crush", "iv_overpayment", "event_shock"} for risk in case.risk_vectors)),
        },
        "per_family_coverage_score": per_family_scores,
        "per_regime_coverage_score": {regime: 1.0 for regime in sorted(regime_counts)},
        "undercovered_families": missing_families,
        "undercovered_regimes": missing_regimes,
        "highest_risk_family_regime_combinations": high_risk,
        "next_corpus_recommendations": [
            "add multi-day swing-to-0DTE hybrid replay cases",
            "add paired family-relative strength and weakness rotations",
            "add deeper cross-family overstrict blocked cases before stronger promotion",
        ],
        "paper_only": True,
        "live_blocked": True,
    }


def _cases_by_family(
    family_id_to_name: dict[str, str],
    cases: list[ZeroDTECrossUnderlyingRegimeCase],
) -> dict[str, list[ZeroDTECrossUnderlyingRegimeCase]]:
    by_family: dict[str, list[ZeroDTECrossUnderlyingRegimeCase]] = defaultdict(list)
    for case in cases:
        by_family[family_id_to_name[case.underlying_family_id]].append(case)
    return dict(by_family)


def _family_presence(
    by_family: dict[str, list[ZeroDTECrossUnderlyingRegimeCase]],
    predicate,
) -> dict[str, bool]:
    return {family_name: any(predicate(case) for case in rows) for family_name, rows in sorted(by_family.items())}


def _per_family_score(rows: list[ZeroDTECrossUnderlyingRegimeCase]) -> float:
    regimes = {case.regime_family for case in rows}
    options = {case.option_type for case in rows}
    required = [
        len(rows) >= 12,
        len(regimes) >= 8,
        options == {"call", "put"},
        any(case.expected_policy_result == "blocked_policy_loophole" for case in rows),
        any(case.case_family == "special_close_stress" for case in rows),
        any(case.case_family == "expiry_management_stress" for case in rows),
        any(case.candidate_type == "later_expiry" for case in rows),
    ]
    return round(sum(1 for item in required if item) / len(required), 6)


def _call_put_balance(option_counts: Counter[str]) -> float:
    calls = option_counts.get("call", 0)
    puts = option_counts.get("put", 0)
    total = calls + puts
    if total == 0:
        return 0.0
    return round(1.0 - abs(calls - puts) / total, 6)


def _fraction(numerator: int, denominator: int) -> float:
    return round(min(1.0, numerator / denominator), 6) if denominator else 0.0
