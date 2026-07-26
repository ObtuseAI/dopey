"""Dopey IV surface engine: deterministic IV surface sketch (research stub, no network).

DOPEY-native stub. Builds a simple IV surface grid (strike x expiry) from a chain for research
visualization. No external data; no live pricing.
"""
from __future__ import annotations

from .ontology import OptionChain


def iv_grid(chain: OptionChain) -> dict:
    """Return {expiry: {strike: iv}} grid from chain contracts."""
    grid: dict[str, dict[float, float]] = {}
    for c in chain.contracts:
        grid.setdefault(c.expiry, {})[c.strike] = c.iv
    return grid


def moneyness_rank(chain: OptionChain, spot: float) -> list[tuple[str, float, float]]:
    """Return (symbol, moneyness, iv) sorted by abs moneyness from ATM."""
    rows = []
    for c in chain.contracts:
        rows.append((c.symbol, round(c.strike / spot, 6), c.iv))
    rows.sort(key=lambda r: abs(r[1] - 1.0))
    return rows
