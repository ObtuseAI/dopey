"""Strategy-aware option value projection over stock-price and time scenarios."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Final

from dopey.protocols.identity import canonical_hash
from dopey_options.option_pricing_models import option_pricing_input, price_european_option


OPTIONS_VALUE_PROJECTOR_VERSION: Final[str] = "dopey-options-value-projector-v1"
MAX_CONTRACT_DTE: Final[int] = 180
MAX_SPREAD_PCT: Final[float] = 0.30
MIN_OPEN_INTEREST: Final[int] = 10


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _model_mark(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    valuation_date: str,
    stock_price: float,
    dte_days: int,
    implied_vol: float,
    risk_free_rate: float,
    dividend_yield: float,
) -> dict[str, Any]:
    result = price_european_option(
        option_pricing_input(
            symbol,
            option_type,
            strike,
            expiry,
            valuation_date,
            stock_price,
            max(dte_days, 0) / 365.0,
            implied_vol,
            risk_free_rate,
            dividend_yield,
            "model_priced",
        )
    )
    return result.to_dict()


def _percentile_rank(value: float, values: Sequence[float]) -> float:
    if not values:
        return 0.5
    below = sum(candidate < value for candidate in values)
    equal = sum(candidate == value for candidate in values)
    return (below + 0.5 * equal) / len(values)


def _directional_option_types(strategy_direction: str, scenario_price: float, spot: float) -> tuple[str, ...]:
    if strategy_direction == "bullish":
        return ("call",)
    if strategy_direction == "bearish":
        return ("put",)
    if scenario_price > spot * 1.002:
        return ("call",)
    if scenario_price < spot * 0.998:
        return ("put",)
    return ("call", "put")


def _candidate_record(
    row: dict[str, Any],
    scenario_price: float,
    days_forward: int,
    iv_shift: float,
    strategy_direction: str,
    target_dte: int,
    risk_free_rate: float,
    dividend_yield: float,
    iv_values: Sequence[float],
) -> dict[str, object]:
    symbol = str(row["symbol"])
    option_type = str(row["option_type"])
    strike = float(row["strike"])
    expiry = str(row["expiry"])
    snapshot_date = str(row["snapshot_date"])
    spot = float(row["underlying_spot"])
    dte = int(row["dte_calendar"])
    bid = float(row["bid"])
    ask = float(row["ask"])
    mid = float(row["mid"])
    implied_vol = float(row["implied_vol"])
    scenario_iv = _clamp(implied_vol + iv_shift, 0.005, 5.0)
    remaining_dte = max(dte - days_forward, 0)
    current_model = _model_mark(
        symbol,
        option_type,
        strike,
        expiry,
        snapshot_date,
        spot,
        dte,
        implied_vol,
        risk_free_rate,
        dividend_yield,
    )
    scenario_model = _model_mark(
        symbol,
        option_type,
        strike,
        expiry,
        snapshot_date,
        scenario_price,
        remaining_dte,
        scenario_iv,
        risk_free_rate,
        dividend_yield,
    )
    spread = ask - bid
    spread_pct = spread / mid if mid > 0.0 else 1.0
    modeled_exit_friction = min(max(spread / 2.0, 0.01), float(scenario_model["model_price"]))
    modeled_exit = max(0.0, float(scenario_model["model_price"]) - modeled_exit_friction)
    projected_pnl = modeled_exit - ask
    projected_return = projected_pnl / ask if ask > 0.0 else -1.0
    target_delta = 0.58 if option_type == "call" else -0.58
    delta_fit = _clamp(1.0 - abs(float(current_model["delta"]) - target_delta) / 0.45, 0.0, 1.0)
    dte_fit = _clamp(1.0 - abs(dte - target_dte) / max(float(target_dte), 1.0), 0.0, 1.0)
    spread_score = _clamp(1.0 - spread_pct / MAX_SPREAD_PCT, 0.0, 1.0)
    oi_score = _clamp(math.log1p(int(row["open_interest"])) / math.log(5001.0), 0.0, 1.0)
    volume_score = _clamp(math.log1p(int(row["volume"])) / math.log(1001.0), 0.0, 1.0)
    liquidity_score = 0.55 * spread_score + 0.30 * oi_score + 0.15 * volume_score
    iv_value_score = 1.0 - _percentile_rank(implied_vol, iv_values)
    scenario_score = 0.5 + 0.5 * math.tanh(projected_return / 1.5)
    quote_model_fit = _clamp(1.0 - abs(float(current_model["model_price"]) - mid) / max(mid, 0.01), 0.0, 1.0)
    theta_runway = _clamp(remaining_dte / max(dte, 1), 0.0, 1.0)
    strategy_fit = 1.0 if (
        (strategy_direction == "bullish" and option_type == "call")
        or (strategy_direction == "bearish" and option_type == "put")
    ) else 0.55
    score = (
        0.22 * liquidity_score
        + 0.20 * scenario_score
        + 0.16 * delta_fit
        + 0.13 * dte_fit
        + 0.10 * iv_value_score
        + 0.08 * quote_model_fit
        + 0.06 * theta_runway
        + 0.05 * strategy_fit
    )
    breakeven = strike + ask if option_type == "call" else strike - ask
    return {
        "expression_id": f"{symbol}|{expiry}|{option_type}|{strike:g}|long",
        "expression_type": f"long_{option_type}",
        "symbol": symbol,
        "expiry": expiry,
        "dte_calendar": dte,
        "remaining_dte_in_scenario": remaining_dte,
        "option_type": option_type,
        "strike": round(strike, 6),
        "bid": round(bid, 6),
        "ask": round(ask, 6),
        "mid": round(mid, 6),
        "spread_pct": round(spread_pct, 6),
        "volume": int(row["volume"]),
        "open_interest": int(row["open_interest"]),
        "implied_vol": round(implied_vol, 6),
        "scenario_implied_vol": round(scenario_iv, 6),
        "current_model_value": round(float(current_model["model_price"]), 6),
        "scenario_model_value": round(float(scenario_model["model_price"]), 6),
        "modeled_exit_after_friction": round(modeled_exit, 6),
        "entry_assumption": "current_ask",
        "exit_assumption": "scenario_model_value_less_half_current_spread_floor",
        "projected_pnl_per_share": round(projected_pnl, 6),
        "projected_return_on_premium": round(projected_return, 6),
        "maximum_loss_per_share": round(ask, 6),
        "breakeven_at_expiry": round(breakeven, 6),
        "delta": round(float(current_model["delta"]), 6),
        "gamma": round(float(current_model["gamma"]), 6),
        "theta_per_day": round(float(current_model["theta"]), 6),
        "vega_per_vol_point": round(float(current_model["vega"]), 6),
        "liquidity_score": round(liquidity_score, 6),
        "scenario_fit_score": round(scenario_score, 6),
        "value_score": round(score, 6),
        "active_policy_eligible": True,
        "quote_observed_but_future_value_model_projected": True,
        "not_expected_return": True,
        "not_trade_recommendation": True,
    }


def _vertical_candidates(
    long_candidates: Sequence[dict[str, object]],
    chain_rows: Sequence[dict[str, Any]],
    scenario_price: float,
    days_forward: int,
    iv_shift: float,
    risk_free_rate: float,
    dividend_yield: float,
) -> list[dict[str, object]]:
    verticals: list[dict[str, object]] = []
    for long in long_candidates[:12]:
        option_type = str(long["option_type"])
        long_strike = float(long["strike"])
        expiry = str(long["expiry"])
        possible_shorts = [
            row
            for row in chain_rows
            if str(row["option_type"]) == option_type
            and str(row["expiry"]) == expiry
            and float(row["bid"]) > 0.0
            and (
                (option_type == "call" and long_strike < float(row["strike"]) <= max(scenario_price, long_strike * 1.12))
                or (option_type == "put" and min(scenario_price, long_strike * 0.88) <= float(row["strike"]) < long_strike)
            )
        ]
        if not possible_shorts:
            continue
        short = min(possible_shorts, key=lambda row: (abs(float(row["strike"]) - scenario_price), -int(row["open_interest"])))
        short_strike = float(short["strike"])
        width = abs(short_strike - long_strike)
        debit = float(long["ask"]) - float(short["bid"])
        if debit <= 0.0 or debit >= width:
            continue
        remaining_dte = int(long["remaining_dte_in_scenario"])
        short_scenario = _model_mark(
            str(short["symbol"]),
            option_type,
            short_strike,
            str(short["expiry"]),
            str(short["snapshot_date"]),
            scenario_price,
            remaining_dte,
            _clamp(float(short["implied_vol"]) + iv_shift, 0.005, 5.0),
            risk_free_rate,
            dividend_yield,
        )
        scenario_value = max(float(long["scenario_model_value"]) - float(short_scenario["model_price"]), 0.0)
        spread_friction = max((float(long["ask"]) - float(long["bid"]) + float(short["ask"]) - float(short["bid"])) / 2.0, 0.02)
        exit_value = max(0.0, scenario_value - spread_friction)
        projected_pnl = exit_value - debit
        projected_return = projected_pnl / debit
        capital_efficiency = _clamp((width - debit) / max(debit, 0.01) / 4.0, 0.0, 1.0)
        value_score = 0.55 * float(long["value_score"]) + 0.25 * (0.5 + 0.5 * math.tanh(projected_return / 1.5)) + 0.20 * capital_efficiency
        verticals.append(
            {
                "expression_id": f"{long['symbol']}|{expiry}|{option_type}|{long_strike:g}-{short_strike:g}|debit_vertical",
                "expression_type": f"{option_type}_debit_vertical",
                "symbol": long["symbol"],
                "expiry": expiry,
                "dte_calendar": long["dte_calendar"],
                "remaining_dte_in_scenario": remaining_dte,
                "option_type": option_type,
                "long_strike": round(long_strike, 6),
                "short_strike": round(short_strike, 6),
                "net_debit_assumption": round(debit, 6),
                "entry_assumption": "long_at_ask_short_at_bid",
                "scenario_model_value": round(scenario_value, 6),
                "modeled_exit_after_friction": round(exit_value, 6),
                "projected_pnl_per_share": round(projected_pnl, 6),
                "projected_return_on_debit": round(projected_return, 6),
                "maximum_loss_per_share": round(debit, 6),
                "maximum_profit_per_share": round(width - debit, 6),
                "width": round(width, 6),
                "value_score": round(value_score, 6),
                "active_policy_eligible": False,
                "active_policy_status": "research_structure_only_current_canon_is_long_premium_single_leg",
                "quote_observed_but_future_value_model_projected": True,
                "not_expected_return": True,
                "not_trade_recommendation": True,
            }
        )
    verticals.sort(key=lambda record: (-float(record["value_score"]), str(record["expression_id"])))
    return verticals


def _scenario_surface(
    expression: dict[str, object],
    price_points: Sequence[float],
    time_points: Sequence[int],
    chain_rows: Sequence[dict[str, Any]],
    iv_shift: float,
    risk_free_rate: float,
    dividend_yield: float,
) -> list[dict[str, object]]:
    symbol = str(expression["symbol"])
    expiry = str(expression["expiry"])
    option_type = str(expression["option_type"])
    dte = int(expression["dte_calendar"])
    rows_by_strike = {
        float(row["strike"]): row
        for row in chain_rows
        if str(row["expiry"]) == expiry and str(row["option_type"]) == option_type
    }
    values: list[dict[str, object]] = []
    for elapsed_days in sorted(set(time_points)):
        remaining_dte = max(dte - elapsed_days, 0)
        for stock_price in sorted(set(price_points)):
            if "strike" in expression:
                strike = float(expression["strike"])
                source = rows_by_strike[strike]
                model = _model_mark(
                    symbol,
                    option_type,
                    strike,
                    expiry,
                    str(source["snapshot_date"]),
                    stock_price,
                    remaining_dte,
                    _clamp(float(source["implied_vol"]) + iv_shift, 0.005, 5.0),
                    risk_free_rate,
                    dividend_yield,
                )
                value = float(model["model_price"])
            else:
                long_strike = float(expression["long_strike"])
                short_strike = float(expression["short_strike"])
                long_source = rows_by_strike[long_strike]
                short_source = rows_by_strike[short_strike]
                long_model = _model_mark(
                    symbol,
                    option_type,
                    long_strike,
                    expiry,
                    str(long_source["snapshot_date"]),
                    stock_price,
                    remaining_dte,
                    _clamp(float(long_source["implied_vol"]) + iv_shift, 0.005, 5.0),
                    risk_free_rate,
                    dividend_yield,
                )
                short_model = _model_mark(
                    symbol,
                    option_type,
                    short_strike,
                    expiry,
                    str(short_source["snapshot_date"]),
                    stock_price,
                    remaining_dte,
                    _clamp(float(short_source["implied_vol"]) + iv_shift, 0.005, 5.0),
                    risk_free_rate,
                    dividend_yield,
                )
                value = max(float(long_model["model_price"]) - float(short_model["model_price"]), 0.0)
            values.append(
                {
                    "stock_price": round(stock_price, 6),
                    "elapsed_calendar_days": elapsed_days,
                    "remaining_dte": remaining_dte,
                    "theoretical_value": round(value, 6),
                }
            )
    return values


def project_option_values(
    chain_rows: Sequence[dict[str, Any]],
    scenario_price: float,
    days_forward: int,
    iv_shift: float,
    strategy_direction: str,
    target_dte: int,
    risk_free_rate: float,
    risk_free_source: str,
    dividend_yield: float,
    support_price: float | None,
    resistance_price: float | None,
    annualized_realized_vol: float,
) -> dict[str, object]:
    """Project actual observed contracts without representing model values as future quotes."""

    if not chain_rows:
        return {
            "projector_status": "blocked_no_validated_chain_rows_for_symbol",
            "long_candidates": [],
            "vertical_candidates": [],
            "paper_only": True,
            "live_blocked": True,
        }
    spot = float(chain_rows[0]["underlying_spot"])
    if scenario_price <= 0.0:
        raise ValueError(f"scenario_price must be positive: scenario_price={scenario_price}")
    if days_forward < 0 or days_forward > 365:
        raise ValueError(f"days_forward must be inside [0, 365]: days_forward={days_forward}")
    if not -2.0 <= iv_shift <= 2.0:
        raise ValueError(f"iv_shift must be inside [-2, 2]: iv_shift={iv_shift}")
    option_types = _directional_option_types(strategy_direction, scenario_price, spot)
    eligible = [
        row
        for row in chain_rows
        if str(row["option_type"]) in option_types
        and days_forward + 2 <= int(row["dte_calendar"]) <= MAX_CONTRACT_DTE
        and float(row["ask"]) > 0.0
        and float(row["mid"]) > 0.0
        and (float(row["ask"]) - float(row["bid"])) / float(row["mid"]) <= MAX_SPREAD_PCT
        and int(row["open_interest"]) >= MIN_OPEN_INTEREST
        and abs(float(row["strike"]) / spot - 1.0) <= 0.25
    ]
    iv_values = [float(row["implied_vol"]) for row in eligible]
    longs = [
        _candidate_record(
            row,
            scenario_price,
            days_forward,
            iv_shift,
            strategy_direction,
            target_dte,
            risk_free_rate,
            dividend_yield,
            iv_values,
        )
        for row in eligible
    ]
    longs.sort(key=lambda record: (-float(record["value_score"]), str(record["expression_id"])))
    verticals = _vertical_candidates(
        longs,
        eligible,
        scenario_price,
        days_forward,
        iv_shift,
        risk_free_rate,
        dividend_yield,
    )
    ranked_expressions = sorted(
        [*longs[:12], *verticals[:8]],
        key=lambda record: (-float(record["value_score"]), str(record["expression_id"])),
    )
    best = ranked_expressions[0] if ranked_expressions else None
    sigma_move = spot * annualized_realized_vol * math.sqrt(max(days_forward, 1) / 365.0)
    raw_prices = [spot, scenario_price, max(0.01, spot - sigma_move), spot + sigma_move]
    if support_price is not None:
        raw_prices.append(support_price)
    if resistance_price is not None:
        raw_prices.append(resistance_price)
    price_points = [round(value, 6) for value in raw_prices if value > 0.0]
    time_points = [0, days_forward // 2, days_forward]
    surface = [] if best is None else _scenario_surface(
        best,
        price_points,
        time_points,
        eligible,
        iv_shift,
        risk_free_rate,
        dividend_yield,
    )
    projector_status = (
        "complete_scenario_research"
        if best is not None
        else "blocked_no_contract_passing_eligibility_filters"
    )
    body: dict[str, object] = {
        "artifact_type": "strategy_aware_option_value_projection",
        "projector_version": OPTIONS_VALUE_PROJECTOR_VERSION,
        "projector_status": projector_status,
        "symbol": str(chain_rows[0]["symbol"]),
        "snapshot_date": str(chain_rows[0]["snapshot_date"]),
        "current_stock_price": round(spot, 6),
        "scenario_stock_price": round(scenario_price, 6),
        "days_forward": days_forward,
        "iv_shift_decimal": round(iv_shift, 6),
        "strategy_direction": strategy_direction,
        "target_dte": target_dte,
        "risk_free_rate": round(risk_free_rate, 8),
        "risk_free_source": risk_free_source,
        "dividend_yield_assumption": round(dividend_yield, 8),
        "eligible_contract_count": len(eligible),
        "eligibility_filters": {
            "minimum_remaining_dte_after_scenario": days_forward + 2,
            "maximum_contract_dte": MAX_CONTRACT_DTE,
            "maximum_relative_spread": MAX_SPREAD_PCT,
            "minimum_open_interest": MIN_OPEN_INTEREST,
            "maximum_absolute_moneyness_distance": 0.25,
            "positive_ask_required": True,
            "positive_mid_required": True,
        },
        "long_candidates": longs[:20],
        "vertical_candidates": verticals[:12],
        "best_expression": best,
        "best_expression_semantics": "highest_scenario_fit_research_expression_not_a_trade_recommendation",
        "best_active_policy_eligible_expression": next((record for record in ranked_expressions if record.get("active_policy_eligible") is True), None),
        "scenario_surface": surface,
        "scenario_price_points": sorted(set(price_points)),
        "scenario_time_points": sorted(set(time_points)),
        "observed_quotes_are_entry_context_only": True,
        "future_values_are_model_projections_not_quotes": True,
        "american_exercise_and_discrete_dividend_adjustment_not_applied": True,
        "model_risk_present": True,
        "profitability_claim_allowed": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "projection_hash": canonical_hash(body)}
