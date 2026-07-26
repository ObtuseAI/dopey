"""Dopey technical analysis layer: deterministic technical-context scoring.

DEFERRED (real data): live OHLCV feed, intraday pattern state. No network. Implements: trend
structure, momentum, realized volatility, range compression/expansion, breakout/fakeout
detection, support/resistance zones, moving-average regime, volume confirmation, gap behavior.
"""
from __future__ import annotations

from .models import TechnicalContext


def score_technical(ctx: TechnicalContext) -> float:
    """Aggregate technical layer score in 0..1. Higher = clearer technical edge."""
    s = (
        0.20 * ctx.trend_score
        + 0.15 * ctx.momentum_score
        + 0.15 * ctx.support_resistance_score
        + 0.10 * ctx.volume_confirmation_score
        + 0.10 * ctx.realized_volatility_score
        + 0.15 * ctx.breakout_score
        - 0.15 * ctx.fakeout_risk_score
    )
    return round(max(0.0, min(1.0, s)), 6)
