"""Versioned participation, trend-efficiency, and cycle primitives."""

from __future__ import annotations

import math
from collections.abc import Sequence

from dopey_equity_swing.market_structure import Bar

from .batch_a import IndicatorFunction, IndicatorSpec


def _closes(rows: Sequence[Bar], index: int) -> list[float]:
    return [float(row["close"]) for row in rows[: index + 1]]


def _ema_series(values: Sequence[float], period: int) -> list[float | None]:
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


def _compact_ema(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    current = sum(values[:period]) / period
    output = [current]
    alpha = 2.0 / (period + 1.0)
    for observation in values[period:]:
        current = alpha * observation + (1.0 - alpha) * current
        output.append(current)
    return output


def _wma_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period - 1:
        return None
    window = _closes(rows, index)[-period:]
    denominator = period * (period + 1) / 2.0
    average = sum((offset + 1) * value for offset, value in enumerate(window)) / denominator
    close = window[-1]
    return None if average == 0.0 else close / average - 1.0


def _vwma_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period - 1:
        return None
    window = rows[index - period + 1 : index + 1]
    volume = sum(float(row["volume"]) for row in window)
    if volume <= 0.0:
        return None
    average = sum(float(row["close"]) * float(row["volume"]) for row in window) / volume
    return None if average == 0.0 else float(rows[index]["close"]) / average - 1.0


def _parabolic_sar_distance(rows: Sequence[Bar], index: int) -> float | None:
    if index < 5:
        return None
    bullish = float(rows[1]["close"]) >= float(rows[0]["close"])
    sar = float(rows[0]["low"] if bullish else rows[0]["high"])
    extreme = float(rows[0]["high"] if bullish else rows[0]["low"])
    acceleration = 0.02
    for position in range(1, index + 1):
        sar += acceleration * (extreme - sar)
        if bullish:
            sar = min(sar, float(rows[position - 1]["low"]))
            if position > 1:
                sar = min(sar, float(rows[position - 2]["low"]))
            if float(rows[position]["low"]) < sar:
                bullish = False
                sar = extreme
                extreme = float(rows[position]["low"])
                acceleration = 0.02
            elif float(rows[position]["high"]) > extreme:
                extreme = float(rows[position]["high"])
                acceleration = min(0.2, acceleration + 0.02)
        else:
            sar = max(sar, float(rows[position - 1]["high"]))
            if position > 1:
                sar = max(sar, float(rows[position - 2]["high"]))
            if float(rows[position]["high"]) > sar:
                bullish = True
                sar = extreme
                extreme = float(rows[position]["high"])
                acceleration = 0.02
            elif float(rows[position]["low"]) < extreme:
                extreme = float(rows[position]["low"])
                acceleration = min(0.2, acceleration + 0.02)
    close = float(rows[index]["close"])
    return None if close == 0.0 else (close - sar) / close


def _elder_power(rows: Sequence[Bar], index: int, field: str) -> float | None:
    closes = _closes(rows, index)
    ema_values = _ema_series(closes, 13)
    average = ema_values[-1]
    close = closes[-1]
    if average is None or close == 0.0:
        return None
    return (float(rows[index][field]) - average) / close


def _elder_bull_power(rows: Sequence[Bar], index: int) -> float | None:
    return _elder_power(rows, index, "high")


def _elder_bear_power(rows: Sequence[Bar], index: int) -> float | None:
    return _elder_power(rows, index, "low")


def _accumulation_distribution(rows: Sequence[Bar], index: int) -> list[float]:
    values: list[float] = []
    current = 0.0
    for row in rows[: index + 1]:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row["volume"])
        multiplier = 0.0 if high == low else ((close - low) - (high - close)) / (high - low)
        current += multiplier * volume
        values.append(current)
    return values


