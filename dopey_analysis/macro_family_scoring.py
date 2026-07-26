"""Family-specific deterministic macro-event scoring for DOPEY paper replay.

Scores how well each strategy family fits a deterministic macro-event scenario. The math is
fixture-only; no real macro feeds are used.
"""
from __future__ import annotations

from .macro_event_fixture import (
    FamilyMacroEventScore,
    MacroEventScenario,
    clamp,
)


MACRO_FAMILY_SCORING_VERSION = "dopey-macro-family-scoring-v1"


def _breadth_sector_confirmation(scenario: MacroEventScenario) -> float:
    regime = scenario.regime_context
    return clamp(
        0.40 * regime.breadth_score
        + 0.30 * (1.0 - abs(regime.risk_on_score - regime.risk_off_score))
        + 0.20 * (1.0 - regime.macro_fakeout_risk_score)
        + 0.10 * (1.0 - regime.sector_rotation_score * 0.5),
    )


def _liquidity_macro_score(scenario: MacroEventScenario) -> float:
    regime = scenario.regime_context
    return regime.liquidity_regime_score


def score_family_macro_event(strategy_family: str, scenario: MacroEventScenario) -> FamilyMacroEventScore:
    """Score a strategy family against a deterministic macro-event scenario."""
    risk = scenario.risk_summary
    regime = scenario.regime_context
    event = scenario.macro_event

    flags: list[str] = []

    if strategy_family == "directional_convexity":
        base = (
            0.28 * risk.directional_confirmation_score
            + 0.22 * _breadth_sector_confirmation(scenario)
            + 0.18 * (1.0 - risk.event_gap_risk_score)
            + 0.16 * regime.macro_trend_score
            + 0.16 * (1.0 - risk.macro_contradiction_score)
        )
        penalty = risk.directional_fakeout_score * 0.35 + risk.macro_contradiction_score * 0.25
        if risk.directional_fakeout_score >= 0.70:
            flags.append("macro_fakeout_against_directional")
            penalty += 0.12
        if scenario.regime_tag == "gap_reversal" and event.overnight_futures_pressure >= 0.70:
            flags.append("overnight_gap_against_directional")
            penalty += 0.10
        if risk.vol_expansion_support_score >= 0.70 and risk.directional_confirmation_score < 0.50:
            flags.append("volatility_shock_without_directional_clarity")
            penalty += 0.12
        if _breadth_sector_confirmation(scenario) < 0.40:
            flags.append("breadth_contradiction_against_directional")
            penalty += 0.10
        if scenario.risk_summary.directional_fakeout_score >= 0.70:
            flags.append("macro_fakeout_against_directional")
            penalty += 0.10

    elif strategy_family == "volatility_expansion":
        base = (
            0.30 * risk.vol_expansion_support_score
            + 0.24 * (regime.vix_stress_score + regime.vvix_stress_score) / 2.0
            + 0.18 * risk.macro_shock_score
            + 0.16 * event.overnight_futures_pressure
            + 0.12 * regime.rate_shock_score
        )
        penalty = 0.0
        if scenario.scenario_id == "post_fomc_iv_crush":
            flags.append("post_event_crush_against_vol_expansion")
            penalty += 0.28
        if event.event_intensity < 0.35 and risk.vol_expansion_support_score < 0.45:
            flags.append("low_event_intensity_premium_overpayment")
            penalty += 0.14
        if risk.vol_expansion_support_score < 0.40:
            flags.append("declining_vol_regime")
            penalty += 0.16
        if scenario.regime_tag == "post_event_iv_crush":
            flags.append("post_event_crush_against_vol_expansion")
            penalty += 0.22

    elif strategy_family == "volatility_compression":
        base = (
            0.30 * (1.0 - risk.vol_expansion_support_score)
            + 0.22 * (1.0 - risk.macro_shock_score)
            + 0.18 * (1.0 - regime.vix_stress_score)
            + 0.16 * (1.0 - risk.event_gap_risk_score)
            + 0.14 * regime.liquidity_regime_score
        )
        penalty = risk.compression_danger_score * 0.40
        if scenario.scenario_id == "hot_cpi_rate_shock":
            flags.append("rate_shock_against_compression")
            penalty += 0.22
        if regime.vix_stress_score >= 0.75:
            flags.append("vix_spike_against_compression")
            penalty += 0.20
        if risk.macro_shock_score >= 0.70:
            flags.append("macro_shock_against_compression")
            penalty += 0.18
        if risk.event_gap_risk_score >= 0.70:
            flags.append("event_gap_risk_against_compression")
            penalty += 0.10
        if regime.breadth_score < 0.30:
            flags.append("breadth_breakdown_against_compression")
            penalty += 0.10

    else:  # short_duration_defined_risk
        base = (
            0.28 * risk.directional_confirmation_score
            + 0.24 * regime.liquidity_regime_score
            + 0.20 * (1.0 - risk.event_gap_risk_score)
            + 0.16 * (1.0 - (regime.vix_stress_score + regime.vvix_stress_score) / 2.0)
            + 0.12 * (1.0 - risk.macro_contradiction_score)
        )
        penalty = risk.short_duration_liquidity_risk_score * 0.30
        if risk.event_gap_risk_score >= 0.65:
            flags.append("event_gap_against_short_duration")
            penalty += 0.18
        if regime.liquidity_regime_score < 0.35:
            flags.append("liquidity_contraction_bad_fill_failure")
            penalty += 0.18
        if event.overnight_futures_pressure >= 0.65:
            flags.append("overnight_gap_slippage_failure")
            penalty += 0.14
        if risk.directional_fakeout_score >= 0.65:
            flags.append("macro_fakeout_against_short_duration")
            penalty += 0.10
        if (regime.vix_stress_score + regime.vvix_stress_score) / 2.0 >= 0.70:
            flags.append("vix_spike_against_short_duration")
            penalty += 0.10

    macro_fit = clamp(base - min(penalty, base * 0.90), 0.0, 1.0)
    opportunity = clamp(risk.vol_expansion_support_score if strategy_family == "volatility_expansion" else base, 0.0, 1.0)
    macro_risk = clamp(
        0.30 * risk.macro_shock_score
        + 0.20 * risk.macro_contradiction_score
        + 0.20 * risk.event_gap_risk_score
        + 0.15 * risk.directional_fakeout_score
        + 0.15 * (1.0 - regime.liquidity_regime_score),
    )

    if strategy_family in scenario.preferred_strategy_families:
        macro_fit = clamp(macro_fit + 0.06, 0.0, 1.0)
        opportunity = clamp(opportunity + 0.05, 0.0, 1.0)
    if strategy_family in scenario.penalized_strategy_families:
        macro_fit = clamp(macro_fit - 0.10, 0.0, 1.0)
        macro_risk = clamp(macro_risk + 0.08, 0.0, 1.0)
        penalty += 0.10

    verdict = "macro_neutral"
    if macro_fit >= 0.70:
        verdict = "macro_favored"
    elif macro_fit <= 0.35 or macro_risk >= 0.78:
        verdict = "macro_reject"
    elif macro_risk >= 0.60:
        verdict = "macro_danger"
    elif macro_fit >= 0.55:
        verdict = "macro_ok"

    return FamilyMacroEventScore(
        strategy_family=strategy_family,
        scenario_id=scenario.scenario_id,
        regime_tag=scenario.regime_tag,
        macro_fit_score=round(macro_fit, 6),
        macro_opportunity_score=round(opportunity, 6),
        macro_risk_score=round(macro_risk, 6),
        event_risk_score=round(risk.macro_shock_score, 6),
        rate_shock_score=round(regime.rate_shock_score, 6),
        vix_vvix_stress_score=round((regime.vix_stress_score + regime.vvix_stress_score) / 2.0, 6),
        breadth_sector_confirmation_score=round(_breadth_sector_confirmation(scenario), 6),
        liquidity_regime_macro_score=round(_liquidity_macro_score(scenario), 6),
        macro_contradiction_penalty=round(risk.macro_contradiction_score, 6),
        event_gap_risk_penalty=round(risk.event_gap_risk_score, 6),
        risk_flags=sorted(set(flags + scenario.risk_summary.risk_flags)),
        verdict=verdict,
    )


def score_all_families_for_scenario(scenario: MacroEventScenario) -> dict[str, FamilyMacroEventScore]:
    families = [
        "directional_convexity",
        "volatility_expansion",
        "volatility_compression",
        "short_duration_defined_risk",
    ]
    return {family: score_family_macro_event(family, scenario) for family in families}


def score_family_for_regime(strategy_family: str, regime_tag: str) -> FamilyMacroEventScore:
    from .macro_event_scenarios import scenario_for_regime

    return score_family_macro_event(strategy_family, scenario_for_regime(regime_tag))
