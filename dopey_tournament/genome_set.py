"""Dopey tournament multi-strategy genome set: 4 deterministic defined-risk families.

All paper-only, all defined-risk where option spreads are involved, no naked undefined-risk
selling, no live eligibility. Each genome carries thesis/entry/exit/contract-selection/
spread-construction/sizing/invalidation/regime/liquidity/event/analysis-layer-preferences
rules + proof-score placeholder + promotion tier.
"""
from __future__ import annotations

from dopey_strategy_lab.strategy_genome import StrategyGenome


PROMOTION_TIER_PAPER = "paper_candidate"
PROMOTION_TIER_RESEARCH = "research_only"


def _genome(genome_id: str, family: str, preferred_regime: str,
            params: dict) -> StrategyGenome:
    params.setdefault("promotion_tier", PROMOTION_TIER_PAPER)
    params.setdefault("structure", "vertical")
    params.setdefault("structure_risk", "defined")
    return StrategyGenome(
        genome_id=genome_id,
        family=family,
        preferred_regime=preferred_regime,
        entry_threshold=0.55,
        max_position_fraction=0.05,
        min_open_interest=5000,
        defined_risk_only=True,
        live_allowed=False,
        version=1,
        parameters=params,
    )


def _directional_convexity() -> StrategyGenome:
    return _genome(
        "genome-directional-convexity-spy-fixture-v1",
        "directional_convexity",
        "low_vol_bull",
        {
            "thesis": "Long SPY_FIXTURE convexity via a call vertical; defined-risk, capped premium outlay.",
            "entry_rule": "aggression gate score >= 0.55 and ranked candidate liquidity >= 0.5",
            "exit_rule": "target_profit reached OR invalidation rule tripped OR expiry within 5 sessions",
            "contract_selection_rule": "long ATM-ish call, short OTM call 1 strike up, same expiry, |delta| in 0.30-0.70",
            "spread_construction_rule": "long-call vertical; width <= 10 strikes; defined-risk",
            "sizing_rule": "1 paper contract per pipeline run; max_position_fraction 0.05 of paper budget",
            "invalidation_rule": "underlying drops more than 4% from entry, OR signal_decay > 0.5, OR overfit_flag",
            "regime_filter": "preferred_regime == low_vol_bull or neutral",
            "liquidity_filter": "open_interest >= 5000 and spread_pct <= 0.10",
            "event_filter": "event_risk_score <= 0.4 (no earnings/FOMC shock window)",
            "analysis_layer_preferences": ["technical", "macro", "microstructure"],
            "proof_score_placeholder": 0.0,
            "direction": "long",
            "structure": "vertical",
        },
    )


def _volatility_expansion() -> StrategyGenome:
    return _genome(
        "genome-volatility-expansion-spy-fixture-v1",
        "volatility_expansion",
        "trend_vol_expansion",
        {
            "thesis": "Long convexity on IV expansion; long call vertical benefits when realized vol rises.",
            "entry_rule": "volatility_regime_score >= 0.6 and technical breakout_score >= 0.5",
            "exit_rule": "IV expansion stalls OR target_profit reached OR invalidation",
            "contract_selection_rule": "long ATM call, short OTM call, same expiry; prefer higher-vega contracts",
            "spread_construction_rule": "long-call vertical; defined-risk; width <= 10 strikes",
            "sizing_rule": "1 paper contract; max_position_fraction 0.04",
            "invalidation_rule": "IV compresses > 20% from entry OR underlying adverse > 4%",
            "regime_filter": "preferred_regime == trend_vol_expansion",
            "liquidity_filter": "open_interest >= 5000 and spread_pct <= 0.12",
            "event_filter": "event_risk_score <= 0.5",
            "analysis_layer_preferences": ["macro", "technical", "pattern"],
            "proof_score_placeholder": 0.0,
            "direction": "long",
            "structure": "vertical",
        },
    )


def _volatility_compression() -> StrategyGenome:
    return _genome(
        "genome-volatility-compression-spy-fixture-v1",
        "volatility_compression",
        "chop_vol_compression",
        {
            "thesis": "Defined-risk long call vertical on a volatility-compression breakout setup; "
                      "buys convexity cheap into a compressed range expecting expansion.",
            "entry_rule": "realized_volatility_score <= 0.4 and breakout_score >= 0.45 and fakeout_risk_score <= 0.5",
            "exit_rule": "range expands beyond upper band OR invalidation OR expiry",
            "contract_selection_rule": "long ATM call, short OTM call; prefer low-IV (cheap) entry",
            "spread_construction_rule": "long-call vertical; defined-risk; width <= 10 strikes",
            "sizing_rule": "1 paper contract; max_position_fraction 0.04",
            "invalidation_rule": "compression fails to expand within 7 sessions OR underlying adverse > 4%",
            "regime_filter": "preferred_regime == chop_vol_compression",
            "liquidity_filter": "open_interest >= 5000 and spread_pct <= 0.12",
            "event_filter": "event_risk_score <= 0.4",
            "analysis_layer_preferences": ["technical", "pattern", "microstructure"],
            "proof_score_placeholder": 0.0,
            "direction": "long",
            "structure": "vertical",
        },
    )


def _short_duration_defined_risk() -> StrategyGenome:
    return _genome(
        "genome-short-duration-defined-risk-spy-fixture-v1",
        "short_duration_defined_risk",
        "neutral",
        {
            "thesis": "Short-DTE defined-risk long call vertical; minimal theta exposure, "
                      "captures near-term directional move with capped premium.",
            "entry_rule": "technical trend_score >= 0.55 and momentum_score >= 0.5",
            "exit_rule": "target_profit reached within 2-4 sessions OR invalidation OR expiry",
            "contract_selection_rule": "short-DTE long ATM call, short OTM call; |delta| in 0.40-0.70",
            "spread_construction_rule": "long-call vertical; defined-risk; narrow width <= 5 strikes",
            "sizing_rule": "1 paper contract; max_position_fraction 0.03",
            "invalidation_rule": "underlying adverse > 3% within 2 sessions OR signal_decay > 0.5",
            "regime_filter": "preferred_regime == neutral or low_vol_bull",
            "liquidity_filter": "open_interest >= 8000 and spread_pct <= 0.08",
            "event_filter": "event_risk_score <= 0.3 (avoid event windows for short DTE)",
            "analysis_layer_preferences": ["technical", "microstructure", "fundamental"],
            "proof_score_placeholder": 0.0,
            "direction": "long",
            "structure": "vertical",
        },
    )


def build_tournament_genomes() -> list[StrategyGenome]:
    """Return the 4 deterministic defined-risk tournament genomes."""
    return [
        _directional_convexity(),
        _volatility_expansion(),
        _volatility_compression(),
        _short_duration_defined_risk(),
    ]


def build_tournament_proof_bundle(strong: bool = True) -> dict:
    """Shared deterministic proof bundle for tournament genomes (paper-only)."""
    if strong:
        return {
            "proof_strength": 0.8,
            "oos_edge": 0.18,
            "walk_forward_consistency": 0.75,
            "paper_fill_quality": 0.85,
            "regime_alignment": True,
            "capital_efficiency": 0.7,
            "family_proof": True,
            "overfit_flag": False,
            "signal_decay": 0.1,
            "drawdown_slope": 0.01,
            "slippage_bps": 4,
        }
    return {
        "proof_strength": 0.2,
        "oos_edge": 0.0,
        "overfit_flag": True,
        "signal_decay": 0.6,
        "drawdown_slope": 0.08,
        "slippage_bps": 20,
    }
