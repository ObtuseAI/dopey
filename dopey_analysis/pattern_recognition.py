"""Dopey pattern recognition layer: deterministic pattern-signal scoring.

DEFERRED (real data): large ML pattern recognition model. No network. Implements: volatility
patterns, price-action patterns, options-chain anomalies, IV skew/term-structure patterns,
unusual volume/OI patterns, regime-transition patterns, failed-breakout patterns,
continuation/reversal patterns, strategy outcome patterns, recurring failure-mode patterns.
"""
from __future__ import annotations

from .models import PatternSignal


def score_patterns(patterns: list[PatternSignal]) -> float:
    """Aggregate pattern layer score in 0..1 from a list of PatternSignals.

    Rewards high-confidence aligned patterns; penalizes failure_mode-bearing signals.
    """
    if not patterns:
        return 0.0
    total = 0.0
    for p in patterns:
        base = p.confidence
        if p.failure_mode:
            base *= 0.5  # a flagged failure mode halves the contribution
        total += base
    return round(max(0.0, min(1.0, total / len(patterns))), 6)


def dominant_direction(patterns: list[PatternSignal]) -> str:
    """Return the dominant directional bias across patterns (long/short/neutral)."""
    if not patterns:
        return "neutral"
    longs = sum(1 for p in patterns if p.directional_bias == "long")
    shorts = sum(1 for p in patterns if p.directional_bias == "short")
    if longs > shorts:
        return "long"
    if shorts > longs:
        return "short"
    return "neutral"
