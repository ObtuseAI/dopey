"""Deterministic macro-event scenario fixtures for DOPEY paper replay.

Fourteen offline fixtures covering CPI/PPI/FOMC/jobs/rates/dollar/VIX/breadth/sector/
liquidity/overnight/risk-on/risk-off transitions. No real macro data is used.
"""
from __future__ import annotations

from .macro_event_fixture import (
    MacroEventFixture,
    MacroEventRiskSummary,
    MacroEventScenario,
    MacroRegimeContext,
    summarize_macro_risk,
)


MACRO_EVENT_SCENARIO_VERSION = "dopey-macro-event-scenarios-v1"


def _event(
    event_id: str,
    event_type: str,
    intensity: float,
    surprise: str,
    bias: str,
    vol: float,
    rates: float,
    dollar: float,
    sector_rot: float,
    breadth: float,
    liquidity: float,
    overnight: float,
    notes: str,
) -> MacroEventFixture:
    return MacroEventFixture(
        event_id=event_id,
        event_type=event_type,
        event_window=event_id.replace("_", " "),
        event_intensity=intensity,
        surprise_direction=surprise,
        risk_on_off_bias=bias,
        volatility_impulse=vol,
        rates_pressure=rates,
        dollar_pressure=dollar,
        sector_rotation_pressure=sector_rot,
        breadth_pressure=breadth,
        liquidity_pressure=liquidity,
        overnight_futures_pressure=overnight,
        notes=notes,
    )


def _regime(
    regime_id: str,
    risk_on: float,
    risk_off: float,
    rate_shock: float,
    inflation: float,
    dollar: float,
    vix: float,
    vvix: float,
    breadth: float,
    sector_rot: float,
    liquidity: float,
    overnight: float,
    trend: float,
    fakeout: float,
    notes: str,
) -> MacroRegimeContext:
    return MacroRegimeContext(
        regime_id=regime_id,
        risk_on_score=risk_on,
        risk_off_score=risk_off,
        rate_shock_score=rate_shock,
        inflation_pressure_score=inflation,
        dollar_strength_score=dollar,
        vix_stress_score=vix,
        vvix_stress_score=vvix,
        breadth_score=breadth,
        sector_rotation_score=sector_rot,
        liquidity_regime_score=liquidity,
        overnight_pressure_score=overnight,
        macro_trend_score=trend,
        macro_fakeout_risk_score=fakeout,
        notes=notes,
    )


def _scenario(
    scenario_id: str,
    regime_tag: str,
    event: MacroEventFixture,
    regime: MacroRegimeContext,
    preferred: list[str],
    penalized: list[str],
    iv_effect: str,
    slippage_effect: str,
    pattern_effect: str,
    failure_modes: list[str],
    notes: str,
) -> MacroEventScenario:
    return MacroEventScenario(
        scenario_id=scenario_id,
        regime_tag=regime_tag,
        macro_event=event,
        regime_context=regime,
        risk_summary=summarize_macro_risk(event, regime),
        preferred_strategy_families=preferred,
        penalized_strategy_families=penalized,
        expected_iv_effect=iv_effect,
        expected_slippage_effect=slippage_effect,
        expected_pattern_effect=pattern_effect,
        expected_failure_modes=failure_modes,
        notes=notes,
    )


