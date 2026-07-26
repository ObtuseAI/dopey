"""Deterministic sector / peer / fundamental context summarization for DOPEY.

Pure math over SectorContext, PeerRelativeContext, FundamentalFixture, ValuationContext, and
EarningsQualityContext. Produces a FundamentalRiskSummary that highlights confirmation vs.
contradiction, valuation traps, and crowding risk. No real market data is used.
"""
from __future__ import annotations

from .fundamental_fixture_models import (
    EarningsQualityContext,
    FundamentalFixture,
    FundamentalRiskSummary,
    FUNDAMENTAL_FIXTURE_VERSION,
    PeerRelativeContext,
    SectorContext,
    ValuationContext,
    clamp,
)


def build_valuation_context(
    fundamental: FundamentalFixture,
    sector: SectorContext,
    *,
    override_valuation_regime: str | None = None,
) -> ValuationContext:
    """Build a deterministic ValuationContext from a fundamental + sector."""
    stretch = clamp(fundamental.valuation_stretch_proxy)
    sector_pe = clamp(sector.sector_relative_strength_score)
    growth = clamp(fundamental.revenue_growth_proxy)
    earnings = clamp(fundamental.earnings_quality_proxy)
    rel_valuation = clamp(0.55 * stretch + 0.25 * sector_pe + 0.20 * (1.0 - growth))
    compression_risk = clamp(0.40 * stretch + 0.30 * (1.0 - earnings) + 0.30 * (1.0 - sector.sector_momentum_score))
    expansion_support = clamp(0.40 * (1.0 - stretch) + 0.30 * growth + 0.30 * earnings)
    growth_adjusted = clamp(0.60 * (1.0 - stretch) + 0.25 * growth + 0.15 * earnings)
    trap = clamp(0.45 * stretch + 0.25 * (1.0 - fundamental.cash_flow_quality_proxy) + 0.15 * fundamental.balance_sheet_risk_proxy + 0.15 * (1.0 - fundamental.revision_momentum_proxy))
    regime = override_valuation_regime or _valuation_regime(stretch, trap, growth_adjusted)
    return ValuationContext(
        valuation_regime=regime,
        relative_valuation_score=round(rel_valuation, 6),
        valuation_stretch_score=round(stretch, 6),
        multiple_compression_risk=round(compression_risk, 6),
        multiple_expansion_support=round(expansion_support, 6),
        growth_adjusted_value_score=round(growth_adjusted, 6),
        valuation_trap_score=round(trap, 6),
    )


def _valuation_regime(stretch: float, trap: float, growth_adjusted: float) -> str:
    if trap >= 0.72 and stretch >= 0.65:
        return "valuation_trap"
    if stretch >= 0.75:
        return "extreme_stretch"
    if stretch <= 0.30 and growth_adjusted >= 0.60:
        return "value_support"
    if growth_adjusted >= 0.55:
        return "growth_justified"
    if stretch <= 0.45:
        return "reasonable"
    return "neutral"


def build_earnings_quality_context(
    fundamental: FundamentalFixture,
) -> EarningsQualityContext:
    """Derive EarningsQualityContext from the fundamental fixture."""
    return EarningsQualityContext(
        earnings_quality_score=round(clamp(fundamental.earnings_quality_proxy), 6),
        earnings_consistency_score=round(clamp(fundamental.earnings_quality_proxy * 0.7 + fundamental.cash_flow_quality_proxy * 0.3), 6),
        margin_quality_score=round(clamp(fundamental.margin_quality_proxy), 6),
        cash_flow_quality_score=round(clamp(fundamental.cash_flow_quality_proxy), 6),
        revenue_growth_score=round(clamp(fundamental.revenue_growth_proxy), 6),
        revision_momentum_score=round(clamp(fundamental.revision_momentum_proxy), 6),
        event_catalyst_quality_score=round(clamp(fundamental.event_catalyst_quality_proxy), 6),
        balance_sheet_risk_score=round(clamp(fundamental.balance_sheet_risk_proxy), 6),
        short_interest_pressure_score=round(clamp(fundamental.short_interest_pressure_proxy), 6),
        fragility_score=round(clamp(fundamental.fundamental_fragility_score), 6),
    )


