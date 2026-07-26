"""Dopey contract ranker: deterministic contract ranking (research stub, no network).

DOPEY-native stub. Ranks contracts by a configurable blend of liquidity and edge-relevance.
"""
from __future__ import annotations

from .ontology import OptionChain, OptionContract
from .liquidity_engine import liquidity_score


def rank_contracts(chain: OptionChain, edge_score: dict[str, float] | None = None,
                   w_liq: float = 0.7, w_edge: float = 0.3) -> list[tuple[str, float]]:
    edge_score = edge_score or {}
    rows = []
    for c in chain.contracts:
        liq = liquidity_score(c)
        edge = edge_score.get(c.symbol, 0.0)
        rows.append((c.symbol, round(w_liq * liq + w_edge * edge, 6)))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows
