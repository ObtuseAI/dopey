"""Dopey macro analysis layer: deterministic macro-context scoring.

DEFERRED (real data): rates/yields, CPI/PPI/FOMC calendar, dollar strength, VIX/VVIX feeds,
futures/overnight pressure — all placeholder scores fed from deterministic fixture contexts.
No network. Implements: risk-on/off classification, volatility-regime, event-risk shock
handling (penalize), sector rotation, breadth, liquidity regime.
"""
from __future__ import annotations

from .models import MacroContext


def score_macro(ctx: MacroContext) -> float:
    """Aggregate macro layer score in 0..1. Higher = macro-favorable for risk assets / convexity.

    Penalize high event risk and low liquidity regime; reward risk-on + breadth.
    """
    s = (
        0.30 * ctx.risk_on_score
        + 0.20 * ctx.breadth_score
        + 0.15 * ctx.sector_rotation_score
        + 0.15 * ctx.liquidity_regime_score
        + 0.10 * ctx.volatility_regime_score
        - 0.20 * ctx.event_risk_score
    )
    return round(max(0.0, min(1.0, s)), 6)


def is_risk_on(ctx: MacroContext) -> bool:
    """Naive risk-on classification: risk_on_score high AND event_risk low."""
    return ctx.risk_on_score >= 0.6 and ctx.event_risk_score <= 0.4
