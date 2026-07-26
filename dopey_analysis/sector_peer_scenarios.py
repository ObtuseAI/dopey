"""Deterministic sector / peer / fundamental scenario fixtures for DOPEY paper replay.

Eighteen offline scenarios covering directional confirmation/traps, volatility expansion,
volatility compression, and short-duration / liquidity-trap cases. Every value is a
deterministic 0..1 fixture score. No real sector/peer/fundamental data is used.
"""
from __future__ import annotations

from .fundamental_fixture_models import (
    EarningsQualityContext,
    FUNDAMENTAL_FIXTURE_VERSION,
    FundamentalFixture,
    PeerRelativeContext,
    SectorContext,
    SectorPeerFundamentalScenario,
    ValuationContext,
)
from .sector_peer_context import (
    build_earnings_quality_context,
    build_fundamental_risk_summary,
    build_valuation_context,
)


SECTOR_PEER_SCENARIO_VERSION = "dopey-sector-peer-fundamental-scenarios-v1"


def _sector(
    sector_id: str,
    sector_name: str,
    regime: str,
    momentum: float,
    relative_strength: float,
    dispersion: float,
    volatility: float,
    rotation: float,
    def_cyc: str,
    growth_value: str,
    liquidity: str,
    notes: str,
) -> SectorContext:
    return SectorContext(
        sector_id=sector_id,
        sector_name=sector_name,
        sector_regime=regime,
        sector_momentum_score=momentum,
        sector_relative_strength_score=relative_strength,
        sector_dispersion_score=dispersion,
        sector_volatility_score=volatility,
        sector_rotation_score=rotation,
        defensive_cyclical_bias=def_cyc,
        growth_value_bias=growth_value,
        liquidity_context=liquidity,
        notes=notes,
    )


def _peer(
    peer_group_id: str,
    peer_count: int,
    relative_strength: float,
    dispersion: float,
    leadership: float,
    breakdown: float,
    confirmation: float,
    contradiction: float,
    crowding: float,
    notes: str,
) -> PeerRelativeContext:
    return PeerRelativeContext(
        peer_group_id=peer_group_id,
        peer_count=peer_count,
        peer_relative_strength_score=relative_strength,
        peer_dispersion_score=dispersion,
        peer_leadership_score=leadership,
        peer_breakdown_pressure=breakdown,
        peer_confirmation_score=confirmation,
        peer_contradiction_score=contradiction,
        crowding_proxy_score=crowding,
        notes=notes,
    )


def _fundamental(
    fundamental_id: str,
    symbol: str,
    sector_id: str,
    revenue: float,
    margin: float,
    earnings: float,
    balance_sheet_risk: float,
    cash_flow: float,
    valuation_stretch: float,
    revision_momentum: float,
    event_quality: float,
    short_interest: float,
    trend: float,
    fragility: float,
    notes: str,
) -> FundamentalFixture:
    return FundamentalFixture(
        fundamental_id=fundamental_id,
        symbol=symbol,
        sector_id=sector_id,
        revenue_growth_proxy=revenue,
        margin_quality_proxy=margin,
        earnings_quality_proxy=earnings,
        balance_sheet_risk_proxy=balance_sheet_risk,
        cash_flow_quality_proxy=cash_flow,
        valuation_stretch_proxy=valuation_stretch,
        revision_momentum_proxy=revision_momentum,
        event_catalyst_quality_proxy=event_quality,
        short_interest_pressure_proxy=short_interest,
        fundamental_trend_score=trend,
        fundamental_fragility_score=fragility,
        notes=notes,
    )


def _scenario(
    scenario_id: str,
    regime_tag: str,
    sector: SectorContext,
    peer: PeerRelativeContext,
    fundamental: FundamentalFixture,
    preferred: list[str],
    penalized: list[str],
    macro_effect: str,
    iv_effect: str,
    liquidity_effect: str,
    pattern_effect: str,
    failure_modes: list[str],
    notes: str,
) -> SectorPeerFundamentalScenario:
    valuation = build_valuation_context(fundamental, sector)
    earnings = build_earnings_quality_context(fundamental)
    risk = build_fundamental_risk_summary(sector, peer, fundamental, valuation, earnings)
    return SectorPeerFundamentalScenario(
        scenario_id=scenario_id,
        regime_tag=regime_tag,
        sector_context=sector,
        peer_context=peer,
        fundamental_fixture=fundamental,
        valuation_context=valuation,
        earnings_quality_context=earnings,
        risk_summary=risk,
        preferred_strategy_families=preferred,
        penalized_strategy_families=penalized,
        expected_macro_effect=macro_effect,
        expected_iv_effect=iv_effect,
        expected_liquidity_slippage_effect=liquidity_effect,
        expected_pattern_effect=pattern_effect,
        expected_failure_modes=failure_modes,
        notes=notes,
    )


