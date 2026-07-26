"""Versioned Batch C adaptive-trend, momentum, and participation diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence

from dopey_equity_swing.market_structure import Bar

from .batch_a import IndicatorFunction, IndicatorSpec


def _values(rows: Sequence[Bar], field: str, index: int) -> list[float]:
    return [float(row[field]) for row in rows[: index + 1]]


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    result = sum(values[:period]) / period
    alpha = 2.0 / (period + 1.0)
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    result = sum(values[:period]) / period
    output = [result]
    alpha = 2.0 / (period + 1.0)
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
        output.append(result)
    return output


def _wma(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    denominator = period * (period + 1) / 2.0
    return sum((index + 1) * value for index, value in enumerate(window)) / denominator


def _hma_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    closes = _values(rows, "close", index)
    if len(closes) < period + int(math.sqrt(period)):
        return None
    synthetic: list[float] = []
    for end in range(period, len(closes) + 1):
        half = _wma(closes[:end], period // 2)
        full = _wma(closes[:end], period)
        if half is not None and full is not None:
            synthetic.append(2.0 * half - full)
    hull = _wma(synthetic, int(math.sqrt(period)))
    close = closes[-1]
    return None if hull is None or close == 0.0 else close / hull - 1.0


def _kama_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 10
    closes = _values(rows, "close", index)
    if len(closes) <= period:
        return None
    kama = closes[period]
    fast = 2.0 / 3.0
    slow = 2.0 / 31.0
    for position in range(period + 1, len(closes)):
        change = abs(closes[position] - closes[position - period])
        volatility = sum(abs(closes[offset] - closes[offset - 1]) for offset in range(position - period + 1, position + 1))
        efficiency = 0.0 if volatility == 0.0 else change / volatility
        smoothing = (efficiency * (fast - slow) + slow) ** 2
        kama += smoothing * (closes[position] - kama)
    return None if kama == 0.0 else closes[-1] / kama - 1.0


def _zlema_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    lag = (period - 1) // 2
    closes = _values(rows, "close", index)
    if len(closes) < period + lag:
        return None
    adjusted = [closes[position] + (closes[position] - closes[position - lag]) for position in range(lag, len(closes))]
    value = _ema(adjusted, period)
    return None if value in {None, 0.0} else closes[-1] / value - 1.0


def _dema_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    closes = _values(rows, "close", index)
    if len(closes) < period * 2:
        return None
    finite = _ema_series(closes, period)
    first = finite[-1]
    second = _ema(finite, period)
    dema = None if second is None else 2.0 * first - second
    return None if dema in {None, 0.0} else closes[-1] / dema - 1.0


def _tema_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 15
    closes = _values(rows, "close", index)
    if len(closes) < period * 3:
        return None
    ema1 = _ema_series(closes, period)
    ema2 = _ema_series(ema1, period)
    ema3 = _ema(ema2, period)
    tema = None if ema3 is None else 3.0 * ema1[-1] - 3.0 * ema2[-1] + ema3
    return None if tema in {None, 0.0} else closes[-1] / tema - 1.0


def _linear_regression_slope(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    closes = _values(rows, "close", index)
    if len(closes) < period:
        return None
    y = closes[-period:]
    x_mean = (period - 1) / 2.0
    y_mean = sum(y) / period
    denominator = sum((position - x_mean) ** 2 for position in range(period))
    slope = sum((position - x_mean) * (value - y_mean) for position, value in enumerate(y)) / denominator
    return 0.0 if y_mean == 0.0 else slope / y_mean


def _ppo(rows: Sequence[Bar], index: int) -> float | None:
    closes = _values(rows, "close", index)
    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    return None if fast is None or slow in {None, 0.0} else 100.0 * (fast - slow) / slow


def _true_range(rows: Sequence[Bar], position: int) -> float:
    prior = float(rows[position - 1]["close"])
    return max(
        float(rows[position]["high"]) - float(rows[position]["low"]),
        abs(float(rows[position]["high"]) - prior),
        abs(float(rows[position]["low"]) - prior),
    )


def _buying_pressure(rows: Sequence[Bar], position: int) -> float:
    prior = float(rows[position - 1]["close"])
    return float(rows[position]["close"]) - min(float(rows[position]["low"]), prior)


def _ultimate_oscillator(rows: Sequence[Bar], index: int) -> float | None:
    if index < 28:
        return None
    def average(period: int) -> float:
        positions = range(index - period + 1, index + 1)
        tr = sum(_true_range(rows, position) for position in positions)
        return 0.5 if tr == 0.0 else sum(_buying_pressure(rows, position) for position in positions) / tr
    return 100.0 * (4.0 * average(7) + 2.0 * average(14) + average(28)) / 7.0


def _fisher_transform(rows: Sequence[Bar], index: int) -> float | None:
    period = 10
    if index < period - 1:
        return None
    window = rows[index - period + 1 : index + 1]
    prices = [(float(row["high"]) + float(row["low"])) / 2.0 for row in window]
    minimum = min(prices)
    maximum = max(prices)
    normalized = 0.0 if maximum == minimum else 2.0 * ((prices[-1] - minimum) / (maximum - minimum) - 0.5)
    bounded = max(-0.999, min(0.999, normalized))
    return 0.5 * math.log((1.0 + bounded) / (1.0 - bounded))


def _dpo(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    offset = period // 2 + 1
    closes = _values(rows, "close", index)
    if len(closes) < period + offset:
        return None
    average = sum(closes[-period:]) / period
    return 0.0 if average == 0.0 else closes[-offset] / average - 1.0


def _awesome_oscillator(rows: Sequence[Bar], index: int) -> float | None:
    if index < 33:
        return None
    medians = [(float(row["high"]) + float(row["low"])) / 2.0 for row in rows[: index + 1]]
    return sum(medians[-5:]) / 5.0 - sum(medians[-34:]) / 34.0


def _roc(closes: Sequence[float], period: int) -> float | None:
    return None if len(closes) <= period or closes[-period - 1] == 0.0 else 100.0 * (closes[-1] / closes[-period - 1] - 1.0)


def _kst(rows: Sequence[Bar], index: int) -> float | None:
    closes = _values(rows, "close", index)
    components = [(_roc(closes, period), weight) for period, weight in ((10, 1.0), (15, 2.0), (20, 3.0), (30, 4.0))]
    return None if any(value is None for value, _ in components) else sum(float(value) * weight for value, weight in components)


def _accumulation_distribution_slope(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period - 1:
        return None
    cumulative = 0.0
    values: list[float] = []
    for row in rows[index - period + 1 : index + 1]:
        high = float(row["high"])
        low = float(row["low"])
        multiplier = 0.0 if high == low else ((float(row["close"]) - low) - (high - float(row["close"]))) / (high - low)
        cumulative += multiplier * float(row["volume"])
        values.append(cumulative)
    scale = sum(float(row["volume"]) for row in rows[index - period + 1 : index + 1])
    return 0.0 if scale == 0.0 else (values[-1] - values[0]) / scale


def _ease_of_movement(rows: Sequence[Bar], index: int) -> float | None:
    period = 14
    if index < period:
        return None
    values: list[float] = []
    for position in range(index - period + 1, index + 1):
        midpoint_move = (
            (float(rows[position]["high"]) + float(rows[position]["low"]))
            - (float(rows[position - 1]["high"]) + float(rows[position - 1]["low"]))
        ) / 2.0
        range_value = float(rows[position]["high"]) - float(rows[position]["low"])
        volume = float(rows[position]["volume"])
        if range_value <= 0.0 or volume <= 0.0:
            return None
        box_ratio = volume / range_value
        values.append(midpoint_move / box_ratio)
    scale = max(sum(abs(value) for value in values) / len(values), 1e-12)
    return (sum(values) / len(values)) / scale


def _volume_oscillator(rows: Sequence[Bar], index: int) -> float | None:
    volumes = _values(rows, "volume", index)
    short = _ema(volumes, 14)
    long = _ema(volumes, 28)
    return None if short is None or long in {None, 0.0} else (short - long) / long


def _relative_volume(rows: Sequence[Bar], index: int) -> float | None:
    if index < 19:
        return None
    volumes = _values(rows, "volume", index)[-20:]
    baseline = sum(volumes[:-1]) / len(volumes[:-1])
    return None if baseline == 0.0 else volumes[-1] / baseline - 1.0


def _spec(
    indicator: str,
    version: str,
    lookback: int,
    limitations: tuple[str, ...],
    calculate: IndicatorFunction,
) -> IndicatorSpec:
    return IndicatorSpec(
        indicator=indicator,
        formula_version=version,
        required_lookback=lookback,
        warmup_period=lookback - 1,
        missing_data_behavior="return_null_until_warmup_or_required_volume",
        normalization_method="within_timeframe_trailing_empirical_percentile",
        timeframe_compatibility=("intraday", "daily", "weekly", "monthly"),
        limitations=limitations,
        calculate=calculate,
    )


BATCH_C_SPECS: tuple[IndicatorSpec, ...] = (
    _spec("HMA_DISTANCE", "hma-20-distance-v1", 24, ("adaptive_lag_reduction",), _hma_distance),
    _spec("KAMA_DISTANCE", "kama-10-2-30-distance-v1", 11, ("efficiency_ratio_adaptive",), _kama_distance),
    _spec("ZLEMA_DISTANCE", "zlema-20-distance-v1", 29, ("lag_adjusted_trend",), _zlema_distance),
    _spec("DEMA_DISTANCE", "dema-20-distance-v1", 40, ("lag_reduced_trend",), _dema_distance),
    _spec("TEMA_DISTANCE", "tema-15-distance-v1", 45, ("lag_reduced_trend",), _tema_distance),
    _spec("LINEAR_REGRESSION_SLOPE", "ols-slope-20-normalized-v1", 20, ("linear_window_assumption",), _linear_regression_slope),
    _spec("PPO", "ppo-12-26-v1", 26, ("relative_ema_momentum",), _ppo),
    _spec("ULTIMATE_OSCILLATOR", "ultimate-7-14-28-v1", 29, ("multi_horizon_momentum",), _ultimate_oscillator),
    _spec("FISHER_TRANSFORM", "fisher-midprice-10-v1", 10, ("rolling_extreme_normalization",), _fisher_transform),
    _spec("DPO", "dpo-20-v1", 31, ("detrended_cycle_proxy",), _dpo),
    _spec("AWESOME_OSCILLATOR", "awesome-5-34-v1", 34, ("median_price_momentum",), _awesome_oscillator),
    _spec("KST", "kst-10-15-20-30-v1", 31, ("weighted_multi_roc",), _kst),
    _spec("ACCUMULATION_DISTRIBUTION_SLOPE", "ad-slope-20-v1", 20, ("close_location_volume_proxy",), _accumulation_distribution_slope),
    _spec("EASE_OF_MOVEMENT", "eom-14-normalized-v1", 15, ("bar_volume_liquidity_proxy",), _ease_of_movement),
    _spec("VOLUME_OSCILLATOR", "volume-ema-14-28-v1", 28, ("reported_volume_only",), _volume_oscillator),
    _spec("RELATIVE_VOLUME", "relative-volume-20-v1", 20, ("time_of_day_not_applicable_on_daily_bars",), _relative_volume),
)
