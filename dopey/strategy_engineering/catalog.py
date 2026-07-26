"""Interpretable primitive and mechanism catalog for candidate construction."""

from __future__ import annotations

from typing import Final

from .schema import MechanismSpec, PrimitiveSpec


PRIMITIVES: Final[tuple[PrimitiveSpec, ...]] = (
    {"primitive_id": "trend_strength", "family": "technical", "expression": "normalized multi-horizon trend slope and persistence", "output_domain": "[-1,1]", "leakage_risk": "low_if_point_in_time", "source_ids": ("alphaforge",)},
    {"primitive_id": "momentum_state", "family": "technical", "expression": "cross-horizon normalized momentum rank", "output_domain": "[-1,1]", "leakage_risk": "low_if_point_in_time", "source_ids": ("momentum-crashes",)},
    {"primitive_id": "participation", "family": "volume", "expression": "relative volume and signed participation state", "output_domain": "[-1,1]", "leakage_risk": "provider_quality", "source_ids": ("alphaforge",)},
    {"primitive_id": "volatility_state", "family": "volatility", "expression": "robust realized volatility percentile and slope", "output_domain": "[0,1]", "leakage_risk": "low_if_point_in_time", "source_ids": ("change-point",)},
    {"primitive_id": "relative_strength", "family": "cross_sectional", "expression": "symbol return minus sector and benchmark return", "output_domain": "[-1,1]", "leakage_risk": "universe_selection", "source_ids": ("alphaevolve-factor-mining",)},
    {"primitive_id": "spread_stationarity", "family": "relative_value", "expression": "point-in-time spread stability and mean-reversion score", "output_domain": "[0,1]", "leakage_risk": "pair_selection", "source_ids": ("pairs-trading",)},
    {"primitive_id": "factor_quality", "family": "fundamental", "expression": "point-in-time quality and cash-flow composite", "output_domain": "[0,1]", "leakage_risk": "revision_and_reporting_lag", "source_ids": ("alphaforge",)},
    {"primitive_id": "estimate_revision", "family": "fundamental", "expression": "timestamped analyst revision direction and breadth", "output_domain": "[-1,1]", "leakage_risk": "revision_timestamp", "source_ids": ("multifactor-timing",)},
    {"primitive_id": "valuation_state", "family": "fundamental", "expression": "sector-relative valuation percentile", "output_domain": "[0,1]", "leakage_risk": "reporting_lag", "source_ids": ("multifactor-timing",)},
    {"primitive_id": "breadth_state", "family": "market", "expression": "advance participation and leadership concentration", "output_domain": "[-1,1]", "leakage_risk": "universe_history", "source_ids": ("change-point",)},
    {"primitive_id": "cross_asset_stress", "family": "macro", "expression": "rates, credit, dollar, commodity and volatility stress", "output_domain": "[0,1]", "leakage_risk": "clock_alignment", "source_ids": ("change-point",)},
    {"primitive_id": "change_point_probability", "family": "regime", "expression": "online probability of a structural break", "output_domain": "[0,1]", "leakage_risk": "sequential_peeking", "source_ids": ("change-point", "confidence-sequences")},
    {"primitive_id": "options_skew", "family": "derivatives", "expression": "quality-gated downside skew and term structure", "output_domain": "[-1,1]", "leakage_risk": "surface_quality", "source_ids": ("alphaforge",)},
    {"primitive_id": "liquidity_state", "family": "market", "expression": "spread, turnover and depth proxy state", "output_domain": "[0,1]", "leakage_risk": "provider_quality", "source_ids": ("pairs-trading",)},
    {"primitive_id": "calibration_risk", "family": "metacognitive", "expression": "time-uniform upper bound on forecast error", "output_domain": "[0,1]", "leakage_risk": "low", "source_ids": ("confidence-sequences", "conformal-risk-control")},
)