def _chaikin_oscillator(rows: Sequence[Bar], index: int) -> float | None:
    if index < 19:
        return None
    line = _accumulation_distribution(rows, index)
    fast = _ema_series(line, 3)[-1]
    slow = _ema_series(line, 10)[-1]
    mean_volume = sum(float(row["volume"]) for row in rows[index - 19 : index + 1]) / 20.0
    if fast is None or slow is None or mean_volume <= 0.0:
        return None
    return (fast - slow) / mean_volume


def _volume_index_momentum(rows: Sequence[Bar], index: int, update_on_lower_volume: bool) -> float | None:
    period = 20
    if index < period:
        return None
    values = [1000.0]
    for position in range(1, index + 1):
        prior_volume = float(rows[position - 1]["volume"])
        volume = float(rows[position]["volume"])
        lower = volume < prior_volume
        should_update = lower if update_on_lower_volume else not lower and volume > prior_volume
        prior_close = float(rows[position - 1]["close"])
        change = float(rows[position]["close"]) / prior_close - 1.0
        values.append(values[-1] * (1.0 + change) if should_update else values[-1])
    prior = values[-period - 1]
    return 0.0 if prior == 0.0 else values[-1] / prior - 1.0


def _negative_volume_index_momentum(rows: Sequence[Bar], index: int) -> float | None:
    return _volume_index_momentum(rows, index, True)


def _positive_volume_index_momentum(rows: Sequence[Bar], index: int) -> float | None:
    return _volume_index_momentum(rows, index, False)


def _true_range(rows: Sequence[Bar], index: int) -> float:
    if index == 0:
        return float(rows[0]["high"]) - float(rows[0]["low"])
    prior_close = float(rows[index - 1]["close"])
    return max(
        float(rows[index]["high"]) - float(rows[index]["low"]),
        abs(float(rows[index]["high"]) - prior_close),
        abs(float(rows[index]["low"]) - prior_close),
    )


def _choppiness_index(rows: Sequence[Bar], index: int) -> float | None:
    period = 14
    if index < period:
        return None
    positions = range(index - period + 1, index + 1)
    true_range_sum = sum(_true_range(rows, position) for position in positions)
    high = max(float(rows[position]["high"]) for position in positions)
    low = min(float(rows[position]["low"]) for position in positions)
    price_range = high - low
    if price_range <= 0.0 or true_range_sum <= 0.0:
        return 50.0
    return 100.0 * math.log10(true_range_sum / price_range) / math.log10(period)


def _mass_index(rows: Sequence[Bar], index: int) -> float | None:
    if index < 40:
        return None
    ranges = [float(row["high"]) - float(row["low"]) for row in rows[: index + 1]]
    first = _compact_ema(ranges, 9)
    second = _compact_ema(first, 9)
    if len(second) < 25:
        return None
    aligned_first = first[8:]
    ratios = [
        1.0 if denominator == 0.0 else numerator / denominator
        for numerator, denominator in zip(aligned_first, second, strict=True)
    ]
    return sum(ratios[-25:])


def _relative_vigor_index(rows: Sequence[Bar], index: int) -> float | None:
    period = 10
    if index < period - 1:
        return None
    window = rows[index - period + 1 : index + 1]
    numerator = sum(float(row["close"]) - float(row["open"]) for row in window)
    denominator = sum(float(row["high"]) - float(row["low"]) for row in window)
    return 0.0 if denominator == 0.0 else numerator / denominator


def _trix(rows: Sequence[Bar], index: int) -> float | None:
    closes = _closes(rows, index)
    first = _compact_ema(closes, 15)
    second = _compact_ema(first, 15)
    third = _compact_ema(second, 15)
    if len(third) < 2 or third[-2] == 0.0:
        return None
    return 100.0 * (third[-1] / third[-2] - 1.0)


