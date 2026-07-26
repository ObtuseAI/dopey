"""Leak-safe, deterministic indicator-combination research for one symbol."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import median
from typing import Final, TypedDict

from dopey.protocols.identity import canonical_hash
from dopey_equity_swing.market_structure import Bar


SYMBOL_STRATEGY_RESEARCH_VERSION: Final[str] = "dopey-symbol-strategy-research-v1"
FORWARD_HORIZON_DAYS: Final[int] = 20
ROUND_TRIP_COST_RATE: Final[float] = 0.0015
CHRONOLOGICAL_FOLD_COUNT: Final[int] = 4


class StrategyRecipe(TypedDict):
    strategy_id: str
    family: str
    direction: str
    conditions: tuple[str, ...]
    thesis: str


class StrategyTrade(TypedDict):
    signal_date: str
    entry_date: str
    exit_date: str
    direction: str
    entry_price: float
    exit_price: float
    net_return: float
    random_entry_net_return: float


STRATEGY_RECIPES: Final[tuple[StrategyRecipe, ...]] = (
    {
        "strategy_id": "trend_pullback_bull",
        "family": "trend",
        "direction": "bullish",
        "conditions": ("trend_up", "pullback_up"),
        "thesis": "Established uptrend revisits its fast trend without momentum failure.",
    },
    {
        "strategy_id": "trend_rally_bear",
        "family": "trend",
        "direction": "bearish",
        "conditions": ("trend_down", "pullback_down"),
        "thesis": "Established downtrend rallies into fast resistance without momentum repair.",
    },
    {
        "strategy_id": "momentum_stack_bull",
        "family": "momentum",
        "direction": "bullish",
        "conditions": ("trend_up", "momentum_up"),
        "thesis": "Trend, MACD impulse, and RSI state agree without an extreme reading.",
    },
    {
        "strategy_id": "momentum_stack_bear",
        "family": "momentum",
        "direction": "bearish",
        "conditions": ("trend_down", "momentum_down"),
        "thesis": "Downtrend, MACD impulse, and RSI state agree without capitulation.",
    },
    {
        "strategy_id": "breakout_participation_bull",
        "family": "breakout",
        "direction": "bullish",
        "conditions": ("breakout_up", "volume_confirm_up"),
        "thesis": "Price clears a prior range with above-normal participation.",
    },
    {
        "strategy_id": "breakdown_participation_bear",
        "family": "breakout",
        "direction": "bearish",
        "conditions": ("breakout_down", "volume_confirm_down"),
        "thesis": "Price loses a prior range with above-normal participation.",
    },
    {
        "strategy_id": "compression_release_bull",
        "family": "volatility",
        "direction": "bullish",
        "conditions": ("compression_release", "breakout_up"),
        "thesis": "A low-volatility range resolves upward.",
    },
    {
        "strategy_id": "compression_release_bear",
        "family": "volatility",
        "direction": "bearish",
        "conditions": ("compression_release", "breakout_down"),
        "thesis": "A low-volatility range resolves downward.",
    },
    {
        "strategy_id": "bollinger_reversion_bull",
        "family": "mean_reversion",
        "direction": "bullish",
        "conditions": ("reversion_up", "not_trend_down"),
        "thesis": "Price and RSI reach a downside statistical extreme outside a confirmed downtrend.",
    },
    {
        "strategy_id": "bollinger_reversion_bear",
        "family": "mean_reversion",
        "direction": "bearish",
        "conditions": ("reversion_down", "not_trend_up"),
        "thesis": "Price and RSI reach an upside statistical extreme outside a confirmed uptrend.",
    },
    {
        "strategy_id": "volume_reversal_bull",
        "family": "reversal",
        "direction": "bullish",
        "conditions": ("reversal_up", "volume_confirm_up"),
        "thesis": "A high-participation reversal closes back through the prior bar.",
    },
    {
        "strategy_id": "volume_reversal_bear",
        "family": "reversal",
        "direction": "bearish",
        "conditions": ("reversal_down", "volume_confirm_down"),
        "thesis": "A high-participation reversal closes back through the prior bar.",
    },
)


def _rolling_mean(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        output.append(None if index < period - 1 else running / period)
    return output


def _rolling_std(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = []
    for index in range(len(values)):
        if index < period - 1:
            output.append(None)
            continue
        window = values[index - period + 1 : index + 1]
        mean_value = sum(window) / period
        variance = sum((value - mean_value) ** 2 for value in window) / period
        output.append(math.sqrt(max(variance, 0.0)))
    return output


def _ema(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    current = sum(values[:period]) / period
    output[period - 1] = current
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        current = alpha * values[index] + (1.0 - alpha) * current
        output[index] = current
    return output


def _rsi(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return output
    gains = [max(values[index] - values[index - 1], 0.0) for index in range(1, len(values))]
    losses = [max(values[index - 1] - values[index], 0.0) for index in range(1, len(values))]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    output[period] = _rsi_value(average_gain, average_loss)
    for index in range(period + 1, len(values)):
        average_gain = (average_gain * (period - 1) + gains[index - 1]) / period
        average_loss = (average_loss * (period - 1) + losses[index - 1]) / period
        output[index] = _rsi_value(average_gain, average_loss)
    return output


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0.0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def _previous_extreme(values: Sequence[float], period: int, use_maximum: bool) -> list[float | None]:
    output: list[float | None] = []
    reducer = max if use_maximum else min
    for index in range(len(values)):
        output.append(None if index < period else reducer(values[index - period : index]))
    return output


def _feature_states(rows: Sequence[Bar]) -> dict[str, list[bool]]:
    closes = [float(row["adjusted_close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    sma20 = _rolling_mean(closes, 20)
    sma50 = _rolling_mean(closes, 50)
    sma200 = _rolling_mean(closes, 200)
    std20 = _rolling_std(closes, 20)
    ema12 = _ema(closes, 12)
    ema20 = _ema(closes, 20)
    ema26 = _ema(closes, 26)
    rsi14 = _rsi(closes, 14)
    volume20 = _rolling_mean(volumes, 20)
    prior_high20 = _previous_extreme(highs, 20, True)
    prior_low20 = _previous_extreme(lows, 20, False)
    bandwidth: list[float | None] = []
    for mean_value, deviation in zip(sma20, std20):
        bandwidth.append(
            None
            if mean_value is None or deviation is None or mean_value <= 0.0
            else 4.0 * deviation / mean_value
        )
    states = {name: [False] * len(rows) for name in (
        "trend_up",
        "trend_down",
        "not_trend_up",
        "not_trend_down",
        "momentum_up",
        "momentum_down",
        "pullback_up",
        "pullback_down",
        "breakout_up",
        "breakout_down",
        "volume_confirm_up",
        "volume_confirm_down",
        "compression_release",
        "reversion_up",
        "reversion_down",
        "reversal_up",
        "reversal_down",
    )}
    for index in range(len(rows)):
        required = (sma20[index], sma50[index], sma200[index], ema12[index], ema20[index], ema26[index], rsi14[index])
        if any(value is None for value in required):
            continue
        close = closes[index]
        prior_close = closes[index - 1] if index > 0 else close
        mean20 = float(sma20[index])
        mean50 = float(sma50[index])
        mean200 = float(sma200[index])
        fast = float(ema12[index])
        trend = float(ema20[index])
        slow = float(ema26[index])
        rsi_value = float(rsi14[index])
        trend_up = close > trend > mean50 > mean200
        trend_down = close < trend < mean50 < mean200
        states["trend_up"][index] = trend_up
        states["trend_down"][index] = trend_down
        states["not_trend_up"][index] = not trend_up
        states["not_trend_down"][index] = not trend_down
        states["momentum_up"][index] = fast > slow and 52.0 <= rsi_value <= 76.0
        states["momentum_down"][index] = fast < slow and 24.0 <= rsi_value <= 48.0
        states["pullback_up"][index] = close <= trend * 1.015 and close >= mean50 * 0.98 and 38.0 <= rsi_value <= 58.0
        states["pullback_down"][index] = close >= trend * 0.985 and close <= mean50 * 1.02 and 42.0 <= rsi_value <= 62.0
        states["breakout_up"][index] = prior_high20[index] is not None and close > float(prior_high20[index])
        states["breakout_down"][index] = prior_low20[index] is not None and close < float(prior_low20[index])
        volume_ratio = 0.0 if volume20[index] in {None, 0.0} else volumes[index] / float(volume20[index])
        states["volume_confirm_up"][index] = volume_ratio >= 1.2 and close > prior_close
        states["volume_confirm_down"][index] = volume_ratio >= 1.2 and close < prior_close
        if index >= 120 and bandwidth[index - 1] is not None:
            history = sorted(float(value) for value in bandwidth[index - 120 : index] if value is not None)
            if history:
                threshold = history[max(0, int(len(history) * 0.20) - 1)]
                states["compression_release"][index] = float(bandwidth[index - 1]) <= threshold
        deviation = std20[index]
        if deviation is not None:
            lower = mean20 - 2.0 * float(deviation)
            upper = mean20 + 2.0 * float(deviation)
            states["reversion_up"][index] = close < lower and rsi_value <= 32.0
            states["reversion_down"][index] = close > upper and rsi_value >= 68.0
        if index > 0:
            prior = rows[index - 1]
            states["reversal_up"][index] = float(rows[index]["low"]) < float(prior["low"]) and close > float(prior["close"])
            states["reversal_down"][index] = float(rows[index]["high"]) > float(prior["high"]) and close < float(prior["close"])
    return states


def _recipe_signal(recipe: StrategyRecipe, states: dict[str, list[bool]], index: int) -> bool:
    return all(states[condition][index] for condition in recipe["conditions"])


def _strategy_trades(
    rows: Sequence[Bar],
    states: dict[str, list[bool]],
    recipe: StrategyRecipe,
    horizon_days: int,
    cost_rate: float,
) -> list[StrategyTrade]:
    trades: list[StrategyTrade] = []
    start_index = 200
    last_signal_index = -horizon_days
    direction_multiplier = 1.0 if recipe["direction"] == "bullish" else -1.0
    final_signal_index = len(rows) - horizon_days - 2
    for index in range(start_index, max(start_index, final_signal_index + 1)):
        if index - last_signal_index < horizon_days or not _recipe_signal(recipe, states, index):
            continue
        entry_index = index + 1
        exit_index = entry_index + horizon_days
        entry_price = float(rows[entry_index]["adjusted_close"])
        exit_price = float(rows[exit_index]["adjusted_close"])
        gross_return = direction_multiplier * (exit_price / entry_price - 1.0)
        random_index = max(start_index + 1, entry_index - 7)
        random_exit_index = min(random_index + horizon_days, len(rows) - 1)
        random_entry = float(rows[random_index]["adjusted_close"])
        random_exit = float(rows[random_exit_index]["adjusted_close"])
        random_return = direction_multiplier * (random_exit / random_entry - 1.0) - cost_rate
        trades.append(
            {
                "signal_date": str(rows[index]["date"]),
                "entry_date": str(rows[entry_index]["date"]),
                "exit_date": str(rows[exit_index]["date"]),
                "direction": recipe["direction"],
                "entry_price": round(entry_price, 8),
                "exit_price": round(exit_price, 8),
                "net_return": round(gross_return - cost_rate, 8),
                "random_entry_net_return": round(random_return, 8),
            }
        )
        last_signal_index = index
    return trades


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = _mean(values)
    return math.sqrt(sum((value - mean_value) ** 2 for value in values) / (len(values) - 1))


def _maximum_drawdown(returns: Sequence[float]) -> float:
    wealth = 1.0
    peak = 1.0
    maximum = 0.0
    for value in returns:
        wealth *= max(0.0, 1.0 + value)
        peak = max(peak, wealth)
        maximum = max(maximum, 1.0 - wealth / peak)
    return maximum


def _profit_factor(returns: Sequence[float]) -> float | None:
    gains = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    return None if losses == 0.0 else gains / losses


def _fold_metrics(returns: Sequence[float], fold_count: int) -> list[dict[str, float | int]]:
    metrics: list[dict[str, float | int]] = []
    for fold_index in range(fold_count):
        start = len(returns) * fold_index // fold_count
        end = len(returns) * (fold_index + 1) // fold_count
        fold = list(returns[start:end])
        metrics.append(
            {
                "fold": fold_index + 1,
                "sample_count": len(fold),
                "mean_net_return": round(_mean(fold), 8),
                "hit_rate": round(sum(value > 0.0 for value in fold) / len(fold), 6) if fold else 0.0,
            }
        )
    return metrics


def _score_recipe(
    recipe: StrategyRecipe,
    trades: list[StrategyTrade],
    trial_count: int,
    current_signal: bool,
) -> dict[str, object]:
    returns = [float(trade["net_return"]) for trade in trades]
    random_returns = [float(trade["random_entry_net_return"]) for trade in trades]
    mean_return = _mean(returns)
    standard_deviation = _sample_std(returns)
    standard_error = standard_deviation / math.sqrt(len(returns)) if returns else 0.0
    naive_lower_bound = mean_return - 1.96 * standard_error
    selection_penalty = standard_error * math.sqrt(2.0 * math.log(max(trial_count, 2)))
    selection_adjusted = mean_return - selection_penalty
    folds = _fold_metrics(returns, CHRONOLOGICAL_FOLD_COUNT)
    populated_folds = [fold for fold in folds if int(fold["sample_count"]) > 0]
    positive_fold_rate = (
        sum(float(fold["mean_net_return"]) > 0.0 for fold in populated_folds) / len(populated_folds)
        if populated_folds
        else 0.0
    )
    worst_fold = min((float(fold["mean_net_return"]) for fold in populated_folds), default=0.0)
    sample_sufficient = len(returns) >= 40
    robust_historical_support = (
        sample_sufficient
        and selection_adjusted > 0.0
        and positive_fold_rate >= 0.75
        and worst_fold > -0.01
    )
    evidence_status = (
        "historically_supported_not_forward_proven"
        if robust_historical_support
        else "insufficient_historical_sample"
        if not sample_sufficient
        else "historically_fragile_or_selection_adjusted_nonpositive"
    )
    stability_score = max(0.0, min(1.0, positive_fold_rate * 0.7 + (0.3 if worst_fold >= 0.0 else 0.0)))
    return_score = 0.5 + 0.5 * math.tanh(selection_adjusted * 20.0)
    robustness_score = max(0.0, min(1.0, 0.45 * return_score + 0.35 * stability_score + 0.20 * min(len(returns) / 80.0, 1.0)))
    record: dict[str, object] = {
        **recipe,
        "current_signal_active": current_signal,
        "sample_count": len(returns),
        "mean_net_return": round(mean_return, 8),
        "median_net_return": round(median(returns), 8) if returns else 0.0,
        "hit_rate": round(sum(value > 0.0 for value in returns) / len(returns), 6) if returns else 0.0,
        "profit_factor": None if (factor := _profit_factor(returns)) is None else round(factor, 6),
        "maximum_sequential_drawdown": round(_maximum_drawdown(returns), 6),
        "random_entry_mean_net_return": round(_mean(random_returns), 8),
        "incremental_mean_over_random_entry": round(mean_return - _mean(random_returns), 8),
        "naive_95pct_lower_bound": round(naive_lower_bound, 8),
        "multiple_testing_penalty": round(selection_penalty, 8),
        "selection_adjusted_mean": round(selection_adjusted, 8),
        "positive_fold_rate": round(positive_fold_rate, 6),
        "worst_fold_mean": round(worst_fold, 8),
        "folds": folds,
        "robustness_score": round(robustness_score, 6),
        "evidence_status": evidence_status,
        "promotion_allowed": False,
    }
    record["result_hash"] = canonical_hash(record)
    return record


def evaluate_symbol_strategies(rows: Sequence[Bar]) -> dict[str, object]:
    """Evaluate independent recipe families with past-only, delayed, non-overlapping entries."""

    if len(rows) < 260:
        raise ValueError(f"symbol strategy research requires at least 260 bars: bars={len(rows)}")
    states = _feature_states(rows)
    results = [
        _score_recipe(
            recipe,
            _strategy_trades(rows, states, recipe, FORWARD_HORIZON_DAYS, ROUND_TRIP_COST_RATE),
            len(STRATEGY_RECIPES),
            _recipe_signal(recipe, states, len(rows) - 1),
        )
        for recipe in STRATEGY_RECIPES
    ]
    results.sort(
        key=lambda record: (
            -int(bool(record["current_signal_active"])),
            -float(record["robustness_score"]),
            str(record["strategy_id"]),
        )
    )
    active = [record for record in results if record["current_signal_active"] is True]
    body: dict[str, object] = {
        "artifact_type": "symbol_strategy_combination_research",
        "research_version": SYMBOL_STRATEGY_RESEARCH_VERSION,
        "as_of_date": str(rows[-1]["date"]),
        "bar_count": len(rows),
        "recipe_trial_count": len(STRATEGY_RECIPES),
        "forward_horizon_trading_days": FORWARD_HORIZON_DAYS,
        "round_trip_cost_rate": ROUND_TRIP_COST_RATE,
        "chronological_fold_count": CHRONOLOGICAL_FOLD_COUNT,
        "entry_policy": "signal_at_close_then_delayed_entry_at_next_adjusted_close",
        "overlap_policy": "one_entry_per_recipe_per_forward_horizon",
        "multiple_testing_policy": "normal_extreme_value_selection_penalty_reported_for_every_recipe",
        "random_control_policy": "matched_direction_entry_shifted_seven_sessions_earlier",
        "current_active_strategy_ids": [str(record["strategy_id"]) for record in active],
        "strategy_results": results,
        "historical_testing_is_not_forward_proof": True,
        "synthetic_data_used": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "research_hash": canonical_hash(body)}
