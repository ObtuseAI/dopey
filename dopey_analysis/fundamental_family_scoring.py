"""Family-specific deterministic sector/peer/fundamental scoring for DOPEY paper replay.

Scores how well each strategy family fits a deterministic sector/peer/fundamental scenario.
All math is fixture-only; no real sector/peer/fundamental data is used.
"""
from __future__ import annotations

from .fundamental_fixture_models import (
    FamilyFundamentalScore,
    FUNDAMENTAL_FIXTURE_VERSION,
    SectorPeerFundamentalScenario,
    clamp,
)


FUNDAMENTAL_FAMILY_SCORING_VERSION = "dopey-fundamental-family-scoring-v1"


def _sector_fit(scenario: SectorPeerFundamentalScenario) -> float:
    sector = scenario.sector_context
    return clamp(
        0.40 * sector.sector_momentum_score
        + 0.20 * sector.sector_relative_strength_score
        + 0.20 * (1.0 - sector.sector_dispersion_score)
        + 0.20 * (1.0 - sector.sector_volatility_score)
    )


def _peer_confirmation(scenario: SectorPeerFundamentalScenario) -> float:
    peer = scenario.peer_context
    return clamp(0.55 * peer.peer_confirmation_score + 0.25 * peer.peer_leadership_score + 0.20 * (1.0 - peer.peer_contradiction_score))


def _fundamental_confirmation(scenario: SectorPeerFundamentalScenario) -> float:
    return clamp(scenario.risk_summary.fundamental_confirmation_score)


def _earnings_quality(scenario: SectorPeerFundamentalScenario) -> float:
    eq = scenario.earnings_quality_context
    return clamp(0.40 * eq.earnings_quality_score + 0.20 * eq.cash_flow_quality_score + 0.20 * eq.margin_quality_score + 0.20 * eq.revenue_growth_score)


def _crowding_risk(scenario: SectorPeerFundamentalScenario) -> float:
    return clamp(scenario.risk_summary.crowding_risk_score)


def _valuation_risk(scenario: SectorPeerFundamentalScenario) -> float:
    return clamp(scenario.risk_summary.valuation_risk_score)


def _fundamental_contradiction(scenario: SectorPeerFundamentalScenario) -> float:
    return clamp(scenario.risk_summary.fundamental_contradiction_score)


def _fragility(scenario: SectorPeerFundamentalScenario) -> float:
    return clamp(scenario.risk_summary.fragility_score)


