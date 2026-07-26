"""Dopey assignment/exercise engine: deterministic assignment risk estimation (research stub).

DOPEY-native stub. Estimates naive assignment risk for short option legs from moneyness and
delta. No live exercise; no broker calls.
"""
from __future__ import annotations

from .ontology import OptionContract


def assignment_risk(short_leg: OptionContract, spot: float) -> dict:
    intrinsic = max(0.0, (short_leg.strike - spot) if short_leg.option_type == "put" else (spot - short_leg.strike))
    itm = intrinsic > 0
    delta = abs(short_leg.delta)
    prob = min(1.0, delta)
    return {
        "itm": itm,
        "intrinsic": round(intrinsic, 6),
        "delta_abs": round(delta, 6),
        "naive_assignment_prob": round(prob, 6),
    }
