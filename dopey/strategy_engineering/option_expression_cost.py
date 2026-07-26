"""Does an underlying directional signal survive expression as a long option?

The cross-lane convergence engine works on UNDERLYING excess-over-drift, but
DOPEY trades long premium (calls/puts), which pays a steep tax the underlying
does not: half-spread + slippage on both sides, commission, and - the big one -
theta decay over the holding window. A correct directional read can still lose
as an option if the move is too small to clear that tax. (The r/ai_trading
audit's #13 warns of exactly this.)

This prices an ATM option with the real deterministic kernel and the documented
cost stack to answer two honest questions per corroborated family:
  1. What favorable underlying move over the horizon does a long option need
     just to BREAK EVEN net of costs and decay?
  2. Is the family's corroborated excess anywhere near that breakeven?

Deterministic, measure-only. It never sizes or promotes; it annotates a
research finding with the option-cost reality so the underlying signal is never
mistaken for a tradeable options edge.
"""
from __future__ import annotations

import math
from typing import Any

from dopey_backtest.real_history_honest_backtester import (
    COMMISSION_PER_SIDE_PREMIUM_UNITS,
    COST_PCT_PER_SIDE,
)
from dopey_options.option_pricing_models import option_pricing_input, price_european_option

OPTION_COST_VERSION = "dopey-option-expression-cost-v1"
DEFAULT_IV = 0.30            # representative ATM implied vol
DEFAULT_DTE_DAYS = 30
DEFAULT_HORIZON_DAYS = 5
DEFAULT_RISK_FREE_RATE = 0.037
TRADING_DAYS_PER_YEAR = 252.0


def _mid(spot: float, strike: float, iv: float, dte_days: int, rfr: float, option_type: str) -> float:
    result = price_european_option(
        option_pricing_input(
            symbol="REPR",
            option_type=option_type,
            strike=strike,
            expiry="",
            valuation_date="",
            underlying_price=spot,
            time_to_expiry_years=max(dte_days, 0) / 365.0,
            implied_vol=iv,
            risk_free_rate=rfr,
            dividend_yield=0.0,
            pricing_source_tier="model_priced",
        )
    )
    return float(result.model_price)


def net_return_for_move(
    underlying_move: float,
    spot: float = 100.0,
    iv: float = DEFAULT_IV,
    dte_days: int = DEFAULT_DTE_DAYS,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    option_type: str = "call",
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    strike: float | None = None,
) -> float:
    """Net-of-cost return of a long option after a favorable underlying move.

    Entry pays up (mid + half-spread + slippage + commission); exit receives
    down (mid - half-spread - slippage - commission, floored at 0); the spot
    moves by underlying_move and the clock advances horizon_days. strike
    defaults to ATM; the expression selector sweeps other release angles.
    """
    strike = spot if strike is None else float(strike)
    entry_mid = _mid(spot, strike, iv, dte_days, risk_free_rate, option_type)
    if entry_mid <= 0.0:
        return 0.0
    entry_fill = entry_mid * (1.0 + COST_PCT_PER_SIDE) + COMMISSION_PER_SIDE_PREMIUM_UNITS
    exit_spot = spot * (1.0 + underlying_move)
    exit_mid = _mid(exit_spot, strike, iv, dte_days - horizon_days, risk_free_rate, option_type)
    exit_fill = max(exit_mid * (1.0 - COST_PCT_PER_SIDE) - COMMISSION_PER_SIDE_PREMIUM_UNITS, 0.0)
    return exit_fill / entry_fill - 1.0


def breakeven_move(
    spot: float = 100.0,
    iv: float = DEFAULT_IV,
    dte_days: int = DEFAULT_DTE_DAYS,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    option_type: str = "call",
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    strike: float | None = None,
) -> float:
    """Favorable underlying move (fraction) where net-of-cost option return = 0.

    Monotone in the move for a long option, so a bounded bisection converges.
    """
    lo, hi = 0.0, 0.50  # 0% .. 50% favorable move brackets the breakeven
    if net_return_for_move(hi, spot, iv, dte_days, horizon_days, option_type, risk_free_rate, strike) < 0.0:
        return math.inf  # even a 50% move cannot clear the tax (degenerate)
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if net_return_for_move(mid, spot, iv, dte_days, horizon_days, option_type, risk_free_rate, strike) >= 0.0:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2.0, 6)


def survives_option_costs(
    underlying_excess: float,
    iv: float = DEFAULT_IV,
    dte_days: int = DEFAULT_DTE_DAYS,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> dict[str, Any]:
    """Annotate an underlying edge with the long-option cost verdict.

    The excess is treated as the favorable move a long option would capture in
    the signal's direction. Compares it to the net-of-cost breakeven move.
    """
    magnitude = abs(float(underlying_excess))
    breakeven = breakeven_move(iv=iv, dte_days=dte_days, horizon_days=horizon_days)
    net_at_excess = net_return_for_move(
        magnitude, iv=iv, dte_days=dte_days, horizon_days=horizon_days
    )
    return {
        "option_cost_version": OPTION_COST_VERSION,
        "underlying_excess_magnitude": round(magnitude, 6),
        "breakeven_underlying_move": breakeven,
        "net_long_option_return_at_excess": round(net_at_excess, 6),
        "survives_long_option_costs": bool(net_at_excess > 0.0),
        "assumptions": {
            "implied_vol": iv,
            "dte_days": dte_days,
            "horizon_days": horizon_days,
            "cost_pct_per_side": COST_PCT_PER_SIDE,
            "commission_premium_units_per_side": COMMISSION_PER_SIDE_PREMIUM_UNITS,
        },
        "note": (
            "a long ATM option must clear half-spread + slippage + commission on "
            "both sides AND theta over the horizon; a correct-but-small underlying "
            "edge routinely fails this"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }
