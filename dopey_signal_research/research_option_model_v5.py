"""V5 option model (Workstream I).

Model-priced only. No live quotes. Long-call / long-put / no-trade only.
No short options, no spreads.

Pricing model: simplified Black-Scholes approximation using public
OHLCV-derived inputs (entry spot, hold_window, IV estimate from
volatility feature, DTE, moneyness).

The model is deterministic given inputs and is used to compute per-trade
PnL in the V5 path simulator.
"""
from __future__ import annotations

import math


__all__ = [
    "model_price_option",
    "compute_trade_pnl",
]


SQRT_2 = math.sqrt(2.0)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF (Abramowitz & Stegun approximation)."""
    if x < -8.0:
        return 0.0
    if x > 8.0:
        return 1.0
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    d = 0.3989423 * math.exp(-x * x / 2.0)
    p = d * t * (
        0.3193815
        + t * (-0.3565638 + t * (1.781478 + t * (-1.8212560 + t * 1.3302744)))
    )
    return 1.0 - p if x > 0 else p


def model_price_option(
    direction: str,
    spot: float,
    strike: float,
    dte_days: int,
    iv_annual: float,
    risk_free_rate: float = 0.05,
) -> float:
    """Model-price a long call or long put. Returns option price.

    If direction is no_trade, returns 0.0.
    """
    if direction == "no_trade":
        return 0.0
    if direction not in ("long_call", "long_put"):
        raise ValueError(f"unsupported direction: {direction}")
    if spot <= 0 or strike <= 0 or dte_days <= 0 or iv_annual <= 0:
        return 0.0
    t = dte_days / 365.0
    sigma = iv_annual
    if sigma < 0.05:
        sigma = 0.05
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * sigma * sigma) * t) / (
        sigma * math.sqrt(t)
    )
    d2 = d1 - sigma * math.sqrt(t)
    if direction == "long_call":
        price = spot * _norm_cdf(d1) - strike * math.exp(-risk_free_rate * t) * _norm_cdf(d2)
    else:  # long_put
        price = strike * math.exp(-risk_free_rate * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
    return max(0.0, price)


def compute_trade_pnl(
    direction: str,
    entry_spot: float,
    exit_spot: float,
    strike: float,
    dte_days: int,
    iv_annual: float,
    hold_window_days: int,
) -> float:
    """Compute PnL for a single trade.

    PnL = exit_option_price - entry_option_price.
    For no_trade, returns 0.0.
    Returns 0.0 if entry_spot is non-positive or corrupt.
    """
    if direction == "no_trade":
        return 0.0
    if entry_spot is None or entry_spot <= 0:
        return 0.0
    if entry_spot > 1_000_000.0:
        # Data corruption guard (UVXY-like)
        return 0.0
    if exit_spot is None or exit_spot <= 0:
        return 0.0
    entry_price = model_price_option(
        direction, entry_spot, strike, dte_days, iv_annual
    )
    remaining_dte = max(dte_days - hold_window_days, 0)
    exit_price = model_price_option(
        direction, exit_spot, strike, remaining_dte, iv_annual
    )
    return round(exit_price - entry_price, 6)


def realized_vol_from_features(volatility: float) -> float:
    """Convert the V5 feature vector 'volatility' (0..1) to annual IV.

    Mapping: 0.1 -> 0.15, 0.3 -> 0.25, 0.5 -> 0.35, 0.7 -> 0.50, 1.0 -> 0.80.
    """
    if volatility < 0.0:
        volatility = 0.0
    if volatility > 1.0:
        volatility = 1.0
    return round(0.15 + (volatility ** 1.5) * 0.65, 4)
