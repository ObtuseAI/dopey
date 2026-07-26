"""Versioned Batch B trend, momentum, channel, and volatility primitives."""

from __future__ import annotations

import math
from collections.abc import Sequence

from dopey_equity_swing.market_structure import Bar

from .batch_a import IndicatorFunction, IndicatorSpec


def _series(rows: Sequence[Bar], field: str, index: int) -> list[float]:
    return [float(row[field]) for row in rows[: index + 1]]


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    alpha = 2.0 / (period + 1.0)
    for observation in values[period:]:
        value = alpha * observation + (1.0 - alpha) * value
    return value


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    result = sum(values[:period]) / period
    output = [result]
    alpha = 2.0 / (period + 1.0)
    for observation in values[period:]:
        result = alpha * observation + (1.0 - alpha) * result
        output.append(result)
    return output


def _true_range(rows: Sequence[Bar], index: int) -> float:
    if index == 0:
        return float(rows[index]["high"]) - float(rows[index]["low"])
    prior_close = float(rows[index - 1]["close"])
    return max(
        float(rows[index]["high"]) - float(rows[index]["low"]),
        abs(float(rows[index]["high"]) - prior_close),
        abs(float(rows[index]["low"]) - prior_close),
    )


def _atr(rows: Sequence[Bar], index: int, period: int) -> float | None:
    if index < period:
        return None
    values = [_true_range(rows, position) for position in range(1, index + 1)]
    return _ema(values, period)


def _ichimoku_spread(rows: Sequence[Bar], index: int) -> float | None:
    if index < 25:
        return None
    conversion = (
        max(float(row["high"]) for row in rows[index - 8 : index + 1])
        + min(float(row["low"]) for row in rows[index - 8 : index + 1])
    ) / 2.0
    base = (
        max(float(row["high"]) for row in rows[index - 25 : index + 1])
        + min(float(row["low"]) for row in rows[index - 25 : index + 1])
    ) / 2.0
    close = float(rows[index]["close"])
    return None if close == 0.0 else (conversion - base) / close


def _supertrend_distance(rows: Sequence[Bar], index: int) -> float | None:
    atr = _atr(rows, index, 10)
    if atr is None:
        return None
    midpoint = (float(rows[index]["high"]) + float(rows[index]["low"])) / 2.0
    close = float(rows[index]["close"])
    reference = midpoint - 3.0 * atr if close >= midpoint else midpoint + 3.0 * atr
    return None if close == 0.0 else (close - reference) / close


def _aroon_oscillator(rows: Sequence[Bar], index: int) -> float | None:
    period = 25
    if index < period - 1:
        return None
    window = rows[index - period + 1 : index + 1]
    high_position = max(range(period), key=lambda offset: float(window[offset]["high"]))
    low_position = min(range(period), key=lambda offset: float(window[offset]["low"]))
    aroon_up = 100.0 * (period - 1 - (period - 1 - high_position)) / (period - 1)
    aroon_down = 100.0 * (period - 1 - (period - 1 - low_position)) / (period - 1)
    return aroon_up - aroon_down


def _vortex_spread(rows: Sequence[Bar], index: int) -> float | None:
    period = 14
    if index < period:
        return None
    positions = range(index - period + 1, index + 1)
    tr_total = sum(_true_range(rows, position) for position in positions)
    if tr_total == 0.0:
        return 0.0
    positive = sum(abs(float(rows[position]["high"]) - float(rows[position - 1]["low"])) for position in positions)
    negative = sum(abs(float(rows[position]["low"]) - float(rows[position - 1]["high"])) for position in positions)
    return positive / tr_total - negative / tr_total


def _donchian_position(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period - 1:
        return None
    window = rows[index - period + 1 : index + 1]
    upper = max(float(row["high"]) for row in window)
    lower = min(float(row["low"]) for row in window)
    return 0.5 if upper == lower else (float(rows[index]["close"]) - lower) / (upper - lower) - 0.5


def _keltner_position(rows: Sequence[Bar], index: int) -> float | None:
    closes = _series(rows, "close", index)
    center = _ema(closes, 20)
    atr = _atr(rows, index, 20)
    if center is None or atr is None or atr == 0.0:
        return None
    return (float(rows[index]["close"]) - center) / (2.0 * atr)


def _williams_r(rows: Sequence[Bar], index: int) -> float | None:
    period = 14
    if index < period - 1:
        return None
    window = rows[index - period + 1 : index + 1]
    highest = max(float(row["high"]) for row in window)
    lowest = min(float(row["low"]) for row in window)
    return -50.0 if highest == lowest else -100.0 * (highest - float(rows[index]["close"])) / (highest - lowest)


def _tsi(rows: Sequence[Bar], index: int) -> float | None:
    closes = _series(rows, "close", index)
    if len(closes) < 40:
        return None
    momentum = [closes[position] - closes[position - 1] for position in range(1, len(closes))]
    first = _ema_series(momentum, 25)
    first_abs = _ema_series([abs(value) for value in momentum], 25)
    numerator = _ema(first, 13)
    denominator = _ema(first_abs, 13)
    return None if numerator is None or denominator in {None, 0.0} else 100.0 * numerator / denominator


def _simple_rsi(values: Sequence[float], period: int) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[position] - values[position - 1] for position in range(len(values) - period, len(values))]
    gains = sum(max(change, 0.0) for change in changes) / period
    losses = sum(max(-change, 0.0) for change in changes) / period
    return 100.0 if losses == 0.0 else 100.0 - 100.0 / (1.0 + gains / losses)


def _connors_rsi(rows: Sequence[Bar], index: int) -> float | None:
    if index < 100:
        return None
    closes = _series(rows, "close", index)
    price_rsi = _simple_rsi(closes, 3)
    streaks: list[float] = [0.0]
    for position in range(1, len(closes)):
        direction = 1.0 if closes[position] > closes[position - 1] else -1.0 if closes[position] < closes[position - 1] else 0.0
        prior = streaks[-1]
        streaks.append(direction if direction == 0.0 or prior * direction <= 0.0 else prior + direction)
    streak_rsi = _simple_rsi(streaks, 2)
    returns = [closes[position] / closes[position - 1] - 1.0 for position in range(1, len(closes))]
    window = returns[-100:]
    rank = 100.0 * sum(value < window[-1] for value in window) / len(window)
    return None if price_rsi is None or streak_rsi is None else (price_rsi + streak_rsi + rank) / 3.0


def _force_index(rows: Sequence[Bar], index: int) -> float | None:
    if index < 13:
        return None
    raw = [
        (float(rows[position]["close"]) - float(rows[position - 1]["close"])) * float(rows[position]["volume"])
        for position in range(1, index + 1)
    ]
    value = _ema(raw, 13)
    scale = sum(float(row["volume"]) for row in rows[max(0, index - 12) : index + 1]) / 13.0
    return None if value is None or scale == 0.0 else value / scale


def _ulcer_index(rows: Sequence[Bar], index: int) -> float | None:
    period = 14
    if index < period - 1:
        return None
    closes = _series(rows, "close", index)[-period:]
    peak = 0.0
    squared: list[float] = []
    for close in closes:
        peak = max(peak, close)
        drawdown = 0.0 if peak == 0.0 else 100.0 * (close / peak - 1.0)
        squared.append(drawdown * drawdown)
    return math.sqrt(sum(squared) / len(squared))


def _volatility_window(rows: Sequence[Bar], index: int, period: int) -> Sequence[Bar] | None:
    return None if index < period else rows[index - period + 1 : index + 1]


def _parkinson(rows: Sequence[Bar], index: int) -> float | None:
    window = _volatility_window(rows, index, 20)
    if window is None:
        return None
    variance = sum(math.log(float(row["high"]) / float(row["low"])) ** 2 for row in window) / (4.0 * math.log(2.0) * len(window))
    return math.sqrt(max(0.0, variance) * 252.0)


def _garman_klass(rows: Sequence[Bar], index: int) -> float | None:
    window = _volatility_window(rows, index, 20)
    if window is None:
        return None
    values = [
        0.5 * math.log(float(row["high"]) / float(row["low"])) ** 2
        - (2.0 * math.log(2.0) - 1.0) * math.log(float(row["close"]) / float(row["open"])) ** 2
        for row in window
    ]
    return math.sqrt(max(0.0, sum(values) / len(values)) * 252.0)


def _rogers_satchell_value(row: Bar) -> float:
    high = float(row["high"])
    low = float(row["low"])
    open_value = float(row["open"])
    close = float(row["close"])
    return math.log(high / close) * math.log(high / open_value) + math.log(low / close) * math.log(low / open_value)


def _rogers_satchell(rows: Sequence[Bar], index: int) -> float | None:
    window = _volatility_window(rows, index, 20)
    if window is None:
        return None
    variance = sum(_rogers_satchell_value(row) for row in window) / len(window)
    return math.sqrt(max(0.0, variance) * 252.0)