def build_macro_event_scenarios() -> list[MacroEventScenario]:
    """Return the 14 required deterministic macro-event scenarios."""
    return [
        # 1
        _scenario(
            "pre_fomc_vol_expansion",
            "event_vol_expansion",
            _event(
                "pre_fomc_vol_expansion_event", "fomc_fixture", 0.72, "hawkish", "neutral",
                vol=0.80, rates=0.60, dollar=0.45, sector_rot=0.50, breadth=0.50, liquidity=0.42,
                overnight=0.70,
                notes="Rates decision ahead; IV drifts higher, liquidity thins.",
            ),
            _regime(
                "pre_fomc_regime", risk_on=0.45, risk_off=0.50, rate_shock=0.65,
                inflation=0.50, dollar=0.50, vix=0.75, vvix=0.72, breadth=0.48,
                sector_rot=0.55, liquidity=0.40, overnight=0.70, trend=0.45,
                fakeout=0.55, notes="Macro shock potential, directional clarity low.",
            ),
            preferred=["volatility_expansion"],
            penalized=["volatility_compression", "short_duration_defined_risk"],
            iv_effect="iv_expansion_expected",
            slippage_effect="wider_spreads_event_vol",
            pattern_effect="vol_expansion_pattern_preferred",
            failure_modes=["premium_overpayment", "macro_fakeout_against_directional"],
            notes="Pre-FOMC uncertainty rewards long-vol; penalizes compression and short-duration.",
        ),
        # 2
        _scenario(
            "post_fomc_iv_crush",
            "post_event_iv_crush",
            _event(
                "post_fomc_iv_crush_event", "fomc_fixture", 0.40, "neutral", "neutral",
                vol=0.20, rates=0.25, dollar=0.20, sector_rot=0.45, breadth=0.55,
                liquidity=0.72, overnight=0.25,
                notes="FOMC in-line; event risk removed; IV collapses.",
            ),
            _regime(
                "post_fomc_regime", risk_on=0.55, risk_off=0.25, rate_shock=0.25,
                inflation=0.35, dollar=0.40, vix=0.20, vvix=0.25, breadth=0.60,
                sector_rot=0.45, liquidity=0.70, overnight=0.20, trend=0.55,
                fakeout=0.25, notes="Normalization supports range/compression.",
            ),
            preferred=["volatility_compression", "short_duration_defined_risk"],
            penalized=["volatility_expansion"],
            iv_effect="iv_crush_expected",
            slippage_effect="tighter_spreads_post_event",
            pattern_effect="range_pin_pattern_preferred",
            failure_modes=["post_event_crush_after_vol_expansion"],
            notes="Normalization rewards compression; crushes long-vol.",
        ),
        # 3
        _scenario(
            "hot_cpi_rate_shock",
            "macro_shock_risk_off",
            _event(
                "hot_cpi_rate_shock_event", "cpi_fixture", 0.85, "upside", "risk_off",
                vol=0.78, rates=0.80, dollar=0.70, sector_rot=0.60, breadth=0.35,
                liquidity=0.35, overnight=0.80,
                notes="CPI surprises hot; rates shock, risk-off.",
            ),
            _regime(
                "hot_cpi_regime", risk_on=0.15, risk_off=0.80, rate_shock=0.85,
                inflation=0.90, dollar=0.75, vix=0.80, vvix=0.78, breadth=0.35,
                sector_rot=0.60, liquidity=0.30, overnight=0.80, trend=0.20,
                fakeout=0.45, notes="Macro shock regime; compression is dangerous.",
            ),
            preferred=["volatility_expansion", "directional_convexity"],
            penalized=["volatility_compression", "short_duration_defined_risk"],
            iv_effect="iv_spike_and_skew_shift",
            slippage_effect="wide_spreads_bad_fills",
            pattern_effect="breakdown_continuation_risk_off",
            failure_modes=["rate_shock_against_compression", "macro_shock_danger"],
            notes="Hot CPI is classic macro shock; compression and short-duration punished.",
        ),
        # 4
        _scenario(
            "cool_cpi_risk_on_rebound",
            "bullish_breakout",
            _event(
                "cool_cpi_risk_on_event", "cpi_fixture", 0.55, "downside", "risk_on",
                vol=0.35, rates=0.30, dollar=0.25, sector_rot=0.50, breadth=0.70,
                liquidity=0.75, overnight=0.30,
                notes="CPI cooler than expected; yields fall, futures lift.",
            ),
            _regime(
                "cool_cpi_regime", risk_on=0.78, risk_off=0.15, rate_shock=0.20,
                inflation=0.25, dollar=0.25, vix=0.28, vvix=0.30, breadth=0.72,
                sector_rot=0.45, liquidity=0.75, overnight=0.25, trend=0.75,
                fakeout=0.25, notes="Confirmed risk-on supports directional bullish.",
            ),
            preferred=["directional_convexity", "short_duration_defined_risk"],
            penalized=["volatility_compression"],
            iv_effect="iv_compression_relief",
            slippage_effect="clean_fills",
            pattern_effect="bullish_breakout_continuation",
            failure_modes=[],
            notes="Cool CPI confirms risk-on; bullish directional rewarded.",
        ),
        # 5
        _scenario(
            "ppi_inflation_pressure",
            "event_vol_expansion",
            _event(
                "ppi_inflation_pressure_event", "ppi_fixture", 0.68, "upside", "risk_off",
                vol=0.62, rates=0.70, dollar=0.55, sector_rot=0.55, breadth=0.45,
                liquidity=0.45, overnight=0.60,
                notes="PPI runs hot; inflation scare returns.",
            ),
            _regime(
                "ppi_pressure_regime", risk_on=0.25, risk_off=0.65, rate_shock=0.70,
                inflation=0.75, dollar=0.60, vix=0.65, vvix=0.68, breadth=0.45,
                sector_rot=0.55, liquidity=0.42, overnight=0.60, trend=0.30,
                fakeout=0.50, notes="Inflation pressure supports vol expansion.",
            ),
            preferred=["volatility_expansion"],
            penalized=["volatility_compression", "directional_convexity"],
            iv_effect="iv_expansion_from_inflation_fear",
            slippage_effect="widening_spreads",
            pattern_effect="macro_shock_vol_transition",
            failure_modes=["macro_fakeout_against_directional"],
            notes="PPI inflation pressure is a vol-expansion catalyst; directional clarity low.",
        ),
        # 6
        _scenario(
            "jobs_growth_shock",
            "trend_vol_expansion",
            _event(
                "jobs_growth_shock_event", "jobs_fixture", 0.62, "upside", "risk_on",
                vol=0.50, rates=0.65, dollar=0.55, sector_rot=0.50, breadth=0.60,
                liquidity=0.55, overnight=0.55,
                notes="Jobs report strong; rates reprices higher, but growth confims.",
            ),
            _regime(
                "jobs_shock_regime", risk_on=0.60, risk_off=0.35, rate_shock=0.65,
                inflation=0.45, dollar=0.55, vix=0.48, vvix=0.50, breadth=0.62,
                sector_rot=0.50, liquidity=0.55, overnight=0.55, trend=0.65,
                fakeout=0.40, notes="Growth shock supports trend continuation.",
            ),
            preferred=["directional_convexity", "volatility_expansion"],
            penalized=["volatility_compression"],
            iv_effect="iv_lift_with_trend",
            slippage_effect="moderate_spread_widening",
            pattern_effect="trend_vol_continuation",
            failure_modes=["breadth_contradiction_against_directional"],
            notes="Jobs growth shock rewards directional trend and mild vol expansion.",
        ),
        # 7
        _scenario(
            "dollar_squeeze_risk_off",
            "macro_shock_risk_off",
            _event(
                "dollar_squeeze_event", "dollar_squeeze", 0.70, "upside", "risk_off",
                vol=0.58, rates=0.55, dollar=0.90, sector_rot=0.60, breadth=0.30,
                liquidity=0.38, overnight=0.70,
                notes="Dollar spikes; liquidity leaves risk assets.",
            ),
            _regime(
                "dollar_squeeze_regime", risk_on=0.10, risk_off=0.85, rate_shock=0.50,
                inflation=0.40, dollar=0.92, vix=0.72, vvix=0.70, breadth=0.30,
                sector_rot=0.65, liquidity=0.35, overnight=0.75, trend=0.15,
                fakeout=0.55, notes="Dollar-squeeze risk-off is dangerous for range structures.",
            ),
            preferred=["volatility_expansion", "directional_convexity"],
            penalized=["volatility_compression", "short_duration_defined_risk"],
            iv_effect="iv_risk_premium_expansion",
            slippage_effect="severe_bad_fill_pressure",
            pattern_effect="risk_off_breakdown",
            failure_modes=["liquidity_contraction_bad_fill_failure", "macro_shock_danger"],
            notes="Dollar squeeze triggers broad risk-off and bad fills for short-duration/compression.",
        ),
        # 8
        _scenario(
            "vix_vvix_spike",
            "event_vol_expansion",
            _event(
                "vix_vvix_spike_event", "volatility_index_spike", 0.60, "neutral",
                "risk_off", vol=0.90, rates=0.30, dollar=0.40, sector_rot=0.45,
                breadth=0.35, liquidity=0.32, overnight=0.55,
                notes="VIX and VVIX spike together; vol-of-vol rises.",
            ),
            _regime(
                "vix_vvix_regime", risk_on=0.20, risk_off=0.75, rate_shock=0.35,
                inflation=0.35, dollar=0.45, vix=0.95, vvix=0.92, breadth=0.35,
                sector_rot=0.50, liquidity=0.30, overnight=0.60, trend=0.25,
                fakeout=0.60, notes="Pure volatility-index stress; compression and short-duration fail.",
            ),
            preferred=["volatility_expansion"],
            penalized=["volatility_compression", "short_duration_defined_risk", "directional_convexity"],
            iv_effect="iv_expansion_and_skew_steepening",
            slippage_effect="wide_spreads",
            pattern_effect="vol_expansion_stress",
            failure_modes=["vix_spike_against_compression", "short_duration_bad_fill_risk"],
            notes="VIX/VVIX spike is ideal for long vol; dangerous for others.",
        ),
        # 9
        _scenario(
            "breadth_breakdown",
            "bearish_breakdown",
            _event(
                "breadth_breakdown_event", "breadth_breakdown", 0.58, "downside",
                "risk_off", vol=0.55, rates=0.30, dollar=0.45, sector_rot=0.65,
                breadth=0.15, liquidity=0.40, overnight=0.50,
                notes="Advance/decline collapses; breadth pressure surges.",
            ),
            _regime(
                "breadth_breakdown_regime", risk_on=0.20, risk_off=0.78, rate_shock=0.30,
                inflation=0.30, dollar=0.50, vix=0.68, vvix=0.65, breadth=0.12,
                sector_rot=0.70, liquidity=0.38, overnight=0.55, trend=0.20,
                fakeout=0.45, notes="Breadth breakdown supports bearish directional and vol expansion.",
            ),
            preferred=["directional_convexity", "volatility_expansion"],
            penalized=["volatility_compression", "short_duration_defined_risk"],
            iv_effect="iv_lift_from_breadth_stress",
            slippage_effect="widening_spreads",
            pattern_effect="bearish_breakdown_breadth",
            failure_modes=["breadth_contradiction_against_directional"],
            notes="Breadth deterioration rewards bearish directional and vol expansion.",
        ),
        # 10
        _scenario(
            "sector_rotation_growth_to_value",
            "chop_vol_compression",
            _event(
                "sector_rotation_event", "sector_rotation", 0.42, "neutral", "neutral",
                vol=0.38, rates=0.35, dollar=0.30, sector_rot=0.85, breadth=0.45,
                liquidity=0.60, overnight=0.35,
                notes="Growth-to-value rotation; dispersion rises but index range-bound.",
            ),
            _regime(
                "sector_rotation_regime", risk_on=0.50, risk_off=0.45, rate_shock=0.35,
                inflation=0.40, dollar=0.35, vix=0.40, vvix=0.42, breadth=0.45,
                sector_rot=0.88, liquidity=0.58, overnight=0.35, trend=0.40,
                fakeout=0.60, notes="Sector rotation creates chop and fakeout risk.",
            ),
            preferred=["volatility_compression", "short_duration_defined_risk"],
            penalized=["directional_convexity"],
            iv_effect="range_bound_iv",
            slippage_effect="moderate_dispersion_spreads",
            pattern_effect="chop_fakeout",
            failure_modes=["sector_rotation_mismatch", "macro_fakeout_against_directional"],
            notes="Sector rotation chops indices; directional entries face fakeouts.",
        ),
        # 11
        _scenario(
            "liquidity_contraction_bad_fill",
            "low_liquidity_decay",
            _event(
                "liquidity_contraction_event", "liquidity_contraction", 0.70, "neutral",
                "risk_off", vol=0.58, rates=0.50, dollar=0.55, sector_rot=0.40,
                breadth=0.35, liquidity=0.02, overnight=0.75,
                notes="Liquidity regime contracts; fills degrade.",
            ),
            _regime(
                "liquidity_contraction_regime", risk_on=0.30, risk_off=0.65, rate_shock=0.50,
                inflation=0.40, dollar=0.60, vix=0.65, vvix=0.68, breadth=0.35,
                sector_rot=0.45, liquidity=0.05, overnight=0.80, trend=0.25,
                fakeout=0.55, notes="Liquidity contraction is especially toxic for short-duration fills.",
            ),
            preferred=["volatility_expansion"],
            penalized=["short_duration_defined_risk", "volatility_compression", "directional_convexity"],
            iv_effect="iv_lift_from_liquidity_stress",
            slippage_effect="severe_bad_fills",
            pattern_effect="liquidity_trap",
            failure_modes=["liquidity_contraction_bad_fill_failure"],
            notes="Liquidity contraction penalizes any family needing tight fills.",
        ),
        # 12
        _scenario(
            "overnight_gap_risk",
            "gap_reversal",
            _event(
                "overnight_gap_event", "overnight_gap_pressure", 0.55, "neutral", "neutral",
                vol=0.55, rates=0.30, dollar=0.35, sector_rot=0.40, breadth=0.42,
                liquidity=0.35, overnight=0.95,
                notes="Overnight futures gap into a macro headline; intraday reversal risk.",
            ),
            _regime(
                "overnight_gap_regime", risk_on=0.42, risk_off=0.52, rate_shock=0.30,
                inflation=0.30, dollar=0.40, vix=0.58, vvix=0.62, breadth=0.42,
                sector_rot=0.40, liquidity=0.32, overnight=0.98, trend=0.25,
                fakeout=0.82, notes="Overnight gap creates fakeout and slippage risk.",
            ),
            preferred=["volatility_expansion"],
            penalized=["directional_convexity", "short_duration_defined_risk"],
            iv_effect="gap_iv_jump",
            slippage_effect="gap_slippage",
            pattern_effect="gap_reversal_fakeout",
            failure_modes=["overnight_gap_slippage_failure", "macro_fakeout_against_directional"],
            notes="Overnight gap punishes directional and short-duration; rewards vol expansion.",
        ),
        # 13
        _scenario(
            "risk_on_breakout_confirmation",
            "bullish_breakout",
            _event(
                "risk_on_breakout_event", "risk_on_rebound", 0.45, "upside", "risk_on",
                vol=0.25, rates=0.20, dollar=0.20, sector_rot=0.40, breadth=0.78,
                liquidity=0.78, overnight=0.20,
                notes="Risk-on confirmed by breadth, rates, and futures.",
            ),
            _regime(
                "risk_on_regime", risk_on=0.85, risk_off=0.10, rate_shock=0.15,
                inflation=0.20, dollar=0.20, vix=0.18, vvix=0.20, breadth=0.80,
                sector_rot=0.40, liquidity=0.78, overnight=0.15, trend=0.82,
                fakeout=0.15, notes="Clean risk-on breakout supports bullish directional and short-DTE.",
            ),
            preferred=["directional_convexity", "short_duration_defined_risk"],
            penalized=["volatility_expansion", "volatility_compression"],
            iv_effect="iv_floor_low",
            slippage_effect="tight_spreads",
            pattern_effect="bullish_breakout_confirmation",
            failure_modes=[],
            notes="Confirmed risk-on rewards directional and defined-risk short-duration structures.",
        ),
        # 14
        _scenario(
            "risk_off_breakdown_confirmation",
            "bearish_breakdown",
            _event(
                "risk_off_breakdown_event", "risk_off_breakdown", 0.55, "downside",
                "risk_off", vol=0.62, rates=0.35, dollar=0.65, sector_rot=0.55,
                breadth=0.22, liquidity=0.45, overnight=0.70,
                notes="Risk-off confirmed by breadth, dollar, and futures breakdown.",
            ),
            _regime(
                "risk_off_regime", risk_on=0.10, risk_off=0.88, rate_shock=0.40,
                inflation=0.30, dollar=0.70, vix=0.78, vvix=0.75, breadth=0.20,
                sector_rot=0.60, liquidity=0.42, overnight=0.75, trend=0.12,
                fakeout=0.25, notes="Confirmed risk-off breakdown supports bearish directional and vol expansion.",
            ),
            preferred=["directional_convexity", "volatility_expansion"],
            penalized=["volatility_compression", "short_duration_defined_risk"],
            iv_effect="iv_spike_risk_off",
            slippage_effect="wide_spreads_breakdown",
            pattern_effect="bearish_breakdown_confirmation",
            failure_modes=["macro_shock_danger"],
            notes="Confirmed risk-off rewards bearish directional and long vol; crushes compression.",
        ),
    ]


