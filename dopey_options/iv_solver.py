"""Implied-volatility solver for deterministic offline DOPEY option pricing."""
from __future__ import annotations

import math
from typing import Any

from .option_pricing_models import (
    ImpliedVolResult,
    intrinsic_value,
    option_price_upper_bound,
    option_pricing_input,
    price_european_option,
    validate_pricing_source_tier,
)


IV_SOLVER_VERSION = "dopey-model-repricer-iv-solver-v1"
SOLVER_STATUSES: frozenset[str] = frozenset({
    "solved",
    "fallback_solved",
    "invalid_input",
    "no_solution",
    "max_iterations",
})
MIN_IV = 0.000001
MAX_IV = 5.0


def solve_implied_volatility(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    valuation_date: str,
    underlying_price: float,
    option_price: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    pricing_source_tier: str,
    real_option_chain_present: bool,
    initial_volatility: float,
    tolerance: float,
    max_iterations: int,
) -> ImpliedVolResult:
    invalid_reasons = _invalid_input_reasons(
        option_type,
        strike,
        underlying_price,
        option_price,
        time_to_expiry_years,
        pricing_source_tier,
        real_option_chain_present,
        max_iterations,
        tolerance,
    )
    if invalid_reasons:
        return _result(
            symbol,
            option_type,
            strike,
            expiry,
            valuation_date,
            underlying_price,
            option_price,
            time_to_expiry_years,
            risk_free_rate,
            dividend_yield,
            0.0,
            "invalid_input",
            0,
            0.0,
            "input_validation",
            invalid_reasons,
            _safe_tier(pricing_source_tier),
        )
    tier = validate_pricing_source_tier(pricing_source_tier, real_option_chain_present)
    floor = intrinsic_value(option_type, underlying_price, strike)
    if time_to_expiry_years == 0.0:
        if abs(option_price - floor) <= tolerance:
            return _result(
                symbol,
                option_type,
                strike,
                expiry,
                valuation_date,
                underlying_price,
                option_price,
                time_to_expiry_years,
                risk_free_rate,
                dividend_yield,
                0.0,
                "solved",
                0,
                0.0,
                "expiry_intrinsic",
                ["expiry_intrinsic"],
                tier,
            )
        return _result(
            symbol,
            option_type,
            strike,
            expiry,
            valuation_date,
            underlying_price,
            option_price,
            time_to_expiry_years,
            risk_free_rate,
            dividend_yield,
            0.0,
            "no_solution",
            0,
            round(option_price - floor, 10),
            "expiry_intrinsic",
            ["expiry_has_no_extrinsic_solution"],
            tier,
        )
    newton = _newton_solve(
        symbol,
        option_type,
        strike,
        expiry,
        valuation_date,
        underlying_price,
        option_price,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        tier,
        initial_volatility,
        tolerance,
        max_iterations,
    )
    if newton["status"] == "solved":
        return _result(
            symbol,
            option_type,
            strike,
            expiry,
            valuation_date,
            underlying_price,
            option_price,
            time_to_expiry_years,
            risk_free_rate,
            dividend_yield,
            newton["iv"],
            "solved",
            newton["iterations"],
            newton["price_error"],
            "newton_raphson",
            newton["reason_codes"],
            tier,
        )
    bisection = _bisection_solve(
        symbol,
        option_type,
        strike,
        expiry,
        valuation_date,
        underlying_price,
        option_price,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        tier,
        tolerance,
        max_iterations,
    )
    status = "fallback_solved" if bisection["status"] == "solved" else bisection["status"]
    reason_codes = sorted(set(newton["reason_codes"] + bisection["reason_codes"]))
    return _result(
        symbol,
        option_type,
        strike,
        expiry,
        valuation_date,
        underlying_price,
        option_price,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        bisection["iv"],
        status,
        newton["iterations"] + bisection["iterations"],
        bisection["price_error"],
        "bisection_fallback",
        reason_codes,
        tier,
    )


def _newton_solve(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    valuation_date: str,
    underlying_price: float,
    option_price: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    pricing_source_tier: str,
    initial_volatility: float,
    tolerance: float,
    max_iterations: int,
) -> dict[str, Any]:
    sigma = min(MAX_IV, max(MIN_IV, initial_volatility))
    reason_codes: list[str] = []
    last_error = 0.0
    for iteration in range(1, max_iterations + 1):
        priced = _price(
            symbol,
            option_type,
            strike,
            expiry,
            valuation_date,
            underlying_price,
            time_to_expiry_years,
            risk_free_rate,
            dividend_yield,
            sigma,
            pricing_source_tier,
        )
        last_error = round(priced.model_price - option_price, 10)
        if abs(last_error) <= tolerance:
            return {
                "status": "solved",
                "iv": round(sigma, 10),
                "iterations": iteration,
                "price_error": last_error,
                "reason_codes": ["newton_converged"],
            }
        derivative = priced.vega * 100.0
        if derivative <= 0.00000001:
            reason_codes.append("newton_vega_too_small")
            break
        next_sigma = sigma - (last_error / derivative)
        if not math.isfinite(next_sigma) or next_sigma <= MIN_IV or next_sigma >= MAX_IV:
            reason_codes.append("newton_step_out_of_bounds")
            break
        sigma = next_sigma
    if not reason_codes:
        reason_codes.append("newton_not_converged")
    return {
        "status": "max_iterations",
        "iv": round(sigma, 10),
        "iterations": max_iterations,
        "price_error": last_error,
        "reason_codes": reason_codes,
    }


