"""Black-Scholes proxy pricing and Greeks for paper-only long premium candidates."""
from __future__ import annotations

import math


def price_long_option_proxy(spot: float, strike: float, dte: int, volatility: float, option_side: str) -> dict:
    time_years = max(dte, 1) / 365.0
    rate = 0.04
    sigma = max(volatility, 0.08)
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive for model-priced option proxy")
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * time_years) / (sigma * math.sqrt(time_years))
    d2 = d1 - sigma * math.sqrt(time_years)
    if option_side == "call":
        price = spot * _norm_cdf(d1) - strike * math.exp(-rate * time_years) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
    elif option_side == "put":
        price = strike * math.exp(-rate * time_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
    else:
        raise ValueError(f"unsupported option side: {option_side}")
    theta_proxy = max(price * 0.015, 0.01)
    gamma_proxy = math.exp(-0.5 * d1 * d1) / (spot * sigma * math.sqrt(2.0 * math.pi * time_years))
    return {
        "model_price": round(max(price, 0.05), 4),
        "delta_proxy": round(delta, 4),
        "gamma_proxy": round(gamma_proxy, 6),
        "theta_decay_stress": round(theta_proxy * min(dte, 30), 4),
        "iv_shock_stress": round(max(price, 0.05) * 0.22, 4),
    }


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))

