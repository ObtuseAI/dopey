"""Options PnL reconciliation and a closing-line-value process analogue."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Literal


@dataclass(frozen=True, slots=True)
class PnLAttribution:
    total_pnl: float
    underlying_direction: float
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility_change: float
    realized_volatility: float
    skew: float
    term_structure: float
    vanna: float
    charm: float
    vomma: float
    correlation: float
    carry: float
    financing: float
    dividends: float
    borrow: float
    spread: float
    commissions: float
    slippage: float
    market_impact: float
    exercise: float
    assignment: float
    residual: float


@dataclass(frozen=True, slots=True)
class PnLReconciliation:
    explained_pnl: float
    unexplained_difference: float
    reconciled: bool


@dataclass(frozen=True, slots=True)
class ClosingLineValueInputs:
    price_direction: Literal["debit", "credit"]
    executed_price: float
    later_consensus_fair_value: float
    underlying_move_adjustment: float
    time_decay_adjustment: float
    surface_move_adjustment: float
    event_resolution_adjustment: float
    rates_adjustment: float
    dividends_adjustment: float
    borrow_adjustment: float
    model_uncertainty_haircut: float


@dataclass(frozen=True, slots=True)
class ClosingLineValueResult:
    entry_equivalent_consensus_value: float
    process_price_edge: float
    favorable: bool


def reconcile_pnl(attribution: PnLAttribution, tolerance: float) -> PnLReconciliation:
    values = tuple(float(getattr(attribution, field.name)) for field in fields(attribution))
    if any(not math.isfinite(value) for value in values):
        raise ValueError("PnL attribution requires finite components")
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("PnL reconciliation tolerance must be finite and nonnegative")
    explained = sum(values[1:])
    difference = attribution.total_pnl - explained
    return PnLReconciliation(explained, difference, abs(difference) <= tolerance)


def calculate_closing_line_value(inputs: ClosingLineValueInputs) -> ClosingLineValueResult:
    values = tuple(float(getattr(inputs, field.name)) for field in fields(inputs) if field.name != "price_direction")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("closing-line-value inputs must be finite")
    if inputs.executed_price < 0.0 or inputs.later_consensus_fair_value < 0.0:
        raise ValueError("closing-line-value prices cannot be negative")
    if inputs.model_uncertainty_haircut < 0.0:
        raise ValueError("model uncertainty haircut cannot be negative")
    market_move_adjustments = (
        inputs.underlying_move_adjustment
        + inputs.time_decay_adjustment
        + inputs.surface_move_adjustment
        + inputs.event_resolution_adjustment
        + inputs.rates_adjustment
        + inputs.dividends_adjustment
        + inputs.borrow_adjustment
    )
    entry_equivalent = inputs.later_consensus_fair_value - market_move_adjustments
    raw_edge = (
        entry_equivalent - inputs.executed_price
        if inputs.price_direction == "debit"
        else inputs.executed_price - entry_equivalent
    )
    process_edge = raw_edge - inputs.model_uncertainty_haircut
    return ClosingLineValueResult(entry_equivalent, process_edge, process_edge > 0.0)
