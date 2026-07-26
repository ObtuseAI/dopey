"""Cox-Ross-Rubinstein validation oracle for paper-only option research."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence, TypedDict

from .option_pricing_models import option_pricing_input, price_european_option


BINOMIAL_ORACLE_VERSION = "dopey-crr-binomial-oracle-v2"
MAX_EXACT_CASH_DIVIDEND_STEPS = 18


class CashDividend(TypedDict):
    time_years: float
    amount: float


def cash_dividend(time_years: float, amount: float) -> CashDividend:
    """Create one validated deterministic cash-dividend event."""

    if not math.isfinite(time_years) or time_years <= 0.0:
        raise ValueError(f"cash dividend time_years must be positive and finite: value={time_years}")
    if not math.isfinite(amount) or amount <= 0.0:
        raise ValueError(f"cash dividend amount must be positive and finite: value={amount}")
    return {"time_years": float(time_years), "amount": float(amount)}


def price_binomial_option(
    option_type: str,
    exercise_style: str,
    underlying_price: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    implied_vol: float,
    steps: int,
    cash_dividends: Sequence[CashDividend],
) -> dict[str, object]:
    """Price one option with recombining CRR or exact bounded cash-dividend paths."""

    _validate_inputs(
        option_type,
        exercise_style,
        underlying_price,
        strike,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        implied_vol,
        steps,
        cash_dividends,
    )
    if time_to_expiry_years == 0.0:
        intrinsic = _intrinsic(option_type, underlying_price, strike)
        result: dict[str, object] = {
            "artifact_type": "binomial_option_price",
            "oracle_version": BINOMIAL_ORACLE_VERSION,
            "option_type": option_type,
            "exercise_style": exercise_style,
            "underlying_price": underlying_price,
            "strike": strike,
            "time_to_expiry_years": 0.0,
            "risk_free_rate": risk_free_rate,
            "dividend_yield": dividend_yield,
            "implied_vol": implied_vol,
            "steps": steps,
            "model_price": round(intrinsic, 8),
            "intrinsic_value": round(intrinsic, 8),
            "extrinsic_value": 0.0,
            "delta": None,
            "gamma": None,
            "theta_annual": None,
            "early_exercise_node_count": 0,
            "early_exercise_boundary": [],
            "cash_dividends": list(cash_dividends),
            "cash_dividend_method": "none" if not cash_dividends else "exact_nonrecombining_path_tree",
            "pricing_source_tier": "model_priced_oracle",
            "real_option_chain_absent": True,
            "quality_flags": ["expiry_intrinsic_value"],
            "paper_only": True,
            "live_blocked": True,
        }
        result["tree_hash"] = _stable_hash(result)
        return result

    dt = time_to_expiry_years / steps
    up = math.exp(implied_vol * math.sqrt(dt))
    down = 1.0 / up
    growth = math.exp((risk_free_rate - dividend_yield) * dt)
    probability_up = (growth - down) / (up - down)
    if not 0.0 <= probability_up <= 1.0:
        raise ValueError(
            "CRR risk-neutral probability is outside [0, 1]: "
            f"probability_up={probability_up}, up={up}, down={down}, dt={dt}"
        )
    discount = math.exp(-risk_free_rate * dt)
    if cash_dividends:
        tree = _price_exact_cash_dividend_tree(
            option_type,
            exercise_style,
            underlying_price,
            strike,
            time_to_expiry_years,
            steps,
            up,
            down,
            probability_up,
            discount,
            cash_dividends,
        )
        dividend_method = "exact_nonrecombining_path_tree"
        quality_flags = ["exact_cash_dividend_tree_bounded_steps"]
    else:
        tree = _price_recombining_tree(
            option_type,
            exercise_style,
            underlying_price,
            strike,
            time_to_expiry_years,
            steps,
            up,
            down,
            probability_up,
            discount,
        )
        dividend_method = "continuous_yield_in_risk_neutral_probability"
        quality_flags = []
    model_price = float(tree["model_price"])
    bounds = option_no_arbitrage_bounds(
        option_type,
        exercise_style,
        underlying_price,
        strike,
        time_to_expiry_years,
        risk_free_rate,
        dividend_yield,
        bool(cash_dividends),
    )
    if model_price < float(bounds["lower_bound"]) - 1e-8 or model_price > float(bounds["upper_bound"]) + 1e-8:
        raise ValueError(
            "binomial price violates declared no-arbitrage bounds: "
            f"price={model_price}, bounds={bounds}, option_type={option_type}, style={exercise_style}"
        )
    result = {
        "artifact_type": "binomial_option_price",
        "oracle_version": BINOMIAL_ORACLE_VERSION,
        "option_type": option_type,
        "exercise_style": exercise_style,
        "underlying_price": round(underlying_price, 8),
        "strike": round(strike, 8),
        "time_to_expiry_years": round(time_to_expiry_years, 10),
        "risk_free_rate": round(risk_free_rate, 10),
        "dividend_yield": round(dividend_yield, 10),
        "implied_vol": round(implied_vol, 10),
        "steps": steps,
        "up_factor": round(up, 12),
        "down_factor": round(down, 12),
        "risk_neutral_probability_up": round(probability_up, 12),
        "model_price": round(model_price, 8),
        "intrinsic_value": round(_intrinsic(option_type, underlying_price, strike), 8),
        "extrinsic_value": round(max(0.0, model_price - _intrinsic(option_type, underlying_price, strike)), 8),
        "delta": _rounded_optional(tree["delta"], 8),
        "gamma": _rounded_optional(tree["gamma"], 8),
        "theta_annual": _rounded_optional(tree["theta_annual"], 8),
        "early_exercise_node_count": int(tree["early_exercise_node_count"]),
        "early_exercise_boundary": tree["early_exercise_boundary"],
        "no_arbitrage_bounds": bounds,
        "cash_dividends": [{"time_years": round(item["time_years"], 10), "amount": round(item["amount"], 8)} for item in cash_dividends],
        "cash_dividend_method": dividend_method,
        "pricing_source_tier": "model_priced_oracle",
        "real_option_chain_absent": True,
        "quality_flags": quality_flags,
        "paper_only": True,
        "live_blocked": True,
    }
    result["tree_hash"] = _stable_hash(result)
    return result


def option_no_arbitrage_bounds(
    option_type: str,
    exercise_style: str,
    underlying_price: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    cash_dividends_present: bool,
) -> dict[str, float]:
    """Return conservative bounds valid for the declared exercise/dividend model."""

    if option_type not in {"call", "put"}:
        raise ValueError(f"unsupported option_type: {option_type}")
    if exercise_style not in {"european", "american"}:
        raise ValueError(f"unsupported exercise_style: {exercise_style}")
    discounted_spot = underlying_price * math.exp(-dividend_yield * time_to_expiry_years)
    discounted_strike = strike * math.exp(-risk_free_rate * time_to_expiry_years)
    if cash_dividends_present:
        lower = _intrinsic(option_type, underlying_price, strike) if exercise_style == "american" else 0.0
    elif option_type == "call":
        lower = max(0.0, discounted_spot - discounted_strike)
    else:
        lower = max(0.0, discounted_strike - discounted_spot)
    if option_type == "call":
        upper = underlying_price if exercise_style == "american" or cash_dividends_present else discounted_spot
    else:
        upper = strike if exercise_style == "american" or cash_dividends_present else discounted_strike
    return {"lower_bound": round(lower, 8), "upper_bound": round(upper, 8)}


def defined_risk_vertical_bounds(
    option_type: str,
    long_strike: float,
    short_strike: float,
    long_premium: float,
    short_premium: float,
) -> dict[str, object]:
    """Validate debit-vertical maximum loss and profit in premium units."""

    if option_type not in {"call", "put"}:
        raise ValueError(f"unsupported vertical option_type: {option_type}")
    if min(long_strike, short_strike) <= 0.0:
        raise ValueError("vertical strikes must be positive")
    if min(long_premium, short_premium) < 0.0:
        raise ValueError("vertical premiums must be nonnegative")
    if option_type == "call" and long_strike >= short_strike:
        raise ValueError("debit call vertical requires long_strike < short_strike")
    if option_type == "put" and long_strike <= short_strike:
        raise ValueError("debit put vertical requires long_strike > short_strike")
    debit = long_premium - short_premium
    width = abs(short_strike - long_strike)
    if debit < 0.0 or debit > width:
        raise ValueError(f"vertical debit must be inside [0, width]: debit={debit}, width={width}")
    result: dict[str, object] = {
        "artifact_type": "defined_risk_vertical_bounds",
        "option_type": option_type,
        "width": round(width, 8),
        "net_debit": round(debit, 8),
        "maximum_loss": round(debit, 8),
        "maximum_profit": round(width - debit, 8),
        "loss_is_capped": True,
        "paper_only": True,
        "live_blocked": True,
    }
    result["bounds_hash"] = _stable_hash(result)
    return result


def run_binomial_oracle_validation(output_path: Path) -> dict[str, object]:
    """Run deterministic convergence, invariants, exercise, and spread fixtures."""

    base = {
        "underlying_price": 100.0,
        "strike": 100.0,
        "time_to_expiry_years": 1.0,
        "risk_free_rate": 0.05,
        "dividend_yield": 0.0,
        "implied_vol": 0.2,
    }
    convergence: list[dict[str, object]] = []
    bs_prices: dict[str, float] = {}
    for option_type in ("call", "put"):
        black_scholes = price_european_option(option_pricing_input(
            "ORACLE_FIXTURE",
            option_type,
            base["strike"],
            "2027-01-01",
            "2026-01-01",
            base["underlying_price"],
            base["time_to_expiry_years"],
            base["implied_vol"],
            base["risk_free_rate"],
            base["dividend_yield"],
            "fixture_only",
        ))
        bs_prices[option_type] = black_scholes.model_price
        for steps in (25, 50, 100, 200, 400):
            result = price_binomial_option(
                option_type,
                "european",
                base["underlying_price"],
                base["strike"],
                base["time_to_expiry_years"],
                base["risk_free_rate"],
                base["dividend_yield"],
                base["implied_vol"],
                steps,
                (),
            )
            convergence.append({
                "option_type": option_type,
                "steps": steps,
                "binomial_price": result["model_price"],
                "black_scholes_price": black_scholes.model_price,
                "absolute_error": round(abs(float(result["model_price"]) - black_scholes.model_price), 8),
            })

    european_put = price_binomial_option("put", "european", 90.0, 110.0, 1.0, 0.05, 0.0, 0.2, 400, ())
    american_put = price_binomial_option("put", "american", 90.0, 110.0, 1.0, 0.05, 0.0, 0.2, 400, ())
    european_call = price_binomial_option("call", "european", 100.0, 100.0, 1.0, 0.05, 0.0, 0.2, 400, ())
    american_call = price_binomial_option("call", "american", 100.0, 100.0, 1.0, 0.05, 0.0, 0.2, 400, ())
    dividend_call = price_binomial_option(
        "call", "american", 100.0, 90.0, 0.25, 0.03, 0.0, 0.22, 12, (cash_dividend(0.10, 5.0),),
    )
    parity_left = float(european_call["model_price"]) - float(price_binomial_option("put", "european", 100.0, 100.0, 1.0, 0.05, 0.0, 0.2, 400, ())["model_price"])
    parity_right = 100.0 - 100.0 * math.exp(-0.05)
    low_strike_call = price_binomial_option("call", "european", 100.0, 90.0, 1.0, 0.05, 0.0, 0.2, 200, ())
    high_strike_call = price_binomial_option("call", "european", 100.0, 110.0, 1.0, 0.05, 0.0, 0.2, 200, ())
    low_vol_call = price_binomial_option("call", "european", 100.0, 100.0, 1.0, 0.05, 0.0, 0.15, 200, ())
    high_vol_call = price_binomial_option("call", "european", 100.0, 100.0, 1.0, 0.05, 0.0, 0.30, 200, ())
    vertical = defined_risk_vertical_bounds(
        "call",
        100.0,
        110.0,
        float(european_call["model_price"]),
        float(high_strike_call["model_price"]),
    )
    sensitivity_grid = _build_sensitivity_grid(base)
    call_spot_prices = [
        float(row["model_price"])
        for row in sensitivity_grid
        if row["axis"] == "spot" and row["option_type"] == "call"
    ]
    put_spot_prices = [
        float(row["model_price"])
        for row in sensitivity_grid
        if row["axis"] == "spot" and row["option_type"] == "put"
    ]
    call_strike_prices = [
        float(row["model_price"])
        for row in sensitivity_grid
        if row["axis"] == "strike" and row["option_type"] == "call"
    ]
    put_strike_prices = [
        float(row["model_price"])
        for row in sensitivity_grid
        if row["axis"] == "strike" and row["option_type"] == "put"
    ]
    deltas = [
        (str(row["option_type"]), float(row["delta"]))
        for row in sensitivity_grid
        if row["axis"] == "spot" and row["delta"] is not None
    ]
    gammas = [
        float(row["gamma"])
        for row in sensitivity_grid
        if row["axis"] == "spot" and row["gamma"] is not None
    ]
    odd_steps_call = price_binomial_option("call", "european", 100.0, 100.0, 1.0, 0.05, 0.0, 0.2, 399, ())
    even_steps_call = price_binomial_option("call", "european", 100.0, 100.0, 1.0, 0.05, 0.0, 0.2, 400, ())
    tests = [
        _validation("crr_converges_to_black_scholes", max(float(row["absolute_error"]) for row in convergence if int(row["steps"]) == 400) < 0.02),
        _validation("american_put_not_below_european", float(american_put["model_price"]) >= float(european_put["model_price"])),
        _validation("american_put_has_early_exercise_region", int(american_put["early_exercise_node_count"]) > 0),
        _validation("no_dividend_american_call_matches_european", abs(float(american_call["model_price"]) - float(european_call["model_price"])) < 1e-6),
        _validation("no_dividend_american_call_has_no_early_exercise", int(american_call["early_exercise_node_count"]) == 0),
        _validation("cash_dividend_american_call_detects_early_exercise", int(dividend_call["early_exercise_node_count"]) > 0),
        _validation("put_call_parity", abs(parity_left - parity_right) < 0.02),
        _validation("call_value_decreases_with_strike", float(low_strike_call["model_price"]) > float(high_strike_call["model_price"])),
        _validation("option_value_increases_with_volatility", float(high_vol_call["model_price"]) > float(low_vol_call["model_price"])),
        _validation("defined_risk_vertical_is_capped", bool(vertical["loss_is_capped"]) and float(vertical["maximum_loss"]) >= 0.0),
        _validation("call_value_increases_with_spot", _is_nondecreasing(call_spot_prices)),
        _validation("put_value_decreases_with_spot", _is_nonincreasing(put_spot_prices)),
        _validation("call_value_decreases_across_strikes", _is_nonincreasing(call_strike_prices)),
        _validation("put_value_increases_across_strikes", _is_nondecreasing(put_strike_prices)),
        _validation("call_and_put_values_are_convex_in_spot", _is_convex(call_spot_prices) and _is_convex(put_spot_prices)),
        _validation("delta_respects_option_bounds", all(0.0 <= delta <= 1.0 if option_type == "call" else -1.0 <= delta <= 0.0 for option_type, delta in deltas)),
        _validation("gamma_is_nonnegative", all(gamma >= -1e-8 for gamma in gammas)),
        _validation("odd_even_convergence_gap_is_small", abs(float(odd_steps_call["model_price"]) - float(even_steps_call["model_price"])) < 0.02),
    ]
    failed = [test for test in tests if str(test["status"]) != "pass"]
    result: dict[str, object] = {
        "artifact_type": "binomial_oracle_validation",
        "oracle_version": BINOMIAL_ORACLE_VERSION,
        "validation_status": "complete" if not failed else "failed_invariant",
        "test_count": len(tests),
        "passed_test_count": len(tests) - len(failed),
        "failed_test_count": len(failed),
        "tests": tests,
        "convergence": convergence,
        "sensitivity_grid": sensitivity_grid,
        "convergence_diagnostics": {
            "odd_step_count": 399,
            "even_step_count": 400,
            "odd_even_price_gap": round(abs(float(odd_steps_call["model_price"]) - float(even_steps_call["model_price"])), 8),
            "black_scholes_reference_prices": bs_prices,
        },
        "fixtures": {
            "european_call": european_call,
            "american_call": american_call,
            "european_put": european_put,
            "american_put": american_put,
            "discrete_dividend_american_call": dividend_call,
            "defined_risk_vertical": vertical,
        },
        "separation_law": {
            "theoretical_pricer": "implemented",
            "historical_market_replay": "not_substituted",
            "execution_fill_simulator": "not_substituted",
        },
        "scalability_limits": {
            "exact_cash_dividend_maximum_steps": MAX_EXACT_CASH_DIVIDEND_STEPS,
            "fallback_available": False,
            "failure_policy": "raise_exact_node_budget_error",
            "reason": "no silent approximation may replace the declared exact nonrecombining fixture method",
        },
        "pricing_source_tier": "model_priced_oracle",
        "real_option_chain_absent": True,
        "profitability_claim_allowed": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    result["validation_hash"] = _stable_hash(result)
    _write_json_atomic(output_path, result)
    return result


def _build_sensitivity_grid(base: Mapping[str, float]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    axes = {
        "spot": (70.0, 85.0, 100.0, 115.0, 130.0),
        "strike": (70.0, 85.0, 100.0, 115.0, 130.0),
        "volatility": (0.10, 0.20, 0.30, 0.40, 0.50),
        "time": (0.10, 0.25, 0.50, 0.75, 1.00),
    }
    for axis, values in axes.items():
        for option_type in ("call", "put"):
            for value in values:
                inputs = dict(base)
                if axis == "spot":
                    inputs["underlying_price"] = value
                elif axis == "strike":
                    inputs["strike"] = value
                elif axis == "volatility":
                    inputs["implied_vol"] = value
                else:
                    inputs["time_to_expiry_years"] = value
                priced = price_binomial_option(
                    option_type,
                    "european",
                    inputs["underlying_price"],
                    inputs["strike"],
                    inputs["time_to_expiry_years"],
                    inputs["risk_free_rate"],
                    inputs["dividend_yield"],
                    inputs["implied_vol"],
                    300,
                    (),
                )
                rows.append({
                    "axis": axis,
                    "axis_value": value,
                    "option_type": option_type,
                    "model_price": priced["model_price"],
                    "delta": priced["delta"],
                    "gamma": priced["gamma"],
                    "theta_annual": priced["theta_annual"],
                })
    return rows


def _is_nondecreasing(values: Sequence[float]) -> bool:
    return all(left <= right + 1e-8 for left, right in zip(values, values[1:]))


def _is_nonincreasing(values: Sequence[float]) -> bool:
    return all(left + 1e-8 >= right for left, right in zip(values, values[1:]))


def _is_convex(values: Sequence[float]) -> bool:
    return all(values[index] - 2.0 * values[index + 1] + values[index + 2] >= -1e-6 for index in range(len(values) - 2))


def _price_recombining_tree(
    option_type: str,
    exercise_style: str,
    underlying_price: float,
    strike: float,
    time_to_expiry_years: float,
    steps: int,
    up: float,
    down: float,
    probability_up: float,
    discount: float,
) -> dict[str, object]:
    dt = time_to_expiry_years / steps
    option_values = [
        _intrinsic(option_type, underlying_price * (up ** up_moves) * (down ** (steps - up_moves)), strike)
        for up_moves in range(steps + 1)
    ]
    early_boundaries: list[dict[str, object]] = []
    early_count = 0
    level_one_values: list[float] | None = None
    level_two_values: list[float] | None = None
    for level in range(steps - 1, -1, -1):
        next_values: list[float] = []
        exercised_stocks: list[float] = []
        for up_moves in range(level + 1):
            continuation = discount * (
                probability_up * option_values[up_moves + 1]
                + (1.0 - probability_up) * option_values[up_moves]
            )
            stock = underlying_price * (up ** up_moves) * (down ** (level - up_moves))
            exercise = _intrinsic(option_type, stock, strike)
            should_exercise = exercise_style == "american" and exercise > continuation + 1e-12
            next_values.append(exercise if should_exercise else continuation)
            if should_exercise:
                exercised_stocks.append(stock)
        option_values = next_values
        if level == 2:
            level_two_values = list(next_values)
        if level == 1:
            level_one_values = list(next_values)
        if exercised_stocks:
            early_count += len(exercised_stocks)
            early_boundaries.append(_exercise_boundary(option_type, level, dt, exercised_stocks))
    return {
        "model_price": option_values[0],
        **_tree_greeks(underlying_price, up, down, dt, option_values[0], level_one_values, level_two_values, None),
        "early_exercise_node_count": early_count,
        "early_exercise_boundary": sorted(early_boundaries, key=lambda row: int(row["step"])),
    }


def _price_exact_cash_dividend_tree(
    option_type: str,
    exercise_style: str,
    underlying_price: float,
    strike: float,
    time_to_expiry_years: float,
    steps: int,
    up: float,
    down: float,
    probability_up: float,
    discount: float,
    cash_dividends: Sequence[CashDividend],
) -> dict[str, object]:
    if steps > MAX_EXACT_CASH_DIVIDEND_STEPS:
        raise ValueError(
            "exact nonrecombining cash-dividend tree exceeds its deterministic node budget: "
            f"steps={steps}, maximum={MAX_EXACT_CASH_DIVIDEND_STEPS}"
        )
    dt = time_to_expiry_years / steps
    dividends_by_step: dict[int, float] = {}
    for dividend in cash_dividends:
        step = min(steps, max(1, int(round(dividend["time_years"] / dt))))
        dividends_by_step[step] = dividends_by_step.get(step, 0.0) + float(dividend["amount"])
    stock_levels: list[list[float]] = [[underlying_price]]
    for level in range(1, steps + 1):
        dividend = dividends_by_step.get(level, 0.0)
        stocks: list[float] = []
        for stock in stock_levels[-1]:
            down_stock = stock * down - dividend
            up_stock = stock * up - dividend
            if down_stock <= 0.0 or up_stock <= 0.0:
                raise ValueError(
                    "cash dividend creates a nonpositive lattice node: "
                    f"level={level}, dividend={dividend}, down_stock={down_stock}, up_stock={up_stock}"
                )
            stocks.extend((down_stock, up_stock))
        stock_levels.append(stocks)
    option_values = [_intrinsic(option_type, stock, strike) for stock in stock_levels[-1]]
    early_boundaries: list[dict[str, object]] = []
    early_count = 0
    level_one_values: list[float] | None = None
    level_two_values: list[float] | None = None
    for level in range(steps - 1, -1, -1):
        next_values: list[float] = []
        exercised_stocks: list[float] = []
        for node_index, stock in enumerate(stock_levels[level]):
            down_value = option_values[node_index * 2]
            up_value = option_values[node_index * 2 + 1]
            continuation = discount * (probability_up * up_value + (1.0 - probability_up) * down_value)
            exercise = _intrinsic(option_type, stock, strike)
            should_exercise = exercise_style == "american" and exercise > continuation + 1e-12
            next_values.append(exercise if should_exercise else continuation)
            if should_exercise:
                exercised_stocks.append(stock)
        option_values = next_values
        if level == 2:
            level_two_values = list(next_values)
        if level == 1:
            level_one_values = list(next_values)
        if exercised_stocks:
            early_count += len(exercised_stocks)
            early_boundaries.append(_exercise_boundary(option_type, level, dt, exercised_stocks))
    return {
        "model_price": option_values[0],
        **_tree_greeks(underlying_price, up, down, dt, option_values[0], level_one_values, level_two_values, stock_levels),
        "early_exercise_node_count": early_count,
        "early_exercise_boundary": sorted(early_boundaries, key=lambda row: int(row["step"])),
    }


def _tree_greeks(
    underlying_price: float,
    up: float,
    down: float,
    dt: float,
    root_value: float,
    level_one_values: Sequence[float] | None,
    level_two_values: Sequence[float] | None,
    stock_levels: Sequence[Sequence[float]] | None,
) -> dict[str, float | None]:
    if level_one_values is None or len(level_one_values) != 2:
        return {"delta": None, "gamma": None, "theta_annual": None}
    first_stocks = list(stock_levels[1]) if stock_levels is not None else [underlying_price * down, underlying_price * up]
    delta = (level_one_values[1] - level_one_values[0]) / (first_stocks[1] - first_stocks[0])
    if level_two_values is None or len(level_two_values) < 3:
        return {"delta": delta, "gamma": None, "theta_annual": None}
    if stock_levels is None:
        second_stocks = [underlying_price * down * down, underlying_price, underlying_price * up * up]
        middle_value = level_two_values[1]
    else:
        second_level = list(stock_levels[2])
        second_stocks = [second_level[0], (second_level[1] + second_level[2]) / 2.0, second_level[3]]
        middle_value = (level_two_values[1] + level_two_values[2]) / 2.0
    delta_down = (level_two_values[1] - level_two_values[0]) / (second_stocks[1] - second_stocks[0])
    delta_up = (level_two_values[-1] - level_two_values[-2]) / (second_stocks[2] - second_stocks[1])
    gamma = (delta_up - delta_down) / ((second_stocks[2] - second_stocks[0]) / 2.0)
    theta = (middle_value - root_value) / (2.0 * dt)
    return {"delta": delta, "gamma": gamma, "theta_annual": theta}


def _exercise_boundary(option_type: str, step: int, dt: float, exercised_stocks: Sequence[float]) -> dict[str, object]:
    boundary = min(exercised_stocks) if option_type == "call" else max(exercised_stocks)
    return {
        "step": step,
        "time_years": round(step * dt, 10),
        "boundary_underlying_price": round(boundary, 8),
        "exercised_node_count": len(exercised_stocks),
    }


def _validation(test_id: str, passed: bool) -> dict[str, object]:
    return {"test_id": test_id, "status": "pass" if passed else "fail"}


def _intrinsic(option_type: str, underlying_price: float, strike: float) -> float:
    return max(0.0, underlying_price - strike) if option_type == "call" else max(0.0, strike - underlying_price)


def _rounded_optional(value: object, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def _validate_inputs(
    option_type: str,
    exercise_style: str,
    underlying_price: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    implied_vol: float,
    steps: int,
    cash_dividends: Sequence[CashDividend],
) -> None:
    if option_type not in {"call", "put"}:
        raise ValueError(f"unsupported option_type: {option_type}")
    if exercise_style not in {"european", "american"}:
        raise ValueError(f"unsupported exercise_style: {exercise_style}")
    numeric_values = {
        "underlying_price": underlying_price,
        "strike": strike,
        "time_to_expiry_years": time_to_expiry_years,
        "risk_free_rate": risk_free_rate,
        "dividend_yield": dividend_yield,
        "implied_vol": implied_vol,
    }
    if any(not math.isfinite(value) for value in numeric_values.values()):
        raise ValueError(f"binomial inputs must be finite: values={numeric_values}")
    if underlying_price <= 0.0 or strike <= 0.0:
        raise ValueError(f"underlying_price and strike must be positive: spot={underlying_price}, strike={strike}")
    if time_to_expiry_years < 0.0:
        raise ValueError(f"time_to_expiry_years must be nonnegative: value={time_to_expiry_years}")
    if implied_vol <= 0.0 and time_to_expiry_years > 0.0:
        raise ValueError(f"implied_vol must be positive before expiry: value={implied_vol}")
    if dividend_yield < 0.0:
        raise ValueError(f"dividend_yield must be nonnegative: value={dividend_yield}")
    if steps < 2:
        raise ValueError(f"binomial steps must be at least two: steps={steps}")
    for dividend in cash_dividends:
        if dividend["time_years"] > time_to_expiry_years:
            raise ValueError(
                "cash dividend occurs after option expiry: "
                f"dividend_time={dividend['time_years']}, expiry={time_to_expiry_years}"
            )


def _stable_hash(record: Mapping[str, object]) -> str:
    normalized = {key: value for key, value in record.items() if not key.endswith("_hash")}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(record), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