def score_family_fundamental(strategy_family: str, scenario: SectorPeerFundamentalScenario) -> FamilyFundamentalScore:
    """Score a strategy family against a deterministic sector/peer/fundamental scenario."""
    risk = scenario.risk_summary
    sector_fit = _sector_fit(scenario)
    peer_conf = _peer_confirmation(scenario)
    fund_conf = _fundamental_confirmation(scenario)
    val_risk = _valuation_risk(scenario)
    earn_q = _earnings_quality(scenario)
    crowd = _crowding_risk(scenario)
    contradiction = _fundamental_contradiction(scenario)
    fragility = _fragility(scenario)

    flags: list[str] = []

    if strategy_family == "directional_convexity":
        base = (
            0.30 * sector_fit
            + 0.22 * peer_conf
            + 0.20 * fund_conf
            + 0.16 * (1.0 - val_risk)
            + 0.12 * earn_q
        )
        penalty = 0.30 * contradiction + 0.30 * crowd + 0.20 * (1.0 - peer_conf) + 0.20 * val_risk
        if risk.verdict == "valuation_trap":
            flags.append("valuation_trap_against_directional")
            penalty += 0.18
        if risk.verdict == "peer_contradiction":
            flags.append("peer_contradiction_against_directional")
            penalty += 0.16
        if risk.verdict == "crowding_danger":
            flags.append("crowding_danger_against_directional")
            penalty += 0.14
        if risk.verdict == "fundamental_fragility":
            flags.append("fundamental_fragility_against_directional")
            penalty += 0.14
        if sector_fit < 0.40:
            flags.append("weak_sector_leadership")
            penalty += 0.10

    elif strategy_family == "volatility_expansion":
        base = (
            0.28 * scenario.peer_context.peer_dispersion_score
            + 0.20 * (1.0 - earn_q)
            + 0.16 * scenario.fundamental_fixture.balance_sheet_risk_proxy
            + 0.14 * (1.0 - scenario.fundamental_fixture.revision_momentum_proxy)
            + 0.12 * crowd
            + 0.10 * scenario.fundamental_fixture.event_catalyst_quality_proxy
        )
        penalty = 0.30 * (1.0 - scenario.peer_context.peer_dispersion_score) + 0.25 * earn_q + 0.20 * (1.0 - crowd)
        if risk.verdict == "post_earnings_quality_confirmed" or scenario.earnings_quality_context.earnings_quality_score >= 0.65 and scenario.peer_context.peer_dispersion_score < 0.30:
            flags.append("post_event_clarity_against_vol_expansion")
            penalty += 0.18
        if scenario.peer_context.peer_dispersion_score < 0.30:
            flags.append("low_dispersion_against_vol_expansion")
            penalty += 0.18
        if scenario.fundamental_fixture.event_catalyst_quality_proxy < 0.40:
            flags.append("low_catalyst_quality_against_vol_expansion")
            penalty += 0.12
        if scenario.fundamental_fixture.revision_momentum_proxy >= 0.65 and earn_q >= 0.65:
            flags.append("high_quality_clarity_against_vol_expansion")
            penalty += 0.10

    elif strategy_family == "volatility_compression":
        base = (
            0.28 * (1.0 - scenario.peer_context.peer_dispersion_score)
            + 0.20 * earn_q
            + 0.16 * (1.0 - scenario.fundamental_fixture.balance_sheet_risk_proxy)
            + 0.14 * scenario.fundamental_fixture.fundamental_trend_score
            + 0.12 * (1.0 - scenario.sector_context.sector_volatility_score)
            + 0.10 * (1.0 - val_risk)
        )
        penalty = 0.30 * scenario.peer_context.peer_dispersion_score + 0.25 * (1.0 - earn_q) + 0.20 * scenario.fundamental_fixture.balance_sheet_risk_proxy
        if scenario.peer_context.peer_dispersion_score >= 0.70:
            flags.append("high_dispersion_against_compression")
            penalty += 0.18
        if scenario.fundamental_fixture.revision_momentum_proxy < 0.30:
            flags.append("revision_shock_against_compression")
            penalty += 0.16
        if crowd >= 0.65:
            flags.append("crowding_unwind_against_compression")
            penalty += 0.14
        if scenario.sector_context.sector_volatility_score >= 0.65:
            flags.append("sector_volatility_against_compression")
            penalty += 0.10
        if risk.verdict == "valuation_trap":
            flags.append("valuation_trap_against_compression")
            penalty += 0.10

    else:  # short_duration_defined_risk
        base = (
            0.26 * sector_fit
            + 0.22 * (1.0 - contradiction)
            + 0.18 * (1.0 - scenario.sector_context.sector_volatility_score)
            + 0.16 * earn_q
            + 0.18 * (1.0 - crowd)
        )
        penalty = 0.30 * crowd + 0.25 * contradiction + 0.20 * scenario.sector_context.sector_volatility_score + 0.15 * fragility
        if crowd >= 0.70:
            flags.append("crowded_fakeout_against_short_duration")
            penalty += 0.18
        if scenario.sector_context.liquidity_context in {"thin", "moderate"} and scenario.peer_context.peer_dispersion_score >= 0.65:
            flags.append("small_cap_liquidity_decay_against_short_duration")
            penalty += 0.16
        if scenario.sector_context.sector_rotation_score >= 0.75 and scenario.sector_context.liquidity_context in {"thin", "moderate"}:
            flags.append("sector_rotation_late_day_liquidity_fade")
            penalty += 0.14
        if scenario.peer_context.peer_dispersion_score >= 0.70:
            flags.append("high_dispersion_bad_fill_against_short_duration")
            penalty += 0.12
        if fragility >= 0.55:
            flags.append("fundamental_fragility_against_short_duration")
            penalty += 0.10

    fundamental_fit = clamp(base - min(penalty, base * 0.95), 0.0, 1.0)
    family_fundamental_fit = fundamental_fit

    if strategy_family in scenario.preferred_strategy_families:
        fundamental_fit = clamp(fundamental_fit + 0.06, 0.0, 1.0)
    if strategy_family in scenario.penalized_strategy_families:
        fundamental_fit = clamp(fundamental_fit - 0.10, 0.0, 1.0)
        penalty += 0.10

    verdict = "fundamental_neutral"
    if fundamental_fit >= 0.70:
        verdict = "fundamental_favored"
    elif fundamental_fit <= 0.30 or contradiction >= 0.75:
        verdict = "fundamental_reject"
    elif contradiction >= 0.60:
        verdict = "fundamental_danger"
    elif fundamental_fit >= 0.55:
        verdict = "fundamental_ok"

    return FamilyFundamentalScore(
        strategy_family=strategy_family,
        scenario_id=scenario.scenario_id,
        regime_tag=scenario.regime_tag,
        fundamental_fit_score=round(fundamental_fit, 6),
        sector_fit_score=round(sector_fit, 6),
        peer_confirmation_score=round(peer_conf, 6),
        fundamental_confirmation_score=round(fund_conf, 6),
        valuation_risk_score=round(val_risk, 6),
        earnings_quality_score=round(earn_q, 6),
        crowding_risk_score=round(crowd, 6),
        fundamental_contradiction_penalty=round(contradiction, 6),
        fragility_penalty=round(fragility, 6),
        family_fundamental_fit_score=round(family_fundamental_fit, 6),
        risk_flags=sorted(set(flags + risk.risk_flags)),
        verdict=verdict,
    )


def score_all_families_for_scenario(scenario: SectorPeerFundamentalScenario) -> dict[str, FamilyFundamentalScore]:
    families = [
        "directional_convexity",
        "volatility_expansion",
        "volatility_compression",
        "short_duration_defined_risk",
    ]
    return {family: score_family_fundamental(family, scenario) for family in families}
