"""Build deterministic cross-underlying 0DTE v2 fixture cases."""
from __future__ import annotations

from collections import Counter

from .zero_dte_adversarial_fixture_models import ADVERSARIAL_RISK_VECTORS
from .zero_dte_cross_underlying_fixture_models import ZeroDTECrossUnderlyingRegimeCase, zero_dte_cross_underlying_case_hash
from .zero_dte_underlying_family_models import (
    SYNTHETIC_SYMBOLS_BY_FAMILY,
    ZeroDTEUnderlyingFamily,
    zero_dte_underlying_family_hash,
)


FAMILY_ORDER: tuple[str, ...] = (
    "index_like_etf",
    "megacap_liquid_equity",
    "high_beta_momentum_equity",
    "event_sensitive_equity",
    "low_liquidity_options_equity",
    "sector_rotation_equity",
    "gap_prone_equity",
    "mean_reversion_equity",
    "trend_persistence_equity",
    "volatility_crush_equity",
    "macro_sensitive_equity",
    "pin_risk_heavy_equity",
)

CASE_TEMPLATES: tuple[tuple[str, str, str, str, str], ...] = (
    ("bull_trend", "call", "approved", "approved_candidate_stress", "liquidity_decay"),
    ("bear_trend", "put", "approved", "approved_candidate_stress", "gamma_reversal"),
    ("chop_decay", "call", "approved", "gamma_theta_adversarial", "theta_bleed"),
    ("false_breakout", "put", "blocked", "blocked_maybe_overstrict", "false_breakout"),
    ("false_breakdown", "call", "blocked", "blocked_maybe_overstrict", "false_breakdown"),
    ("gap_and_go", "call", "approved", "regime_reversal_adversarial", "slippage_spike"),
    ("gap_and_fade", "put", "throttled", "throttled_candidate_stress", "spread_explosion"),
    ("iv_expansion", "call", "later_expiry", "later_expiry_alternative", "event_shock"),
    ("iv_crush", "put", "approved", "iv_event_adversarial", "iv_crush"),
    ("late_day_liquidity_decay", "call", "approved", "special_close_stress", "late_day_liquidity_collapse"),
    ("pin_near_strike", "put", "approved", "expiry_management_stress", "pin_risk"),
    ("macro_shock", "call", "blocked", "policy_loophole_adversarial", "same_day_churn_attempt"),
    ("event_whipsaw", "put", "blocked", "policy_loophole_adversarial", "live_path_attempt"),
    ("range_bound", "call", "blocked", "policy_loophole_adversarial", "unsupported_structure_attempt"),
    ("mean_reversion", "put", "approved", "regime_reversal_adversarial", "false_breakout"),
    ("trend_persistence", "put", "approved", "approved_candidate_stress", "theta_bleed"),
)


def build_zero_dte_underlying_families() -> list[ZeroDTEUnderlyingFamily]:
    families: list[ZeroDTEUnderlyingFamily] = []
    for index, family_name in enumerate(FAMILY_ORDER):
        archetypes = _family_archetypes(family_name)
        draft = ZeroDTEUnderlyingFamily(
            underlying_family_id=f"underlying-family-{index + 1:02d}",
            family_name=family_name,
            synthetic_underlying_symbol=SYNTHETIC_SYMBOLS_BY_FAMILY[family_name],
            option_liquidity_archetype=archetypes["liquidity"],
            spread_archetype=archetypes["spread"],
            volatility_archetype=archetypes["volatility"],
            gamma_theta_archetype=archetypes["gamma_theta"],
            event_sensitivity_archetype=archetypes["event"],
            macro_sensitivity_archetype=archetypes["macro"],
            regime_sensitivity_archetype=archetypes["regime"],
            typical_0dte_risk_vectors=_family_risks(family_name),
            paper_only=True,
            live_blocked=True,
            family_hash="",
        )
        families.append(ZeroDTEUnderlyingFamily(**{**draft.__dict__, "family_hash": zero_dte_underlying_family_hash(draft)}))
    return families