def build_sector_peer_fundamental_scenarios() -> list[SectorPeerFundamentalScenario]:
    """Return 18 deterministic sector/peer/fundamental scenarios."""
    return [
        # 1
        _scenario(
            "tech_leadership_breakout_confirmed",
            "sector_leadership_breakout",
            _sector(
                "tech", "Information Technology", "leadership_breakout",
                momentum=0.85, relative_strength=0.88, dispersion=0.30, volatility=0.35, rotation=0.45,
                def_cyc="cyclical", growth_value="growth", liquidity="deep",
                notes="Tech sector leadership confirmed; deep liquidity, moderate dispersion.",
            ),
            _peer(
                "tech_megacap", 8, relative_strength=0.82, dispersion=0.30, leadership=0.85,
                breakdown=0.15, confirmation=0.82, contradiction=0.15, crowding=0.55,
                notes="Megacap tech leaders confirming; modest crowding but not extreme.",
            ),
            _fundamental(
                "tech_megacap_aapl", "AAPL", "tech",
                revenue=0.65, margin=0.78, earnings=0.80, balance_sheet_risk=0.10, cash_flow=0.85,
                valuation_stretch=0.55, revision_momentum=0.65, event_quality=0.60, short_interest=0.20,
                trend=0.78, fragility=0.18, notes="High quality growth with reasonable valuation.",
            ),
            preferred=["directional_convexity", "short_duration_defined_risk"],
            penalized=["volatility_compression"],
            macro_effect="macro_supportive",
            iv_effect="moderate_iv_with_call_skew",
            liquidity_effect="clean_fills_deep_liquidity",
            pattern_effect="leadership_breakout_pattern",
            failure_modes=["valuation_stretch_against_directional"],
            notes="Tech leadership is the canonical confirmed directional setup.",
        ),
        # 2
        _scenario(
            "semiconductor_peer_fakeout",
            "sector_peer_fakeout",
            _sector(
                "semis", "Semiconductors", "exhaustion_fakeout",
                momentum=0.55, relative_strength=0.60, dispersion=0.75, volatility=0.70, rotation=0.55,
                def_cyc="cyclical", growth_value="growth", liquidity="moderate",
                notes="Semis dispersion high; leadership exhausted.",
            ),
            _peer(
                "semis_group", 12, relative_strength=0.50, dispersion=0.78, leadership=0.45,
                breakdown=0.62, confirmation=0.32, contradiction=0.72, crowding=0.68,
                notes="Peer breakdown vs index; strong contradiction.",
            ),
            _fundamental(
                "semis_leader", "NVDA", "semis",
                revenue=0.75, margin=0.72, earnings=0.68, balance_sheet_risk=0.18, cash_flow=0.65,
                valuation_stretch=0.80, revision_momentum=0.30, event_quality=0.55, short_interest=0.30,
                trend=0.55, fragility=0.42, notes="Stretched valuation with weakening revisions.",
            ),
            preferred=["volatility_expansion"],
            penalized=["directional_convexity", "short_duration_defined_risk"],
            macro_effect="macro_contradiction",
            iv_effect="iv_lift_with_skew_steepening",
            liquidity_effect="wide_spreads_dispersion",
            pattern_effect="peer_fakeout_pattern",
            failure_modes=["peer_contradiction_against_directional", "valuation_trap_against_directional"],
            notes="Semiconductor peer fakeout; rewards vol expansion, penalizes directional.",
        ),
        # 3
        _scenario(
            "financials_rate_tailwind_breakout",
            "rate_tailwind_directional",
            _sector(
                "financials", "Financials", "rate_tailwind",
                momentum=0.75, relative_strength=0.72, dispersion=0.40, volatility=0.40, rotation=0.55,
                def_cyc="cyclical", growth_value="value", liquidity="deep",
                notes="Financials benefit from steeper curve.",
            ),
            _peer(
                "banks_group", 10, relative_strength=0.72, dispersion=0.38, leadership=0.70,
                breakdown=0.20, confirmation=0.78, contradiction=0.18, crowding=0.35,
                notes="Banks confirm; benign crowding.",
            ),
            _fundamental(
                "banks_jpm", "JPM", "financials",
                revenue=0.55, margin=0.70, earnings=0.72, balance_sheet_risk=0.30, cash_flow=0.70,
                valuation_stretch=0.40, revision_momentum=0.75, event_quality=0.55, short_interest=0.20,
                trend=0.72, fragility=0.25, notes="Improving revisions and reasonable valuation.",
            ),
            preferred=["directional_convexity", "short_duration_defined_risk"],
            penalized=["volatility_compression"],
            macro_effect="rate_tailwind_supportive",
            iv_effect="moderate_iv",
            liquidity_effect="clean_fills",
            pattern_effect="rate_tailwind_breakout",
            failure_modes=[],
            notes="Classic rate-tailwind directional setup.",
        ),
        # 4
        _scenario(
            "consumer_discretionary_peer_breakdown",
            "consumer_peer_breakdown",
            _sector(
                "consumer_disc", "Consumer Discretionary", "peer_breakdown",
                momentum=0.30, relative_strength=0.32, dispersion=0.70, volatility=0.55, rotation=0.65,
                def_cyc="cyclical", growth_value="blend", liquidity="moderate",
                notes="Consumer disc peers diverging; index vulnerable.",
            ),
            _peer(
                "consumer_disc_group", 9, relative_strength=0.30, dispersion=0.72, leadership=0.25,
                breakdown=0.78, confirmation=0.22, contradiction=0.78, crowding=0.55,
                notes="Strong peer breakdown pressure.",
            ),
            _fundamental(
                "consumer_disc_amzn", "AMZN", "consumer_disc",
                revenue=0.55, margin=0.45, earnings=0.50, balance_sheet_risk=0.32, cash_flow=0.55,
                valuation_stretch=0.55, revision_momentum=0.30, event_quality=0.45, short_interest=0.30,
                trend=0.40, fragility=0.50, notes="Weakening revisions, fragile thesis.",
            ),
            preferred=["volatility_expansion", "directional_convexity"],
            penalized=["volatility_compression", "short_duration_defined_risk"],
            macro_effect="macro_consumer_pressure",
            iv_effect="iv_lift_with_dispersion",
            liquidity_effect="widening_spreads",
            pattern_effect="peer_breakdown_pattern",
            failure_modes=["peer_contradiction_against_compression", "fundamental_fragility_against_short_duration"],
            notes="Consumer disc peer breakdown; bullish directional can survive if dispersion resolves bearishly.",
        ),
        # 5
        _scenario(
            "healthcare_defensive_rotation_confirmed",
            "defensive_rotation",
            _sector(
                "healthcare", "Health Care", "defensive_rotation",
                momentum=0.65, relative_strength=0.68, dispersion=0.30, volatility=0.30, rotation=0.45,
                def_cyc="defensive", growth_value="blend", liquidity="deep",
                notes="Healthcare defensive rotation confirmed.",
            ),
            _peer(
                "pharma_group", 7, relative_strength=0.65, dispersion=0.32, leadership=0.62,
                breakdown=0.18, confirmation=0.72, contradiction=0.18, crowding=0.30,
                notes="Pharma peers confirm rotation.",
            ),
            _fundamental(
                "pharma_jnj", "JNJ", "healthcare",
                revenue=0.45, margin=0.78, earnings=0.72, balance_sheet_risk=0.20, cash_flow=0.80,
                valuation_stretch=0.35, revision_momentum=0.55, event_quality=0.55, short_interest=0.10,
                trend=0.62, fragility=0.20, notes="Defensive quality, low valuation stretch.",
            ),
            preferred=["directional_convexity", "volatility_compression", "short_duration_defined_risk"],
            penalized=["volatility_expansion"],
            macro_effect="macro_defensive_supportive",
            iv_effect="iv_anchored_low",
            liquidity_effect="tight_spreads",
            pattern_effect="defensive_rotation_pattern",
            failure_modes=[],
            notes="Defensive rotation supports all but vol expansion families.",
        ),
        # 6
        _scenario(
            "earnings_quality_uncertainty_vol_expansion",
            "earnings_quality_vol_expansion",
            _sector(
                "blend", "Cross-Sector Blend", "earnings_uncertainty",
                momentum=0.50, relative_strength=0.50, dispersion=0.65, volatility=0.60, rotation=0.55,
                def_cyc="blend", growth_value="blend", liquidity="moderate",
                notes="Cross-sector earnings quality uncertainty.",
            ),
            _peer(
                "earnings_group", 10, relative_strength=0.45, dispersion=0.70, leadership=0.40,
                breakdown=0.55, confirmation=0.35, contradiction=0.62, crowding=0.50,
                notes="Peer leadership weak; dispersion high.",
            ),
            _fundamental(
                "earnings_uncertain", "MIXED", "blend",
                revenue=0.45, margin=0.50, earnings=0.42, balance_sheet_risk=0.40, cash_flow=0.50,
                valuation_stretch=0.55, revision_momentum=0.25, event_quality=0.35, short_interest=0.35,
                trend=0.45, fragility=0.55, notes="Earnings quality uncertain; weak revisions.",
            ),
            preferred=["volatility_expansion"],
            penalized=["volatility_compression", "directional_convexity"],
            macro_effect="macro_earnings_uncertainty",
            iv_effect="iv_lift_pre_earnings",
            liquidity_effect="wide_spreads_pre_earnings",
            pattern_effect="earnings_vol_expansion_pattern",
            failure_modes=["post_event_crush_against_vol_expansion", "low_dispersion_against_vol_expansion"],
            notes="Classic earnings-quality uncertainty vol expansion setup.",
        ),
        # 7
        _scenario(
            "high_peer_dispersion_event_vol",
            "high_dispersion_event_vol",
            _sector(
                "blend", "Cross-Sector Blend", "high_dispersion",
                momentum=0.45, relative_strength=0.50, dispersion=0.85, volatility=0.70, rotation=0.60,
                def_cyc="blend", growth_value="blend", liquidity="moderate",
                notes="Cross-sector dispersion high.",
            ),
            _peer(
                "high_dispersion_group", 12, relative_strength=0.40, dispersion=0.85, leadership=0.35,
                breakdown=0.70, confirmation=0.30, contradiction=0.72, crowding=0.60,
                notes="High dispersion; weak leadership.",
            ),
            _fundamental(
                "high_dispersion_xyz", "XYZ", "blend",
                revenue=0.50, margin=0.55, earnings=0.50, balance_sheet_risk=0.30, cash_flow=0.55,
                valuation_stretch=0.55, revision_momentum=0.50, event_quality=0.60, short_interest=0.40,
                trend=0.50, fragility=0.40, notes="Average quality; high dispersion dominates.",
            ),
            preferred=["volatility_expansion"],
            penalized=["volatility_compression", "short_duration_defined_risk"],
            macro_effect="macro_dispersion_dominant",
            iv_effect="iv_lift_high_dispersion",
            liquidity_effect="bad_fills_high_dispersion",
            pattern_effect="high_dispersion_vol_pattern",
            failure_modes=["post_event_clarity_against_vol_expansion"],
            notes="High dispersion event-vol expansion setup.",
        ),
        # 8
        _scenario(
            "margin_pressure_gap_risk",
            "margin_pressure_gap",
            _sector(
                "blend", "Cross-Sector Blend", "margin_pressure",
                momentum=0.35, relative_strength=0.30, dispersion=0.65, volatility=0.70, rotation=0.55,
                def_cyc="blend", growth_value="blend", liquidity="thin",
                notes="Cross-sector margin pressure; thin liquidity.",
            ),
            _peer(
                "margin_pressure_group", 8, relative_strength=0.32, dispersion=0.68, leadership=0.28,
                breakdown=0.72, confirmation=0.30, contradiction=0.65, crowding=0.50,
                notes="Peer breakdown pressure high.",
            ),
            _fundamental(
                "margin_pressure_abc", "ABC", "blend",
                revenue=0.40, margin=0.25, earnings=0.30, balance_sheet_risk=0.55, cash_flow=0.35,
                valuation_stretch=0.45, revision_momentum=0.20, event_quality=0.30, short_interest=0.45,
                trend=0.32, fragility=0.65, notes="Severe margin pressure and balance sheet risk.",
            ),
            preferred=["volatility_expansion"],
            penalized=["directional_convexity", "volatility_compression", "short_duration_defined_risk"],
            macro_effect="macro_margin_shock",
            iv_effect="iv_lift_with_gap_risk",
            liquidity_effect="severe_bad_fills",
            pattern_effect="margin_pressure_gap_pattern",
            failure_modes=["fundamental_fragility_against_directional", "margin_pressure_against_compression"],
            notes="Margin pressure gap risk; vol expansion favored, others penalized.",
        ),
        # 9
        _scenario(
            "revision_shock_vol_expansion",
            "revision_shock",
            _sector(
                "blend", "Cross-Sector Blend", "revision_shock",
                momentum=0.40, relative_strength=0.40, dispersion=0.70, volatility=0.65, rotation=0.55,
                def_cyc="blend", growth_value="blend", liquidity="moderate",
                notes="Cross-sector revision shock.",
            ),
            _peer(
                "revision_shock_group", 9, relative_strength=0.40, dispersion=0.72, leadership=0.32,
                breakdown=0.60, confirmation=0.32, contradiction=0.62, crowding=0.55,
                notes="Peer dispersion high after revision shock.",
            ),
            _fundamental(
                "revision_shock_def", "DEF", "blend",
                revenue=0.45, margin=0.50, earnings=0.45, balance_sheet_risk=0.30, cash_flow=0.50,
                valuation_stretch=0.55, revision_momentum=0.10, event_quality=0.40, short_interest=0.30,
                trend=0.40, fragility=0.50, notes="Sharp negative revision shock.",
            ),
            preferred=["volatility_expansion"],
            penalized=["volatility_compression", "directional_convexity"],
            macro_effect="macro_revision_shock",
            iv_effect="iv_lift_with_skew_shift",
            liquidity_effect="wide_spreads",
            pattern_effect="revision_shock_pattern",
            failure_modes=["revision_shock_against_compression", "low_dispersion_against_vol_expansion"],
            notes="Revision shock rewards vol expansion; penalizes compression and directional clarity.",
        ),
        # 10
        _scenario(
            "crowded_growth_unwind_vol_expansion",
            "crowded_unwind",
            _sector(
                "growth", "Growth Cross-Sector", "crowded_unwind",
                momentum=0.45, relative_strength=0.50, dispersion=0.78, volatility=0.70, rotation=0.65,
                def_cyc="blend", growth_value="growth", liquidity="moderate",
                notes="Cross-sector growth crowded unwind.",
            ),
            _peer(
                "growth_crowded_group", 10, relative_strength=0.42, dispersion=0.80, leadership=0.30,
                breakdown=0.78, confirmation=0.25, contradiction=0.78, crowding=0.85,
                notes="Crowding high; peer breakdown high.",
            ),
            _fundamental(
                "crowded_growth_ghi", "GHI", "growth",
                revenue=0.55, margin=0.45, earnings=0.50, balance_sheet_risk=0.30, cash_flow=0.50,
                valuation_stretch=0.78, revision_momentum=0.30, event_quality=0.40, short_interest=0.55,
                trend=0.45, fragility=0.55, notes="Crowded growth with stretched valuation.",
            ),
            preferred=["volatility_expansion"],
            penalized=["directional_convexity", "volatility_compression", "short_duration_defined_risk"],
            macro_effect="macro_growth_unwind",
            iv_effect="iv_lift_with_skew_inversion",
            liquidity_effect="wide_spreads_crowding",
            pattern_effect="crowded_unwind_pattern",
            failure_modes=["crowding_danger_against_directional", "crowding_danger_against_short_duration"],
            notes="Crowded growth unwind rewards vol expansion; penalizes all other families.",
        ),
        # 11
        _scenario(
            "post_earnings_quality_confirmed_iv_crush",
            "post_earnings_quality_iv_crush",
            _sector(
                "blend", "Cross-Sector Blend", "post_earnings_clarity",
                momentum=0.60, relative_strength=0.62, dispersion=0.30, volatility=0.30, rotation=0.40,
                def_cyc="blend", growth_value="blend", liquidity="deep",
                notes="Cross-sector post-earnings clarity; low dispersion.",
            ),
            _peer(
                "post_earnings_group", 9, relative_strength=0.62, dispersion=0.30, leadership=0.60,
                breakdown=0.18, confirmation=0.78, contradiction=0.18, crowding=0.30,
                notes="Peers confirm; benign crowding.",
            ),
            _fundamental(
                "post_earnings_jkl", "JKL", "blend",
                revenue=0.55, margin=0.65, earnings=0.72, balance_sheet_risk=0.18, cash_flow=0.75,
                valuation_stretch=0.40, revision_momentum=0.65, event_quality=0.70, short_interest=0.15,
                trend=0.65, fragility=0.20, notes="High quality post-earnings confirmation.",
            ),
            preferred=["volatility_compression", "short_duration_defined_risk"],
            penalized=["volatility_expansion"],
            macro_effect="macro_post_event_clarity",
            iv_effect="iv_crush_expected",
            liquidity_effect="tighter_spreads",
            pattern_effect="iv_crush_pattern",
            failure_modes=["post_event_clarity_against_vol_expansion"],
            notes="Post-earnings quality confirmation IV-crush setup.",
        ),
        # 12
        _scenario(
            "low_dispersion_range_compression",
            "low_dispersion_compression",
            _sector(
                "blend", "Cross-Sector Blend", "low_dispersion_range",
                momentum=0.50, relative_strength=0.50, dispersion=0.20, volatility=0.25, rotation=0.30,
                def_cyc="blend", growth_value="blend", liquidity="deep",
                notes="Cross-sector low-dispersion range.",
            ),
            _peer(
                "low_dispersion_group", 8, relative_strength=0.50, dispersion=0.22, leadership=0.45,
                breakdown=0.18, confirmation=0.65, contradiction=0.18, crowding=0.30,
                notes="Low dispersion peers.",
            ),
            _fundamental(
                "low_dispersion_mno", "MNO", "blend",
                revenue=0.50, margin=0.55, earnings=0.55, balance_sheet_risk=0.22, cash_flow=0.60,
                valuation_stretch=0.45, revision_momentum=0.50, event_quality=0.45, short_interest=0.20,
                trend=0.50, fragility=0.25, notes="Stable, average-quality fundamentals.",
            ),
            preferred=["volatility_compression", "short_duration_defined_risk"],
            penalized=["volatility_expansion"],
            macro_effect="macro_quiet_range",
            iv_effect="iv_low_stable",
            liquidity_effect="tighter_spreads",
            pattern_effect="range_compression_pattern",
            failure_modes=["high_dispersion_against_compression"],
            notes="Low-dispersion range compression setup.",
        ),
        # 13
        _scenario(
            "valuation_normalization_compression",
            "valuation_normalization",
            _sector(
                "blend", "Cross-Sector Blend", "valuation_normalization",
                momentum=0.50, relative_strength=0.55, dispersion=0.30, volatility=0.30, rotation=0.40,
                def_cyc="blend", growth_value="blend", liquidity="deep",
                notes="Valuation normalization regime.",
            ),
            _peer(
                "valuation_norm_group", 9, relative_strength=0.55, dispersion=0.30, leadership=0.55,
                breakdown=0.20, confirmation=0.65, contradiction=0.20, crowding=0.30,
                notes="Peer fundamentals confirm normalization.",
            ),
            _fundamental(
                "valuation_norm_pqr", "PQR", "blend",
                revenue=0.50, margin=0.60, earnings=0.65, balance_sheet_risk=0.18, cash_flow=0.65,
                valuation_stretch=0.30, revision_momentum=0.55, event_quality=0.55, short_interest=0.15,
                trend=0.55, fragility=0.18, notes="Reasonable valuation with quality earnings.",
            ),
            preferred=["volatility_compression", "short_duration_defined_risk"],
            penalized=["volatility_expansion"],
            macro_effect="macro_valuation_normalization",
            iv_effect="iv_decay_normalization",
            liquidity_effect="tighter_spreads",
            pattern_effect="valuation_normalization_pattern",
            failure_modes=["high_dispersion_against_compression", "revision_shock_against_compression"],
            notes="Valuation normalization supports compression.",
        ),
        # 14
        _scenario(
            "defensive_sector_stability_compression",
            "defensive_stability",
            _sector(
                "utilities", "Utilities", "defensive_stability",
                momentum=0.55, relative_strength=0.58, dispersion=0.22, volatility=0.20, rotation=0.30,
                def_cyc="defensive", growth_value="value", liquidity="deep",
                notes="Defensive utility stability.",
            ),
            _peer(
                "utilities_group", 6, relative_strength=0.58, dispersion=0.22, leadership=0.55,
                breakdown=0.12, confirmation=0.72, contradiction=0.12, crowding=0.25,
                notes="Utilities peers confirm; low contradiction.",
            ),
            _fundamental(
                "utilities_stu", "STU", "utilities",
                revenue=0.35, margin=0.65, earnings=0.65, balance_sheet_risk=0.30, cash_flow=0.65,
                valuation_stretch=0.35, revision_momentum=0.45, event_quality=0.40, short_interest=0.10,
                trend=0.55, fragility=0.15, notes="Stable utility with low fragility.",
            ),
            preferred=["volatility_compression", "short_duration_defined_risk", "directional_convexity"],
            penalized=["volatility_expansion"],
            macro_effect="macro_defensive_stability",
            iv_effect="iv_anchored_low",
            liquidity_effect="tighter_spreads",
            pattern_effect="defensive_stability_pattern",
            failure_modes=["high_dispersion_against_compression"],
            notes="Defensive sector stability compression setup.",
        ),
        # 15
        _scenario(
            "small_cap_low_liquidity_peer_decay",
            "small_cap_liquidity_decay",
            _sector(
                "small_cap", "Small Cap Blend", "low_liquidity_decay",
                momentum=0.30, relative_strength=0.30, dispersion=0.70, volatility=0.70, rotation=0.60,
                def_cyc="blend", growth_value="blend", liquidity="thin",
                notes="Small cap low liquidity; peer decay.",
            ),
            _peer(
                "small_cap_group", 10, relative_strength=0.30, dispersion=0.78, leadership=0.25,
                breakdown=0.75, confirmation=0.22, contradiction=0.72, crowding=0.45,
                notes="Small cap peer decay with dispersion.",
            ),
            _fundamental(
                "small_cap_vwx", "VWX", "small_cap",
                revenue=0.40, margin=0.40, earnings=0.40, balance_sheet_risk=0.50, cash_flow=0.35,
                valuation_stretch=0.45, revision_momentum=0.30, event_quality=0.30, short_interest=0.45,
                trend=0.30, fragility=0.60, notes="Fragile small cap with low liquidity.",
            ),
            preferred=["volatility_expansion"],
            penalized=["short_duration_defined_risk", "volatility_compression", "directional_convexity"],
            macro_effect="macro_small_cap_pressure",
            iv_effect="iv_lift_with_bad_fills",
            liquidity_effect="severe_bad_fills",
            pattern_effect="small_cap_decay_pattern",
            failure_modes=["small_cap_liquidity_decay_against_short_duration", "crowded_fakeout_against_short_duration"],
            notes="Small cap low-liquidity peer decay; vol expansion survives, short-duration destroyed.",
        ),
        # 16
        _scenario(
            "wide_peer_dispersion_bad_fill",
            "wide_dispersion_bad_fill",
            _sector(
                "blend", "Cross-Sector Blend", "wide_dispersion_bad_fill",
                momentum=0.45, relative_strength=0.45, dispersion=0.80, volatility=0.60, rotation=0.55,
                def_cyc="blend", growth_value="blend", liquidity="thin",
                notes="Wide dispersion; bad fill pressure.",
            ),
            _peer(
                "wide_dispersion_group", 10, relative_strength=0.42, dispersion=0.80, leadership=0.35,
                breakdown=0.68, confirmation=0.28, contradiction=0.72, crowding=0.55,
                notes="Wide dispersion peers; bad fill pressure.",
            ),
            _fundamental(
                "wide_dispersion_yza", "YZA", "blend",
                revenue=0.45, margin=0.50, earnings=0.50, balance_sheet_risk=0.30, cash_flow=0.50,
                valuation_stretch=0.50, revision_momentum=0.40, event_quality=0.45, short_interest=0.35,
                trend=0.45, fragility=0.40, notes="Average quality; dispersion dominates.",
            ),
            preferred=["volatility_expansion"],
            penalized=["short_duration_defined_risk", "volatility_compression"],
            macro_effect="macro_dispersion_dominant",
            iv_effect="iv_lift_high_dispersion",
            liquidity_effect="wide_spreads_bad_fills",
            pattern_effect="wide_dispersion_pattern",
            failure_modes=["small_cap_liquidity_decay_against_short_duration"],
            notes="Wide peer dispersion bad-fill pressure.",
        ),
        # 17
        _scenario(
            "crowded_trade_intraday_fakeout",
            "crowded_intraday_fakeout",
            _sector(
                "blend", "Cross-Sector Blend", "crowded_intraday_fakeout",
                momentum=0.55, relative_strength=0.55, dispersion=0.65, volatility=0.65, rotation=0.60,
                def_cyc="blend", growth_value="blend", liquidity="moderate",
                notes="Crowded intraday fakeout risk.",
            ),
            _peer(
                "crowded_intraday_group", 9, relative_strength=0.50, dispersion=0.65, leadership=0.45,
                breakdown=0.55, confirmation=0.40, contradiction=0.65, crowding=0.85,
                notes="Crowded; intraday fakeout risk.",
            ),
            _fundamental(
                "crowded_bcd", "BCD", "blend",
                revenue=0.50, margin=0.50, earnings=0.50, balance_sheet_risk=0.30, cash_flow=0.50,
                valuation_stretch=0.55, revision_momentum=0.40, event_quality=0.40, short_interest=0.55,
                trend=0.50, fragility=0.45, notes="Average quality; crowding dominates.",
            ),
            preferred=["volatility_expansion"],
            penalized=["short_duration_defined_risk", "directional_convexity"],
            macro_effect="macro_crowding_pressure",
            iv_effect="iv_lift_intraday_fakeout",
            liquidity_effect="bad_fills_intraday",
            pattern_effect="intraday_fakeout_pattern",
            failure_modes=["crowded_fakeout_against_short_duration", "crowding_danger_against_directional"],
            notes="Crowded trade intraday fakeout; vol expansion survives, others exposed.",
        ),
        # 18
        _scenario(
            "sector_rotation_late_day_liquidity_fade",
            "sector_rotation_late_day_liquidity_fade",
            _sector(
                "blend", "Cross-Sector Blend", "sector_rotation_late_day",
                momentum=0.40, relative_strength=0.45, dispersion=0.70, volatility=0.60, rotation=0.90,
                def_cyc="blend", growth_value="blend", liquidity="thin",
                notes="Late-day sector rotation with liquidity fade.",
            ),
            _peer(
                "rotation_late_day_group", 9, relative_strength=0.42, dispersion=0.72, leadership=0.35,
                breakdown=0.62, confirmation=0.30, contradiction=0.68, crowding=0.50,
                notes="Sector rotation late-day; liquidity fading.",
            ),
            _fundamental(
                "rotation_late_day_efg", "EFG", "blend",
                revenue=0.45, margin=0.50, earnings=0.50, balance_sheet_risk=0.30, cash_flow=0.50,
                valuation_stretch=0.50, revision_momentum=0.40, event_quality=0.40, short_interest=0.30,
                trend=0.45, fragility=0.40, notes="Average quality; late-day rotation dominates.",
            ),
            preferred=["volatility_expansion"],
            penalized=["short_duration_defined_risk", "directional_convexity", "volatility_compression"],
            macro_effect="macro_late_day_rotation",
            iv_effect="iv_lift_late_day",
            liquidity_effect="severe_late_day_fade",
            pattern_effect="late_day_rotation_pattern",
            failure_modes=["sector_rotation_late_day_bad_fill", "small_cap_liquidity_decay_against_short_duration"],
            notes="Sector rotation late-day liquidity fade; vol expansion only survivor.",
        ),
    ]


