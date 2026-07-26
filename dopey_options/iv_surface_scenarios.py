"""Deterministic IV surface scenarios for offline DOPEY replay."""
from __future__ import annotations

from .iv_surface_expansion import IVSurfaceScenario, build_surface_grid, summarize_iv_surface_risk
from .skew_term_structure import build_skew_profile, build_term_structure_profile
from .volatility_regime import build_volatility_regime_transition


IV_SURFACE_SCENARIO_VERSION = "dopey-iv-surface-scenarios-v1"


def _scenario(
    scenario_id: str,
    regime_tag: str,
    iv_rank: float,
    iv_percentile: float,
    realized_volatility: float,
    implied_vs_realized_gap: float,
    front_event_bump: float,
    term_slope: float,
    put_skew: float,
    call_skew: float,
    wing_elevation: float,
    iv_crush_risk: float,
    iv_expansion_potential: float,
    surface_instability: float,
    preferred: list[str],
    penalized: list[str],
) -> IVSurfaceScenario:
    return IVSurfaceScenario(
        scenario_id=scenario_id,
        regime_tag=regime_tag,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        realized_volatility=realized_volatility,
        implied_vs_realized_gap=implied_vs_realized_gap,
        front_event_bump=front_event_bump,
        term_slope=term_slope,
        put_skew=put_skew,
        call_skew=call_skew,
        wing_elevation=wing_elevation,
        iv_crush_risk=iv_crush_risk,
        iv_expansion_potential=iv_expansion_potential,
        surface_instability=surface_instability,
        preferred_strategy_families=preferred,
        penalized_strategy_families=penalized,
        strategy_outcome_hints={
            family: "preferred_iv_surface_context" for family in preferred
        } | {
            family: "penalized_iv_surface_context" for family in penalized
        },
    )


def build_iv_surface_scenarios() -> list[IVSurfaceScenario]:
    return [
        _scenario("pre_event_vol_expansion", "event_vol_expansion", 0.58, 0.64, 0.22, 0.08, 0.82, -0.055, 0.28, 0.22, 0.72, 0.34, 0.88, 0.34, ["volatility_expansion", "directional_convexity"], ["volatility_compression", "short_duration_defined_risk"]),
        _scenario("post_event_iv_crush", "post_event_iv_crush", 0.72, 0.78, 0.24, 0.13, 0.10, 0.045, 0.16, 0.10, 0.22, 0.90, 0.12, 0.24, ["volatility_compression"], ["volatility_expansion"]),
        _scenario("macro_shock_backwardation", "macro_shock_risk_off", 0.86, 0.90, 0.36, 0.21, 0.70, -0.125, 0.74, 0.22, 0.86, 0.24, 0.84, 0.70, ["volatility_expansion"], ["volatility_compression", "short_duration_defined_risk"]),
        _scenario("range_bound_compression", "range_bound_pin", 0.62, 0.66, 0.18, 0.14, 0.06, 0.035, 0.12, 0.12, 0.18, 0.78, 0.16, 0.18, ["volatility_compression"], ["volatility_expansion"]),
        _scenario("bullish_call_skew_breakout", "bullish_breakout", 0.42, 0.48, 0.20, 0.04, 0.18, -0.010, 0.12, 0.58, 0.48, 0.28, 0.62, 0.26, ["directional_convexity", "short_duration_defined_risk"], ["volatility_compression"]),
        _scenario("bearish_put_skew_breakdown", "bearish_breakdown", 0.52, 0.56, 0.25, 0.06, 0.28, -0.030, 0.66, 0.16, 0.58, 0.30, 0.66, 0.34, ["directional_convexity", "volatility_expansion"], ["volatility_compression"]),
        _scenario("premium_overpayment_trap", "liquidity_decay", 0.96, 0.98, 0.16, 0.31, 0.42, -0.020, 0.56, 0.50, 0.82, 0.84, 0.18, 0.58, [], ["directional_convexity", "volatility_expansion", "volatility_compression", "short_duration_defined_risk"]),
        _scenario("stable_low_iv_breakout", "trend_vol_expansion", 0.24, 0.30, 0.18, 0.02, 0.12, 0.010, 0.10, 0.18, 0.26, 0.18, 0.64, 0.12, ["directional_convexity", "short_duration_defined_risk"], ["volatility_compression"]),
        _scenario("unstable_surface_fakeout", "gap_reversal", 0.68, 0.72, 0.22, 0.12, 0.36, -0.040, 0.64, 0.52, 0.78, 0.54, 0.42, 0.92, [], ["directional_convexity", "short_duration_defined_risk"]),
        _scenario("low_liquidity_wide_skew", "low_liquidity_decay", 0.74, 0.78, 0.20, 0.17, 0.24, 0.055, 0.82, 0.36, 0.76, 0.62, 0.26, 0.74, [], ["directional_convexity", "volatility_compression", "short_duration_defined_risk"]),
        _scenario("front_expiry_event_bump", "high_spread_bad_fill", 0.70, 0.76, 0.26, 0.15, 0.94, -0.090, 0.38, 0.32, 0.70, 0.46, 0.78, 0.62, ["volatility_expansion"], ["volatility_compression", "short_duration_defined_risk"]),
        _scenario("normal_contango_chop", "chop_vol_compression", 0.38, 0.42, 0.16, 0.03, 0.08, 0.052, 0.12, 0.10, 0.16, 0.42, 0.22, 0.14, ["volatility_compression", "short_duration_defined_risk"], ["volatility_expansion"]),
    ]


def scenario_by_id() -> dict[str, IVSurfaceScenario]:
    return {scenario.scenario_id: scenario for scenario in build_iv_surface_scenarios()}


def scenario_for_id(scenario_id: str) -> IVSurfaceScenario:
    scenarios = scenario_by_id()
    if scenario_id not in scenarios:
        raise KeyError(f"unknown IV surface scenario: {scenario_id}")
    return scenarios[scenario_id]


REGIME_SCENARIO_MAP: dict[str, str] = {
    "event_vol_expansion": "pre_event_vol_expansion",
    "post_event_iv_crush": "post_event_iv_crush",
    "macro_shock_risk_off": "macro_shock_backwardation",
    "range_bound_pin": "range_bound_compression",
    "bullish_breakout": "bullish_call_skew_breakout",
    "bearish_breakdown": "bearish_put_skew_breakdown",
    "liquidity_decay": "premium_overpayment_trap",
    "trend_vol_expansion": "stable_low_iv_breakout",
    "gap_reversal": "unstable_surface_fakeout",
    "low_liquidity_decay": "low_liquidity_wide_skew",
    "high_spread_bad_fill": "front_expiry_event_bump",
    "chop_vol_compression": "normal_contango_chop",
}


def scenario_for_regime(regime_tag: str) -> IVSurfaceScenario:
    scenario_id = REGIME_SCENARIO_MAP.get(regime_tag, "normal_contango_chop")
    return scenario_for_id(scenario_id)


def build_scenario_ledger_records() -> list[dict]:
    records: list[dict] = []
    for scenario in build_iv_surface_scenarios():
        grid = build_surface_grid(scenario, "SPY_FIXTURE")
        risk = summarize_iv_surface_risk(scenario, grid)
        skew = build_skew_profile(scenario)
        term = build_term_structure_profile(scenario)
        transition = build_volatility_regime_transition(scenario)
        records.append({
            "scenario": scenario.to_dict(),
            "surface_grid": grid.to_dict(),
            "risk_summary": risk.to_dict(),
            "skew_profile": skew.to_dict(),
            "term_structure_profile": term.to_dict(),
            "volatility_regime_transition": transition.to_dict(),
        })
    return records