def build_zero_dte_cross_underlying_cases(
    families: list[ZeroDTEUnderlyingFamily],
) -> list[ZeroDTECrossUnderlyingRegimeCase]:
    cases: list[ZeroDTECrossUnderlyingRegimeCase] = []
    secondary_risk_vectors = sorted(ADVERSARIAL_RISK_VECTORS - {"same_day_churn_attempt", "unsupported_structure_attempt", "live_path_attempt"})
    case_index = 0
    for family in families:
        for template_index, (regime, option_type, candidate_type, case_family, base_risk) in enumerate(CASE_TEMPLATES):
            case_index += 1
            primary = _family_adjusted_risk(family.family_name, base_risk, template_index)
            secondary = secondary_risk_vectors[(template_index + len(family.family_name)) % len(secondary_risk_vectors)]
            risks = [primary] if secondary == primary else [primary, secondary]
            draft = ZeroDTECrossUnderlyingRegimeCase(
                case_id=f"cross-0dte-v2-{case_index:03d}",
                underlying_family_id=family.underlying_family_id,
                synthetic_underlying_symbol=family.synthetic_underlying_symbol,
                regime_family=regime,
                option_type=option_type,
                candidate_type=candidate_type,
                case_family=case_family,
                risk_vectors=risks,
                liquidity_profile=_liquidity_profile(family, primary),
                spread_profile=_spread_profile(family, primary),
                gamma_theta_profile=_gamma_theta_profile(family, primary),
                iv_profile=_iv_profile(family, primary),
                event_profile=_event_profile(family, regime, primary),
                macro_profile=_macro_profile(family, regime, primary),
                expected_risk_decision=_expected_risk_decision(candidate_type, primary),
                expected_replay_outcome=_expected_replay_outcome(candidate_type, case_family, primary, regime),
                expected_threshold_feedback=_expected_feedback(primary, case_family),
                expected_optimizer_effect=_expected_optimizer_effect(family.family_name, primary, case_family),
                expected_policy_result=_expected_policy_result(candidate_type, primary),
                paper_only=True,
                live_blocked=True,
                case_hash="",
            )
            cases.append(ZeroDTECrossUnderlyingRegimeCase(**{**draft.__dict__, "case_hash": zero_dte_cross_underlying_case_hash(draft)}))
    return cases


def cross_underlying_family_distribution(cases: list[ZeroDTECrossUnderlyingRegimeCase]) -> dict[str, int]:
    return dict(sorted(Counter(case.underlying_family_id for case in cases).items()))


def cross_underlying_regime_distribution(cases: list[ZeroDTECrossUnderlyingRegimeCase]) -> dict[str, int]:
    return dict(sorted(Counter(case.regime_family for case in cases).items()))


def _family_archetypes(family_name: str) -> dict[str, str]:
    table = {
        "index_like_etf": ("deep", "tight", "moderate", "balanced", "low", "medium", "broad_index"),
        "megacap_liquid_equity": ("deep", "tight", "single_name_moderate", "balanced", "medium", "medium", "large_cap"),
        "high_beta_momentum_equity": ("medium", "variable", "high_beta", "unstable", "medium", "high", "momentum"),
        "event_sensitive_equity": ("medium", "variable", "event_bimodal", "unstable", "high", "medium", "event"),
        "low_liquidity_options_equity": ("thin", "wide", "erratic", "unstable", "medium", "medium", "liquidity_fragile"),
        "sector_rotation_equity": ("medium", "normal", "sector_driven", "balanced", "medium", "high", "rotation"),
        "gap_prone_equity": ("medium", "wide_on_gap", "gap_prone", "unstable", "medium", "high", "gap"),
        "mean_reversion_equity": ("medium", "normal", "range_bound", "reversal", "low", "medium", "mean_reversion"),
        "trend_persistence_equity": ("deep", "normal", "trend", "stable", "low", "medium", "trend_persistence"),
        "volatility_crush_equity": ("medium", "variable", "iv_crush", "unstable", "high", "medium", "volatility_crush"),
        "macro_sensitive_equity": ("medium", "variable", "macro", "unstable", "medium", "high", "macro_sensitive"),
        "pin_risk_heavy_equity": ("medium", "wide_near_close", "pin_heavy", "pin_risk", "medium", "medium", "pin_risk"),
    }[family_name]
    return {
        "liquidity": table[0],
        "spread": table[1],
        "volatility": table[2],
        "gamma_theta": table[3],
        "event": table[4],
        "macro": table[5],
        "regime": table[6],
    }


def _family_risks(family_name: str) -> list[str]:
    risks = {
        "index_like_etf": ["pin_risk", "theta_bleed", "late_day_liquidity_collapse"],
        "megacap_liquid_equity": ["iv_overpayment", "gamma_reversal", "event_shock"],
        "high_beta_momentum_equity": ["gamma_reversal", "false_breakout", "slippage_spike"],
        "event_sensitive_equity": ["event_shock", "iv_crush", "spread_explosion"],
        "low_liquidity_options_equity": ["liquidity_decay", "spread_explosion", "slippage_spike"],
        "sector_rotation_equity": ["macro_reversal", "false_breakout", "iv_crush"],
        "gap_prone_equity": ["slippage_spike", "spread_explosion", "gamma_reversal"],
        "mean_reversion_equity": ["false_breakout", "false_breakdown", "pin_risk"],
        "trend_persistence_equity": ["theta_bleed", "spread_explosion", "gamma_reversal"],
        "volatility_crush_equity": ["iv_crush", "iv_overpayment", "theta_bleed"],
        "macro_sensitive_equity": ["macro_reversal", "event_shock", "liquidity_decay"],
        "pin_risk_heavy_equity": ["pin_risk", "theta_bleed", "spread_explosion"],
    }[family_name]
    return risks


def _family_adjusted_risk(family_name: str, base_risk: str, template_index: int) -> str:
    risks = _family_risks(family_name)
    if template_index in {1, 3, 8}:
        return risks[template_index % len(risks)]
    if family_name == "low_liquidity_options_equity" and template_index in {0, 6, 9}:
        return "liquidity_decay"
    if family_name == "volatility_crush_equity" and template_index in {0, 1, 2, 8}:
        return "iv_crush"
    if family_name == "pin_risk_heavy_equity" and template_index in {0, 1, 10}:
        return "pin_risk"
    return base_risk


def _expected_risk_decision(candidate_type: str, primary: str) -> str:
    if primary in {"same_day_churn_attempt", "unsupported_structure_attempt", "live_path_attempt"}:
        return "blocked_policy_violation"
    return {
        "approved": "approved_for_paper_open",
        "blocked": "blocked_for_paper_open",
        "throttled": "approved_with_throttle",
        "later_expiry": "prefer_non_zero_dte_alternative",
    }[candidate_type]


def _expected_replay_outcome(candidate_type: str, case_family: str, primary: str, regime: str) -> str:
    if primary in {"same_day_churn_attempt", "unsupported_structure_attempt", "live_path_attempt"}:
        return "rejected_policy_violation"
    if candidate_type == "later_expiry":
        return "prefer_later_expiry_confirmed"
    if case_family == "special_close_stress":
        return "approved_special_close_helped"
    if case_family == "expiry_management_stress":
        return "approved_expiry_managed_failure" if primary == "pin_risk" else "approved_expiry_managed_success"
    if candidate_type == "throttled":
        return "throttled_correctly"
    if candidate_type == "blocked":
        return "blocked_correctly" if regime == "macro_shock" else "blocked_maybe_too_strict"
    if primary in {"theta_bleed", "false_breakout", "false_breakdown", "iv_crush"}:
        return "approved_decayed"
    if primary in {"gamma_reversal", "macro_reversal"}:
        return "approved_spiked_then_failed"
    if primary in {"spread_explosion", "slippage_spike", "late_day_liquidity_collapse", "liquidity_decay"}:
        return "approved_should_have_been_throttled_more"
    return "approved_survived_fixture"


def _expected_feedback(primary: str, case_family: str) -> list[str]:
    mapping = {
        "liquidity_decay": "tighten_liquidity_threshold",
        "spread_explosion": "tighten_spread_threshold",
        "slippage_spike": "tighten_spread_threshold",
        "gamma_reversal": "tighten_gamma_instability_threshold",
        "theta_bleed": "tighten_theta_decay_threshold",
        "iv_crush": "tighten_iv_overpayment_threshold",
        "iv_overpayment": "tighten_iv_overpayment_threshold",
        "event_shock": "increase_proof_score_requirement",
        "macro_reversal": "increase_proof_score_requirement",
        "false_breakout": "increase_proof_score_requirement",
        "false_breakdown": "increase_proof_score_requirement",
        "pin_risk": "prefer_later_expiry_more_often",
        "late_day_liquidity_collapse": "tighten_liquidity_threshold",
        "missing_thesis": "increase_proof_score_requirement",
        "missing_exit_plan": "increase_proof_score_requirement",
        "same_day_churn_attempt": "keep_block_reason_validated",
        "unsupported_structure_attempt": "keep_block_reason_validated",
        "live_path_attempt": "keep_block_reason_validated",
    }
    output = [mapping[primary]]
    if case_family == "blocked_maybe_overstrict":
        output.append("mark_inconclusive_needs_more_fixture_coverage")
    return output


def _expected_optimizer_effect(family_name: str, primary: str, case_family: str) -> str:
    if primary in {"same_day_churn_attempt", "unsupported_structure_attempt", "live_path_attempt"}:
        return f"preserve_rejection_gate:{family_name}"
    if case_family == "blocked_maybe_overstrict":
        return f"needs_more_cross_underlying_fixture_coverage:{family_name}"
    if primary in {"gamma_reversal", "theta_bleed", "pin_risk"}:
        return f"cross_underlying_pressure_gamma_theta_profile:{family_name}"
    if primary in {"liquidity_decay", "spread_explosion", "slippage_spike", "late_day_liquidity_collapse"}:
        return f"cross_underlying_pressure_liquidity_profile:{family_name}"
    if primary in {"iv_crush", "iv_overpayment", "event_shock"}:
        return f"cross_underlying_pressure_iv_event_profile:{family_name}"
    return f"retain_paper_shadow_only:{family_name}"


def _expected_policy_result(candidate_type: str, primary: str) -> str:
    if primary in {"same_day_churn_attempt", "unsupported_structure_attempt", "live_path_attempt"}:
        return "blocked_policy_loophole"
    if candidate_type == "later_expiry":
        return "prefer_later_expiry"
    if candidate_type == "blocked":
        return "blocked_by_risk_model"
    return "paper_only_allowed_by_fixture_policy"


def _liquidity_profile(family: ZeroDTEUnderlyingFamily, primary: str) -> str:
    return "decaying" if primary in {"liquidity_decay", "late_day_liquidity_collapse"} else family.option_liquidity_archetype


def _spread_profile(family: ZeroDTEUnderlyingFamily, primary: str) -> str:
    return "exploding" if primary in {"spread_explosion", "slippage_spike"} else family.spread_archetype


def _gamma_theta_profile(family: ZeroDTEUnderlyingFamily, primary: str) -> str:
    return "unstable" if primary in {"gamma_reversal", "theta_bleed", "pin_risk"} else family.gamma_theta_archetype


def _iv_profile(family: ZeroDTEUnderlyingFamily, primary: str) -> str:
    return "crush_or_overpayment" if primary in {"iv_crush", "iv_overpayment"} else family.volatility_archetype


def _event_profile(family: ZeroDTEUnderlyingFamily, regime: str, primary: str) -> str:
    return "event_stressed" if regime == "event_whipsaw" or primary == "event_shock" else family.event_sensitivity_archetype


def _macro_profile(family: ZeroDTEUnderlyingFamily, regime: str, primary: str) -> str:
    return "macro_stressed" if regime == "macro_shock" or primary == "macro_reversal" else family.macro_sensitivity_archetype