def _variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _yang_zhang(rows: Sequence[Bar], index: int) -> float | None:
    period = 20
    if index < period:
        return None
    window = rows[index - period + 1 : index + 1]
    overnight = [
        math.log(float(rows[position]["open"]) / float(rows[position - 1]["close"]))
        for position in range(index - period + 1, index + 1)
    ]
    open_close = [math.log(float(row["close"]) / float(row["open"])) for row in window]
    rs = [_rogers_satchell_value(row) for row in window]
    weight = 0.34 / (1.34 + (period + 1.0) / (period - 1.0))
    variance = _variance(overnight) + weight * _variance(open_close) + (1.0 - weight) * sum(rs) / period
    return math.sqrt(max(0.0, variance) * 252.0)


def _historical_volatility(rows: Sequence[Bar], index: int) -> float | None:
    if index < 20:
        return None
    closes = _series(rows, "close", index)[-21:]
    log_returns = [math.log(closes[position] / closes[position - 1]) for position in range(1, len(closes))]
    return math.sqrt(_variance(log_returns) * 252.0)


def _bollinger_bandwidth(rows: Sequence[Bar], index: int) -> float | None:
    if index < 19:
        return None
    closes = _series(rows, "close", index)[-20:]
    mean = sum(closes) / len(closes)
    deviation = math.sqrt(sum((value - mean) ** 2 for value in closes) / len(closes))
    return None if mean == 0.0 else 4.0 * deviation / mean


def _keltner_width(rows: Sequence[Bar], index: int) -> float | None:
    center = _ema(_series(rows, "close", index), 20)
    atr = _atr(rows, index, 20)
    return None if center in {None, 0.0} or atr is None else 4.0 * atr / center


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


BATCH_B_SPECS: tuple[IndicatorSpec, ...] = (
    _spec("ICHIMOKU_TK_SPREAD", "ichimoku-9-26-normalized-v1", 26, ("lagging_and_level_based",), _ichimoku_spread),
    _spec("SUPERTREND_DISTANCE", "supertrend-10-3-distance-v1", 11, ("band_proxy_not_trade_signal",), _supertrend_distance),
    _spec("AROON_OSCILLATOR", "aroon-25-v1", 25, ("recency_of_extremes",), _aroon_oscillator),
    _spec("VORTEX_SPREAD", "vortex-14-v1", 15, ("trend_direction_proxy",), _vortex_spread),
    _spec("DONCHIAN_POSITION", "donchian-20-centered-v1", 20, ("range_position_not_breakout_truth",), _donchian_position),
    _spec("KELTNER_POSITION", "keltner-ema20-atr20-2-v1", 21, ("atr_channel_position",), _keltner_position),
    _spec("WILLIAMS_R", "williams-r-14-v1", 14, ("bounded_momentum",), _williams_r),
    _spec("TSI", "tsi-25-13-v1", 40, ("double_smoothed_momentum",), _tsi),
    _spec("CONNORS_RSI", "connors-rsi-3-2-100-v1", 101, ("short_term_composite_oscillator",), _connors_rsi),
    _spec("FORCE_INDEX", "force-index-ema13-volume-normalized-v1", 14, ("daily_volume_proxy",), _force_index),
    _spec("ULCER_INDEX", "ulcer-index-14-v1", 14, ("downside_path_risk",), _ulcer_index),
    _spec("PARKINSON_VOLATILITY", "parkinson-20-annualized-v1", 21, ("range_based_zero_drift_assumption",), _parkinson),
    _spec("GARMAN_KLASS_VOLATILITY", "garman-klass-20-annualized-v1", 21, ("continuous_sampling_assumption",), _garman_klass),
    _spec("ROGERS_SATCHELL_VOLATILITY", "rogers-satchell-20-annualized-v1", 21, ("range_based_estimator",), _rogers_satchell),
    _spec("YANG_ZHANG_VOLATILITY", "yang-zhang-20-annualized-v1", 21, ("overnight_and_range_estimator",), _yang_zhang),
    _spec("HISTORICAL_VOLATILITY", "close-log-return-20-annualized-v1", 21, ("close_to_close_estimator",), _historical_volatility),
    _spec("BOLLINGER_BANDWIDTH", "bollinger-bandwidth-20-2-v1", 20, ("compression_expansion_proxy",), _bollinger_bandwidth),
    _spec("KELTNER_WIDTH", "keltner-width-20-2-v1", 21, ("atr_compression_expansion_proxy",), _keltner_width),
)
