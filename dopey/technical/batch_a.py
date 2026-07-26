"""Leak-safe Batch A technical primitives.

Existing foundry implementations are reused where available. Missing Batch A
primitives are implemented here as deterministic, warm-up-aware measurements.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dopey_analysis.indicator_foundry import (
    bollinger_pct_b,
    macd_histogram,
    obv_slope,
    rate_of_change,
    rsi,
)
from dopey_equity_swing.market_structure import Bar


IndicatorFunction = Callable[[Sequence[Bar], int], float | None]


@dataclass(frozen=True)
class IndicatorSpec:
    indicator: str
    formula_version: str
    required_lookback: int
    warmup_period: int
    missing_data_behavior: str
    normalization_method: str
    timeframe_compatibility: tuple[str, ...]
    limitations: tuple[str, ...]
    calculate: IndicatorFunction


def _series(rows: Sequence[Bar], field: str) -> list[float]:
    return [float(row[field]) for row in rows]


def _rsi(rows: Sequence[Bar], index: int) -> float | None:
    if index < 14:
        return None
    return rsi(_series(rows, "close"), index, 14)


def _macd_histogram(rows: Sequence[Bar], index: int) -> float | None:
    if index < 35:
        return None
    return macd_histogram(_series(rows, "close"), index)


def _stochastic_rsi(rows: Sequence[Bar], index: int) -> float | None:
    period = 14
    if index < period * 2:
        return None
    closes = _series(rows, "close")
    values = [rsi(closes, position, period) for position in range(index - period + 1, index + 1)]
    minimum = min(values)
    maximum = max(values)
    return 50.0 if maximum == minimum else 100.0 * (values[-1] - minimum) / (maximum - minimum)


def _true_range(rows: Sequence[Bar], index: int) -> float:
    current = rows[index]
    prior_close = float(rows[index - 1]["close"])
    return max(
        float(current["high"]) - float(current["low"]),
        abs(float(current["high"]) - prior_close),
        abs(float(current["low"]) - prior_close),
    )


def _atr(rows: Sequence[Bar], index: int, period: int) -> float | None:
    if index < period:
        return None
    values = [_true_range(rows, position) for position in range(index - period + 1, index + 1)]
    return sum(values) / len(values)


def _normalized_atr(rows: Sequence[Bar], index: int) -> float | None:
    atr_value = _atr(rows, index, 14)
    close = float(rows[index]["close"])
    if atr_value is None or close <= 0.0:
        return None
    return atr_value / close


def _directional_components(rows: Sequence[Bar], index: int, period: int) -> tuple[float, float, float] | None:
    if index < period * 2:
        return None
    start = index - period * 2 + 1
    true_ranges: list[float] = []
    positive_moves: list[float] = []
    negative_moves: list[float] = []
    for position in range(max(start, 1), index + 1):
        high_move = float(rows[position]["high"]) - float(rows[position - 1]["high"])
        low_move = float(rows[position - 1]["low"]) - float(rows[position]["low"])
        positive_moves.append(high_move if high_move > low_move and high_move > 0.0 else 0.0)
        negative_moves.append(low_move if low_move > high_move and low_move > 0.0 else 0.0)
        true_ranges.append(_true_range(rows, position))
    if len(true_ranges) < period * 2:
        return None
    dx_values: list[float] = []
    latest_plus = 0.0
    latest_minus = 0.0
    for offset in range(period - 1, len(true_ranges)):
        tr_sum = sum(true_ranges[offset - period + 1 : offset + 1])
        if tr_sum <= 0.0:
            dx_values.append(0.0)
            continue
        latest_plus = 100.0 * sum(positive_moves[offset - period + 1 : offset + 1]) / tr_sum
        latest_minus = 100.0 * sum(negative_moves[offset - period + 1 : offset + 1]) / tr_sum
        denominator = latest_plus + latest_minus
        dx_values.append(0.0 if denominator == 0.0 else 100.0 * abs(latest_plus - latest_minus) / denominator)
    adx_value = sum(dx_values[-period:]) / min(len(dx_values), period)
    return latest_plus, latest_minus, adx_value


def _adx(rows: Sequence[Bar], index: int) -> float | None:
    components = _directional_components(rows, index, 14)
    return None if components is None else components[2]


def _dmi_spread(rows: Sequence[Bar], index: int) -> float | None:
    components = _directional_components(rows, index, 14)
    return None if components is None else components[0] - components[1]


def _bollinger_percent_b(rows: Sequence[Bar], index: int) -> float | None:
    if index < 19:
        return None
    return bollinger_pct_b(_series(rows, "close"), index, 20)


def _obv_slope(rows: Sequence[Bar], index: int) -> float | None:
    if index < 20:
        return None
    return obv_slope(_series(rows, "close"), _series(rows, "volume"), index, 20)


def _chaikin_money_flow(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period - 1:
        return None
    money_flow_volume = 0.0
    volume_total = 0.0
    for row in rows[index - period + 1 : index + 1]:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row["volume"])
        multiplier = 0.0 if high == low else ((close - low) - (high - close)) / (high - low)
        money_flow_volume += multiplier * volume
        volume_total += volume
    return 0.0 if volume_total == 0.0 else money_flow_volume / volume_total


def _money_flow_index(rows: Sequence[Bar], index: int) -> float | None:
    period = 14
    if index < period:
        return None
    positive_flow = 0.0
    negative_flow = 0.0
    for position in range(index - period + 1, index + 1):
        current = rows[position]
        prior = rows[position - 1]
        typical = (float(current["high"]) + float(current["low"]) + float(current["close"])) / 3.0
        prior_typical = (float(prior["high"]) + float(prior["low"]) + float(prior["close"])) / 3.0
        flow = typical * float(current["volume"])
        if typical > prior_typical:
            positive_flow += flow
        elif typical < prior_typical:
            negative_flow += flow
    if negative_flow == 0.0:
        return 100.0 if positive_flow > 0.0 else 50.0
    ratio = positive_flow / negative_flow
    return 100.0 - 100.0 / (1.0 + ratio)


def _rolling_vwap_distance(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period - 1:
        return None
    window = rows[index - period + 1 : index + 1]
    volume_total = sum(float(row["volume"]) for row in window)
    if volume_total <= 0.0:
        return None
    vwap = sum(
        ((float(row["high"]) + float(row["low"]) + float(row["close"])) / 3.0)
        * float(row["volume"])
        for row in window
    ) / volume_total
    close = float(rows[index]["close"])
    return None if vwap == 0.0 else close / vwap - 1.0


def _calendar_year_anchor_index(rows: Sequence[Bar], index: int) -> int:
    year = str(rows[index]["date"])[:4]
    anchor = index
    while anchor > 0 and str(rows[anchor - 1]["date"])[:4] == year:
        anchor -= 1
    return anchor


def _anchored_vwap_distance(rows: Sequence[Bar], index: int) -> float | None:
    anchor = _calendar_year_anchor_index(rows, index)
    window = rows[anchor : index + 1]
    if len(window) < 5:
        return None
    volume_total = sum(float(row["volume"]) for row in window)
    if volume_total <= 0.0:
        return None
    vwap = sum(
        ((float(row["high"]) + float(row["low"]) + float(row["close"])) / 3.0)
        * float(row["volume"])
        for row in window
    ) / volume_total
    close = float(rows[index]["close"])
    return None if vwap == 0.0 else close / vwap - 1.0


def _rate_of_change(rows: Sequence[Bar], index: int) -> float | None:
    if index < 10:
        return None
    return rate_of_change(_series(rows, "close"), index, 10)


def _commodity_channel_index(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period - 1:
        return None
    typical_prices = [
        (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3.0
        for row in rows[index - period + 1 : index + 1]
    ]
    mean = sum(typical_prices) / period
    deviation = sum(abs(value - mean) for value in typical_prices) / period
    return 0.0 if deviation == 0.0 else (typical_prices[-1] - mean) / (0.015 * deviation)


def _spec(
    indicator: str,
    formula_version: str,
    required_lookback: int,
    warmup_period: int,
    limitations: tuple[str, ...],
    calculate: IndicatorFunction,
) -> IndicatorSpec:
    return IndicatorSpec(
        indicator=indicator,
        formula_version=formula_version,
        required_lookback=required_lookback,
        warmup_period=warmup_period,
        missing_data_behavior="return_null_until_warmup_or_required_volume",
        normalization_method="within_timeframe_trailing_empirical_percentile",
        timeframe_compatibility=("daily", "weekly", "monthly"),
        limitations=limitations,
        calculate=calculate,
    )


BATCH_A_SPECS: tuple[IndicatorSpec, ...] = (
    _spec("RSI", "wilder-rsi-14-v1", 15, 14, ("bounded_momentum",), _rsi),
    _spec("MACD_HISTOGRAM", "ema-12-26-9-v1", 36, 35, ("lagging_indicator",), _macd_histogram),
    _spec("STOCHASTIC_RSI", "stochastic-rsi-14-v1", 29, 28, ("double_smoothed_momentum",), _stochastic_rsi),
    _spec("ADX", "directional-index-14-v1", 29, 28, ("trend_strength_not_direction",), _adx),
    _spec("DMI_SPREAD", "plus-minus-di-14-v1", 29, 28, ("trend_direction_not_thesis",), _dmi_spread),
    _spec("NORMALIZED_ATR", "true-range-14-close-normalized-v1", 15, 14, ("historical_volatility_proxy",), _normalized_atr),
    _spec("BOLLINGER_PERCENT_B", "bollinger-20-2-population-v1", 20, 19, ("distribution_assumption",), _bollinger_percent_b),
    _spec("OBV_SLOPE", "obv-slope-20-v1", 21, 20, ("daily_volume_not_signed_flow",), _obv_slope),
    _spec("CHAIKIN_MONEY_FLOW", "cmf-20-v1", 20, 19, ("close_location_volume_proxy",), _chaikin_money_flow),
    _spec("MONEY_FLOW_INDEX", "mfi-14-v1", 15, 14, ("price_volume_proxy",), _money_flow_index),
    _spec("VWAP_DISTANCE", "rolling-typical-price-vwap-20-v1", 20, 19, ("daily_bar_vwap_proxy_not_intraday_vwap",), _rolling_vwap_distance),
    _spec("ANCHORED_VWAP_DISTANCE", "calendar-year-anchored-vwap-v1", 5, 4, ("calendar_year_anchor", "daily_bar_vwap_proxy"), _anchored_vwap_distance),
    _spec("ROC", "rate-of-change-10-v1", 11, 10, ("unbounded_momentum",), _rate_of_change),
    _spec("CCI", "commodity-channel-index-20-v1", 20, 19, ("mean_deviation_oscillator",), _commodity_channel_index),
)


def calculate_indicator_series(spec: IndicatorSpec, rows: Sequence[Bar]) -> list[float | None]:
    values: list[float | None] = []
    for index in range(len(rows)):
        value = spec.calculate(rows, index)
        if value is not None and not math.isfinite(value):
            raise ValueError(
                "indicator produced a non-finite value: "
                f"indicator={spec.indicator}, index={index}, value={value}"
            )
        values.append(value)
    return values
