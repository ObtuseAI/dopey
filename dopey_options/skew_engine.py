"""Dopey skew engine: deterministic skew/risk-reversal measures (research stub, no network).

DOPEY-native stub. Computes simple put/call skew measures for research. No external data.
"""
from __future__ import annotations

from .ontology import OptionChain


def skew_slope(chain: OptionChain, otm_threshold: float = 0.10) -> dict:
    """Return OTM put IV - OTM call IV as a naive skew proxy across expiries."""
    by_exp: dict[str, dict[str, list[float]]] = {}
    for c in chain.contracts:
        by_exp.setdefault(c.expiry, {"call": [], "put": []})[c.option_type].append(c.iv)
    out = {}
    for exp, ivs in by_exp.items():
        call_iv = sum(ivs["call"]) / len(ivs["call"]) if ivs["call"] else 0.0
        put_iv = sum(ivs["put"]) / len(ivs["put"]) if ivs["put"] else 0.0
        out[exp] = round(put_iv - call_iv, 6)
    return out
