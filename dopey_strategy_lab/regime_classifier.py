"""Dopey regime classifier: deterministic regime label (research stub).

DOPEY-native stub. Maps a simple volatility/trend sketch to a regime label.
"""
from __future__ import annotations


def classify_regime(vol: float, trend: float) -> str:
    if vol > 0.30:
        base = "high_vol"
    elif vol < 0.10:
        base = "low_vol"
    else:
        base = "neutral"
    if trend > 0.05:
        return base + "_bull"
    if trend < -0.05:
        return base + "_bear"
    return base