def build_fundamental_risk_summary(
    sector: SectorContext,
    peer: PeerRelativeContext,
    fundamental: FundamentalFixture,
    valuation: ValuationContext,
    earnings: EarningsQualityContext,
) -> FundamentalRiskSummary:
    """Produce a deterministic FundamentalRiskSummary from the contexts."""
    sector_confirmation = clamp(
        0.40 * sector.sector_momentum_score
        + 0.20 * sector.sector_relative_strength_score
        + 0.20 * (1.0 - sector.sector_dispersion_score)
        + 0.20 * (1.0 - sector.sector_volatility_score)
    )
    peer_confirmation = clamp(0.55 * peer.peer_confirmation_score + 0.25 * peer.peer_leadership_score + 0.20 * (1.0 - peer.peer_contradiction_score))
    fundamental_confirmation = clamp(
        0.30 * fundamental.fundamental_trend_score
        + 0.20 * earnings.earnings_quality_score
        + 0.15 * earnings.revenue_growth_score
        + 0.10 * earnings.revision_momentum_score
        + 0.10 * earnings.cash_flow_quality_score
        + 0.15 * (1.0 - fundamental.balance_sheet_risk_proxy)
    )
    fundamental_contradiction = clamp(
        0.30 * peer.peer_contradiction_score
        + 0.25 * valuation.valuation_trap_score
        + 0.20 * fundamental.fundamental_fragility_score
        + 0.15 * peer.crowding_proxy_score
        + 0.10 * (1.0 - fundamental.revision_momentum_proxy)
    )
    quality = clamp(
        0.30 * earnings.earnings_quality_score
        + 0.20 * earnings.margin_quality_score
        + 0.20 * earnings.cash_flow_quality_score
        + 0.15 * earnings.revenue_growth_score
        + 0.15 * (1.0 - fundamental.balance_sheet_risk_proxy)
    )
    fragility = clamp(
        0.30 * fundamental.fundamental_fragility_score
        + 0.20 * fundamental.balance_sheet_risk_proxy
        + 0.20 * (1.0 - earnings.cash_flow_quality_score)
        + 0.15 * (1.0 - earnings.earnings_consistency_score)
        + 0.15 * fundamental.short_interest_pressure_proxy
    )
    valuation_risk = clamp(
        0.50 * valuation.valuation_trap_score
        + 0.30 * valuation.valuation_stretch_score
        + 0.20 * (1.0 - valuation.growth_adjusted_value_score)
    )
    event_quality = clamp(
        0.50 * fundamental.event_catalyst_quality_proxy
        + 0.30 * earnings.revision_momentum_score
        + 0.20 * earnings.earnings_quality_score
    )
    crowding = clamp(0.50 * peer.crowding_proxy_score + 0.30 * fundamental.short_interest_pressure_proxy + 0.20 * (1.0 - earnings.margin_quality_score))

    flags: list[str] = []
    if fundamental_contradiction >= 0.65:
        flags.append("fundamental_contradiction")
    if valuation.valuation_trap_score >= 0.70:
        flags.append("valuation_trap")
    if peer.peer_contradiction_score >= 0.70:
        flags.append("peer_contradiction")
    if fundamental.fundamental_fragility_score >= 0.65:
        flags.append("fundamental_fragility")
    if peer.crowding_proxy_score >= 0.70:
        flags.append("crowding_danger")
    if fundamental_confirmation >= 0.70 and peer_confirmation >= 0.65:
        flags.append("fundamental_confirmation")
    if sector_confirmation >= 0.70 and peer_confirmation >= 0.65:
        flags.append("sector_peer_confirmed")
    if valuation.valuation_stretch_score >= 0.70 and fundamental.fundamental_trend_score < 0.45:
        flags.append("valuation_stretch_without_growth")

    verdict = _verdict(fundamental_confirmation, fundamental_contradiction, valuation, fragility, peer, crowding, sector_confirmation)

    return FundamentalRiskSummary(
        fundamental_confirmation_score=round(fundamental_confirmation, 6),
        fundamental_contradiction_score=round(fundamental_contradiction, 6),
        quality_score=round(quality, 6),
        fragility_score=round(fragility, 6),
        valuation_risk_score=round(valuation_risk, 6),
        peer_confirmation_score=round(peer_confirmation, 6),
        sector_confirmation_score=round(sector_confirmation, 6),
        event_quality_score=round(event_quality, 6),
        crowding_risk_score=round(crowding, 6),
        risk_flags=sorted(set(flags)),
        verdict=verdict,
    )


def _verdict(
    confirmation: float,
    contradiction: float,
    valuation: ValuationContext,
    fragility: float,
    peer: PeerRelativeContext,
    crowding: float,
    sector_confirmation: float,
) -> str:
    if valuation.valuation_trap_score >= 0.78 and confirmation < 0.45:
        return "valuation_trap"
    if fragility >= 0.72 and peer.peer_contradiction_score >= 0.55:
        return "fundamental_fragility"
    if crowding >= 0.78 and peer.peer_contradiction_score >= 0.50:
        return "crowding_danger"
    if peer.peer_contradiction_score >= 0.72 and confirmation < 0.45:
        return "peer_contradiction"
    if confirmation >= 0.72 and sector_confirmation >= 0.65:
        return "strong_fundamental_confirmation"
    if confirmation >= 0.62 and sector_confirmation >= 0.60:
        return "sector_peer_confirmed"
    if valuation.growth_adjusted_value_score >= 0.60 and valuation.valuation_trap_score < 0.40:
        return "valuation_supported"
    if contradiction >= 0.55:
        return "fundamental_neutral"
    return "fundamental_neutral"