def scenario_for_id(scenario_id: str) -> SectorPeerFundamentalScenario:
    for scenario in build_sector_peer_fundamental_scenarios():
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(scenario_id)


def build_scenario_ledger_records() -> list[dict]:
    return [
        {
            "scenario_id": scenario.scenario_id,
            "regime_tag": scenario.regime_tag,
            "sector_id": scenario.sector_context.sector_id,
            "sector_name": scenario.sector_context.sector_name,
            "peer_group_id": scenario.peer_context.peer_group_id,
            "valuation_regime": scenario.valuation_context.valuation_regime,
            "fundamental_verdict": scenario.risk_summary.verdict,
            "preferred_strategy_families": sorted(scenario.preferred_strategy_families),
            "penalized_strategy_families": sorted(scenario.penalized_strategy_families),
            "expected_iv_effect": scenario.expected_iv_effect,
            "expected_liquidity_slippage_effect": scenario.expected_liquidity_slippage_effect,
            "expected_failure_modes": sorted(scenario.expected_failure_modes),
        }
        for scenario in build_sector_peer_fundamental_scenarios()
    ]


REQUIRED_SCENARIO_IDS = frozenset({
    "tech_leadership_breakout_confirmed",
    "semiconductor_peer_fakeout",
    "financials_rate_tailwind_breakout",
    "consumer_discretionary_peer_breakdown",
    "healthcare_defensive_rotation_confirmed",
    "earnings_quality_uncertainty_vol_expansion",
    "high_peer_dispersion_event_vol",
    "margin_pressure_gap_risk",
    "revision_shock_vol_expansion",
    "crowded_growth_unwind_vol_expansion",
    "post_earnings_quality_confirmed_iv_crush",
    "low_dispersion_range_compression",
    "valuation_normalization_compression",
    "defensive_sector_stability_compression",
    "small_cap_low_liquidity_peer_decay",
    "wide_peer_dispersion_bad_fill",
    "crowded_trade_intraday_fakeout",
    "sector_rotation_late_day_liquidity_fade",
})


SECTOR_PEER_FUNDAMENTAL_FIXTURE_VERSION = FUNDAMENTAL_FIXTURE_VERSION
