"""Dopey term structure engine: deterministic term-structure sketch (research stub, no network).

DOPEY-native stub. Aggregates ATM IV by expiry for research. No external data.
"""
from __future__ import annotations

from .ontology import OptionChain


def atm_term_structure(chain: OptionChain, spot: float) -> dict:
    """Return {expiry: atm_iv} picking the nearest-strike contract per expiry."""
    by_exp: dict[str, list[tuple[float, float]]] = {}
    for c in chain.contracts:
        by_exp.setdefault(c.expiry, []).append((abs(c.strike - spot), c.iv))
    out = {}
    for exp, rows in by_exp.items():
        rows.sort(key=lambda r: r[0])
        out[exp] = rows[0][1] if rows else 0.0
    return out