def _schaff_trend_cycle(rows: Sequence[Bar], index: int) -> float | None:
    closes = _closes(rows, index)
    fast = _ema_series(closes, 23)
    slow = _ema_series(closes, 50)
    macd = [
        float(fast_value) - float(slow_value)
        for fast_value, slow_value in zip(fast, slow, strict=True)
        if fast_value is not None and slow_value is not None
    ]
    cycle = 10
    if len(macd) < cycle + 3:
        return None
    stochastic: list[float] = []
    for position in range(cycle - 1, len(macd)):
        window = macd[position - cycle + 1 : position + 1]
        low = min(window)
        high = max(window)
        stochastic.append(50.0 if high == low else 100.0 * (macd[position] - low) / (high - low))
    smoothed = _compact_ema(stochastic, 3)
    twice_smoothed = _compact_ema(smoothed, 3)
    return None if not twice_smoothed else max(0.0, min(100.0, twice_smoothed[-1]))


def _balance_of_power(rows: Sequence[Bar], index: int) -> float | None:
    high = float(rows[index]["high"])
    low = float(rows[index]["low"])
    return 0.0 if high == low else (float(rows[index]["close"]) - float(rows[index]["open"])) / (high - low)


def _spec(
    indicator: str,
    formula_version: str,
    required_lookback: int,
    limitations: tuple[str, ...],
    calculate: IndicatorFunction,
) -> IndicatorSpec:
    return IndicatorSpec(
        indicator=indicator,
        formula_version=formula_version,
        required_lookback=required_lookback,
        warmup_period=required_lookback - 1,
        missing_data_behavior="return_null_until_warmup_or_required_volume",
        normalization_method="within_timeframe_trailing_empirical_percentile",
        timeframe_compatibility=("daily", "weekly", "monthly"),
        limitations=limitations,
        calculate=calculate,
    )


BATCH_D_SPECS: tuple[IndicatorSpec, ...] = (
    _spec("WMA_DISTANCE", "wma-20-distance-v1", 20, ("fixed_linear_weights",), _wma_distance),
    _spec("VWMA_DISTANCE", "vwma-20-distance-v1", 20, ("reported_bar_volume_only",), _vwma_distance),
    _spec("PARABOLIC_SAR_DISTANCE", "wilder-psar-002-02-distance-v1", 6, ("path_dependent_trailing_stop_proxy",), _parabolic_sar_distance),
    _spec("ELDER_BULL_POWER", "elder-bull-power-ema13-normalized-v1", 13, ("trend_dependent_extreme_pressure",), _elder_bull_power),
    _spec("ELDER_BEAR_POWER", "elder-bear-power-ema13-normalized-v1", 13, ("trend_dependent_extreme_pressure",), _elder_bear_power),
    _spec("CHAIKIN_OSCILLATOR", "chaikin-adl-ema3-10-volume-normalized-v1", 20, ("close_location_volume_proxy",), _chaikin_oscillator),
    _spec("NEGATIVE_VOLUME_INDEX_MOMENTUM", "nvi-20-return-v1", 21, ("volume_direction_not_informed_flow",), _negative_volume_index_momentum),
    _spec("POSITIVE_VOLUME_INDEX_MOMENTUM", "pvi-20-return-v1", 21, ("volume_direction_not_informed_flow",), _positive_volume_index_momentum),
    _spec("CHOPPINESS_INDEX", "choppiness-14-v1", 15, ("range_efficiency_not_direction",), _choppiness_index),
    _spec("MASS_INDEX", "mass-index-9-25-v1", 41, ("range_reversal_watch_not_direction",), _mass_index),
    _spec("RELATIVE_VIGOR_INDEX", "rvi-10-v1", 10, ("bar_body_range_momentum",), _relative_vigor_index),
    _spec("TRIX", "trix-triple-ema15-v1", 44, ("triple_smoothed_lagging_momentum",), _trix),
    _spec("SCHAFF_TREND_CYCLE", "stc-23-50-10-3-3-v1", 65, ("bounded_macd_cycle_proxy",), _schaff_trend_cycle),
    _spec("BALANCE_OF_POWER", "balance-of-power-v1", 1, ("single_bar_pressure_proxy",), _balance_of_power),
)
