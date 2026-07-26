"""Dopey spread builder: deterministic defined-risk spread construction (research stub).

DOPEY-native stub. Builds simple defined-risk vertical spreads from a chain. NEVER builds
undefined-risk structures. Returns legs only; no order placement, no live execution.
"""
from __future__ import annotations

from .ontology import OptionChain, OptionContract


def vertical_spread(long_leg: OptionContract, short_leg: OptionContract, quantity: int = 1) -> dict:
    """Return a defined-risk vertical spread intent dict."""
    net = (long_leg.bid - short_leg.ask) * quantity if long_leg.bid > 0 else 0.0
    max_loss = abs(long_leg.strike - short_leg.strike) * quantity + net
    return {
        "structure": "vertical",
        "defined_risk": True,
        "long": long_leg.to_dict(),
        "short": short_leg.to_dict(),
        "quantity": quantity,
        "net_credit": round(net, 6),
        "max_loss_estimate": round(max_loss, 6),
    }


def pick_vertical(chain: OptionChain, option_type: str, long_strike: float, short_strike: float) -> dict | None:
    longs = [c for c in chain.contracts if c.option_type == option_type and c.strike == long_strike]
    shorts = [c for c in chain.contracts if c.option_type == option_type and c.strike == short_strike]
    if not longs or not shorts:
        return None
    return vertical_spread(longs[0], shorts[0])
