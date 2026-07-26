"""Dopey greeks engine: deterministic Black-Scholes greeks (research-only, no network).

DOPEY-native stub. Computes delta/gamma/theta/vega/rho for an option contract using a
closed-form Black-Scholes approximation. Pure math; no external data calls. Used only to
enrich research ontology; not for live pricing.
"""
from __future__ import annotations

import math

from .ontology import OptionContract


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def d1d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    if T <= 0 or sigma <= 0:
        return 0.0, 0.0
    denom = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / denom
    return d1, d1 - denom


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> dict:
    """Return {price, delta, gamma, theta, vega, rho} for a European option."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(0.0, (S - K) if option_type == "call" else (K - S))
        return {"price": intrinsic, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    d1, d2 = d1d2(S, K, T, r, sigma)
    pdf = _norm_pdf(d1)
    if option_type == "call":
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        rho = K * T * math.exp(-r * T) * _norm_cdf(d2) / 100.0
        theta = (-(S * pdf * sigma) / (2.0 * math.sqrt(T)) - r * K * math.exp(-r * T) * _norm_cdf(d2)) / 365.0
    else:
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2) / 100.0
        theta = (-(S * pdf * sigma) / (2.0 * math.sqrt(T)) + r * K * math.exp(-r * T) * _norm_cdf(-d2)) / 365.0
    gamma = pdf / (S * sigma * math.sqrt(T))
    vega = S * math.sqrt(T) * pdf / 100.0
    return {
        "price": round(price, 6),
        "delta": round(delta, 6),
        "gamma": round(gamma, 6),
        "theta": round(theta, 6),
        "vega": round(vega, 6),
        "rho": round(rho, 6),
    }


def implied_vol_bisection(
    price: float, S: float, K: float, T: float, r: float, option_type: str,
    lo: float = 0.005, hi: float = 5.0, tol: float = 1e-6, max_iter: int = 80,
) -> float | None:
    """Invert Black-Scholes for IV by bisection. Deterministic, dependency-free.
    Returns None when the price sits outside the arbitrage-consistent band
    (below intrinsic/discount floor or above the S upper bound)."""
    if price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    floor = bs_greeks(S, K, T, r, lo, option_type)["price"]
    ceiling = bs_greeks(S, K, T, r, hi, option_type)["price"]
    if price <= floor or price >= ceiling:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        value = bs_greeks(S, K, T, r, mid, option_type)["price"]
        if abs(value - price) < tol:
            return round(mid, 8)
        if value < price:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 8)


def enrich_contract(contract: OptionContract, S: float, T_years: float, r: float = 0.04) -> OptionContract:
    """Mutate-in-place enrich of a contract's greeks using its IV. Returns the contract."""
    g = bs_greeks(S, contract.strike, T_years, r, contract.iv, contract.option_type)
    contract.delta = g["delta"]
    contract.gamma = g["gamma"]
    contract.theta = g["theta"]
    contract.vega = g["vega"]
    contract.rho = g["rho"]
    return contract
