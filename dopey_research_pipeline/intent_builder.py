"""Dopey pipeline execution-intent builder: converts an approved paper candidate into an
ExecutionIntent. MUST set live_allowed=false, paper broker preference, defined-risk structure,
max_loss, target_profit, invalidation rule, proof score, aggression tier.

Validates that no live order can be produced by this builder.
"""
from __future__ import annotations

from dopey_execution.execution_intent import ExecutionIntent
from dopey_strategy_lab.strategy_genome import StrategyGenome


def build_paper_intent(genome: StrategyGenome, underlying_symbol: str, long_leg: dict, short_leg: dict,
                       promotion_decision: dict, proof: dict, quantity: int = 1) -> ExecutionIntent:
    """Build a paper ExecutionIntent for a long-call vertical spread (defined-risk).

    long_leg/short_leg are candidate dicts from the pipeline ranker. The intent is ALWAYS
    paper-only and live_allowed=False by construction."""
    params = genome.parameters
    strike_width = abs(long_leg.get("strike", 0) - short_leg.get("strike", 0))
    long_mid = long_leg.get("mid", 0.0)
    short_mid = short_leg.get("mid", 0.0)
    net_debit = round(max(0.0, long_mid - short_mid), 6)
    max_loss = round(net_debit * quantity, 6)
    # target: the spread width minus the net debit, times quantity (defined-risk reward cap)
    target_profit = round(max(0.0, strike_width - net_debit) * quantity, 6)
    aggression_score = promotion_decision.get("aggression_score", 0.0)

    intent = ExecutionIntent(
        intent_id=f"paper-intent-{genome.genome_id}",
        symbol=underlying_symbol,
        structure=genome.parameters.get("structure", "vertical"),
        legs=[
            {"side": "buy", "symbol": long_leg["symbol"], "strike": long_leg["strike"],
             "expiry": long_leg["expiry"], "option_type": long_leg["option_type"], "mid": long_mid},
            {"side": "sell", "symbol": short_leg["symbol"], "strike": short_leg["strike"],
             "expiry": short_leg["expiry"], "option_type": short_leg["option_type"], "mid": short_mid},
        ],
        quantity=quantity,
        defined_risk=True,
        live_allowed=False,
        paper=True,
        broker_preference="paper",
        strategy_id=genome.genome_id,
        max_loss=max_loss,
        target_profit=target_profit,
        invalidation_rule=params.get("invalidation_rule", ""),
        proof_score=proof.get("proof_strength", 0.0),
        aggression_tier=promotion_decision.get("decision", "rejected"),
    )
    return intent
