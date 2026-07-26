"""Dopey asymmetric opportunity ranker: deterministic rank by asymmetric payoff (research stub).

DOPEY-native stub. Ranks signal candidates by reward/risk asymmetry using proof-weighted edge.
"""
from __future__ import annotations

from .signal_discovery import SignalCandidate


def rank_opportunities(signals: list[SignalCandidate], liquidity_scores: dict[str, float] | None = None) -> list[tuple[str, float]]:
    liquidity_scores = liquidity_scores or {}
    rows = []
    for s in signals:
        liq = liquidity_scores.get(s.signal_id, 0.5)
        asym = (s.confidence * (1.0 - s.decay_score)) * liq
        rows.append((s.signal_id, round(asym, 6)))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows
