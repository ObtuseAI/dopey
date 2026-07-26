"""Dopey pipeline strategy-genome fixture: a deterministic defined-risk research candidate.

Builds a StrategyGenome for a "directional convexity" family: a long-call vertical spread on
SPY_FIXTURE. Defined-risk by construction (long vertical = capped loss). No naked/undefined-risk
selling. Includes thesis/entry/exit/contract-selection/sizing/invalidation/liquidity/regime
rules + proof-score placeholder + promotion tier.
"""
from __future__ import annotations

from dopey_strategy_lab.strategy_genome import StrategyGenome


PROMOTION_TIER_PAPER = "paper_candidate"
PROMOTION_TIER_RESEARCH = "research_only"


def build_fixture_genome() -> StrategyGenome:
    """Return a deterministic defined-risk StrategyGenome for the paper pipeline."""
    return StrategyGenome(
        genome_id="genome-directional-convexity-spy-fixture-v1",
        family="directional_convexity",
        preferred_regime="low_vol_bull",
        entry_threshold=0.55,
        max_position_fraction=0.05,
        min_open_interest=5000,
        defined_risk_only=True,
        live_allowed=False,
        version=1,
        parameters={
            "thesis": "Long SPY_FIXTURE convexity via a call vertical; defined-risk, capped premium outlay.",
            "entry_rule": "aggression gate score >= 0.55 and ranked candidate liquidity >= 0.5",
            "exit_rule": "target_profit reached OR invalidation rule tripped OR expiry within 5 sessions",
            "contract_selection_rule": "long ATM-ish call, short OTM call 1 strike up, same expiry, |delta| in 0.30-0.70",
            "sizing_rule": "1 paper contract per pipeline run; max_position_fraction 0.05 of paper budget",
            "invalidation_rule": "underlying drops more than 4% from entry, OR signal_decay > 0.5, OR overfit_flag",
            "liquidity_filter": "open_interest >= 5000 and spread_pct <= 0.10",
            "regime_filter": "preferred_regime == low_vol_bull or neutral",
            "proof_score_placeholder": 0.0,
            "promotion_tier": PROMOTION_TIER_PAPER,
            "structure": "vertical",
            "structure_risk": "defined",
        },
    )


def build_fixture_proof_bundle(strong: bool = True) -> dict:
    """Return a deterministic proof bundle for the fixture genome.

    strong=True yields a proof bundle the aggression gate will promote to paper_candidate.
    strong=False yields a weak bundle that the gate will demote.
    """
    if strong:
        return {
            "family": "directional_convexity",
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
        "family": "directional_convexity",
        "proof_strength": 0.2,
        "oos_edge": 0.0,
        "overfit_flag": True,
        "signal_decay": 0.6,
        "drawdown_slope": 0.08,
        "slippage_bps": 20,
    }