MECHANISMS: Final[tuple[MechanismSpec, ...]] = (
    {"mechanism_id": "crash_aware_momentum", "thesis": "persistent relative momentum survives only outside rebound and panic states", "primitive_ids": ("trend_strength", "momentum_state", "participation", "cross_asset_stress"), "regime_guards": ("abstain when crash rebound probability is elevated", "require breadth confirmation"), "failure_conditions": ("momentum reverses", "breadth diverges", "stress regime changes"), "horizons": (5, 10, 20), "source_ids": ("momentum-crashes", "multifactor-timing")},
    {"mechanism_id": "relative_value_reversion", "thesis": "stable relative-value spreads may revert after idiosyncratic dislocation", "primitive_ids": ("spread_stationarity", "relative_strength", "volatility_state", "liquidity_state"), "regime_guards": ("abstain after detected structural break", "require defensible liquidity"), "failure_conditions": ("cointegration proxy breaks", "cost stress erases edge"), "horizons": (5, 10, 20), "source_ids": ("pairs-trading", "change-point")},
    {"mechanism_id": "quality_revision_compounder", "thesis": "quality plus positive revisions may persist when valuation is not extreme", "primitive_ids": ("factor_quality", "estimate_revision", "valuation_state", "relative_strength"), "regime_guards": ("require point-in-time filings", "abstain on stale revisions"), "failure_conditions": ("cash flow deteriorates", "revisions reverse", "valuation tail dominates"), "horizons": (20, 60), "source_ids": ("alphaforge", "multifactor-timing")},
    {"mechanism_id": "breadth_confirmed_breakout", "thesis": "structure expansion is more credible with participation and cross-sectional confirmation", "primitive_ids": ("trend_strength", "participation", "breadth_state", "relative_strength"), "regime_guards": ("abstain on narrowing breadth", "require volatility-adjusted acceptance"), "failure_conditions": ("failed breakout", "participation collapses"), "horizons": (5, 10, 20), "source_ids": ("alphaforge", "alphaformer")},
    {"mechanism_id": "volatility_regime_transition", "thesis": "change points and volatility term structure can identify expansion or normalization hypotheses", "primitive_ids": ("volatility_state", "change_point_probability", "options_skew", "cross_asset_stress"), "regime_guards": ("require sequential alpha budget", "abstain on low surface quality"), "failure_conditions": ("break probability decays", "surface contradicts realized state"), "horizons": (2, 5, 10), "source_ids": ("change-point", "confidence-sequences")},
    {"mechanism_id": "state_conditioned_factor_timing", "thesis": "factor evidence may vary with jointly observed macro and market states", "primitive_ids": ("factor_quality", "valuation_state", "momentum_state", "cross_asset_stress", "breadth_state"), "regime_guards": ("require regime familiarity", "cap confidence by weakest factor"), "failure_conditions": ("factor crowding reverses", "regime classifier drifts"), "horizons": (20, 60), "source_ids": ("multifactor-timing", "adaptive-conformal-risk-control")},
    {"mechanism_id": "symbolic_factor_discovery", "thesis": "small interpretable expressions may expose transferable conditional relationships", "primitive_ids": ("trend_strength", "momentum_state", "participation", "factor_quality", "valuation_state"), "regime_guards": ("enforce complexity cap", "prune correlated expressions"), "failure_conditions": ("expression is unstable across eras", "null baselines explain gain"), "horizons": (10, 20), "source_ids": ("alphaforge", "alphaformer", "autoalpha")},
    {"mechanism_id": "risk_controlled_abstention", "thesis": "research quality improves when uncertainty and calibration risk explicitly suppress weak theses", "primitive_ids": ("calibration_risk", "change_point_probability", "liquidity_state", "cross_asset_stress"), "regime_guards": ("abstain above conformal risk threshold", "expand evidence inside confidence sequence"), "failure_conditions": ("coverage assumptions fail", "calibration sample is insufficient"), "horizons": (5, 10, 20), "source_ids": ("conformal-risk-control", "adaptive-conformal-risk-control", "confidence-sequences")},
)


def primitive_by_id(primitive_id: str) -> PrimitiveSpec:
    matches = tuple(record for record in PRIMITIVES if record["primitive_id"] == primitive_id)
    if len(matches) != 1:
        raise ValueError(f"strategy primitive must resolve exactly once: primitive_id={primitive_id}, matches={len(matches)}")
    return matches[0]