def _bisection_solve(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    valuation_date: str,
    underlying_price: float,
    option_price: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    pricing_source_tier: str,
    tolerance: float,
    max_iterations: int,
) -> dict[str, Any]:
    low = MIN_IV
    high = MAX_IV
    low_price = _price(
        symbol,
        option_type,
        strike,
        expiry,
        valuation_date,
        underlying_price,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        low,
        pricing_source_tier,
    ).model_price
    high_price = _price(
        symbol,
        option_type,
        strike,
        expiry,
        valuation_date,
        underlying_price,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        high,
        pricing_source_tier,
    ).model_price
    if option_price < low_price - tolerance or option_price > high_price + tolerance:
        return {
            "status": "no_solution",
            "iv": 0.0,
            "iterations": 0,
            "price_error": round(min(abs(option_price - low_price), abs(option_price - high_price)), 10),
            "reason_codes": ["bisection_target_outside_price_range"],
        }
    last_mid = low
    last_error = low_price - option_price
    for iteration in range(1, max_iterations + 1):
        midpoint = (low + high) / 2.0
        midpoint_price = _price(
            symbol,
            option_type,
            strike,
            expiry,
            valuation_date,
            underlying_price,
            time_to_expiry_years,
            risk_free_rate,
            dividend_yield,
            midpoint,
            pricing_source_tier,
        ).model_price
        last_mid = midpoint
        last_error = round(midpoint_price - option_price, 10)
        if abs(last_error) <= tolerance:
            return {
                "status": "solved",
                "iv": round(midpoint, 10),
                "iterations": iteration,
                "price_error": last_error,
                "reason_codes": ["bisection_converged"],
            }
        if midpoint_price < option_price:
            low = midpoint
        else:
            high = midpoint
    return {
        "status": "max_iterations",
        "iv": round(last_mid, 10),
        "iterations": max_iterations,
        "price_error": last_error,
        "reason_codes": ["bisection_not_converged"],
    }


def _price(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    valuation_date: str,
    underlying_price: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    implied_vol: float,
    pricing_source_tier: str,
):
    return price_european_option(option_pricing_input(
        symbol,
        option_type,
        strike,
        expiry,
        valuation_date,
        underlying_price,
        time_to_expiry_years,
        implied_vol,
        risk_free_rate,
        dividend_yield,
        pricing_source_tier,
    ))


def _invalid_input_reasons(
    option_type: str,
    strike: float,
    underlying_price: float,
    option_price: float,
    time_to_expiry_years: float,
    pricing_source_tier: str,
    real_option_chain_present: bool,
    max_iterations: int,
    tolerance: float,
) -> list[str]:
    reasons: list[str] = []
    if option_type not in {"call", "put"}:
        reasons.append("unsupported_option_type")
    if underlying_price <= 0.0:
        reasons.append("nonpositive_underlying")
    if strike <= 0.0:
        reasons.append("nonpositive_strike")
    if time_to_expiry_years < 0.0:
        reasons.append("negative_time_to_expiry")
    if option_price < 0.0:
        reasons.append("negative_option_price")
    if max_iterations <= 0:
        reasons.append("nonpositive_max_iterations")
    if tolerance <= 0.0:
        reasons.append("nonpositive_tolerance")
    if pricing_source_tier not in {"fixture_only", "model_priced", "quote_priced"}:
        reasons.append("unsupported_pricing_source_tier")
    if pricing_source_tier == "quote_priced" and not real_option_chain_present:
        reasons.append("quote_priced_requires_real_option_chain")
    if not reasons and option_price < intrinsic_value(option_type, underlying_price, strike) - tolerance:
        reasons.append("option_price_below_intrinsic_floor")
    if not reasons and option_price > option_price_upper_bound(option_type, underlying_price, strike) + tolerance:
        reasons.append("option_price_above_reasonable_upper_bound")
    return reasons


def _result(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    valuation_date: str,
    underlying_price: float,
    option_price: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    iv: float,
    solver_status: str,
    iterations: int,
    price_error: float,
    method_used: str,
    reason_codes: list[str],
    pricing_source_tier: str,
) -> ImpliedVolResult:
    if solver_status not in SOLVER_STATUSES:
        raise ValueError(f"unsupported solver_status: {solver_status}")
    record = ImpliedVolResult(
        symbol=symbol,
        option_type=option_type,
        strike=round(float(strike), 6),
        expiry=expiry,
        valuation_date=valuation_date,
        underlying_price=round(float(underlying_price), 6),
        option_price=round(float(option_price), 6),
        time_to_expiry_years=round(float(time_to_expiry_years), 10),
        risk_free_rate=round(float(risk_free_rate), 10),
        dividend_yield=round(float(dividend_yield), 10),
        iv=round(float(iv), 10),
        solver_status=solver_status,
        iterations=int(iterations),
        price_error=round(float(price_error), 10),
        method_used=method_used,
        reason_codes=reason_codes,
        pricing_source_tier=pricing_source_tier,
        paper_only=True,
        live_blocked=True,
        result_hash="",
    )
    return ImpliedVolResult(**record.to_dict())


def _safe_tier(pricing_source_tier: str) -> str:
    if pricing_source_tier in {"fixture_only", "model_priced"}:
        return pricing_source_tier
    return "fixture_only"