def scenario_for_id(scenario_id: str) -> MacroEventScenario:
    """Return scenario by id."""
    for scenario in build_macro_event_scenarios():
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(scenario_id)


def scenario_for_regime(regime_tag: str) -> MacroEventScenario:
    """Return the first scenario matching a regime tag."""
    for scenario in build_macro_event_scenarios():
        if scenario.regime_tag == regime_tag:
            return scenario
    # Fallback: a neutral scenario so every regime has something.
    return scenario_for_id("risk_on_breakout_confirmation")


def build_scenario_ledger_records() -> list[dict]:
    """Return deterministic ledger rows (metadata only) for documentation."""
    return [
        {
            "scenario_id": scenario.scenario_id,
            "regime_tag": scenario.regime_tag,
            "event_type": scenario.macro_event.event_type,
            "event_intensity": scenario.macro_event.event_intensity,
            "risk_on_off_bias": scenario.macro_event.risk_on_off_bias,
            "preferred_strategy_families": sorted(scenario.preferred_strategy_families),
            "penalized_strategy_families": sorted(scenario.penalized_strategy_families),
            "verdict": scenario.risk_summary.verdict,
            "risk_flags": sorted(scenario.risk_summary.risk_flags),
            "expected_iv_effect": scenario.expected_iv_effect,
            "expected_slippage_effect": scenario.expected_slippage_effect,
            "expected_failure_modes": sorted(scenario.expected_failure_modes),
        }
        for scenario in build_macro_event_scenarios()
    ]
