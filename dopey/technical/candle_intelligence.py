"""Leak-safe candlestick taxonomy and pivot-aligned divergence evidence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dopey_equity_swing.market_structure import Bar

from .batch_a import calculate_indicator_series
from .foundry import ALL_TECHNICAL_SPECS


CANDLESTICK_PATTERN_FAMILIES: tuple[str, ...] = (
    "doji",
    "spinning_top",
    "marubozu",
    "hammer_or_hanging_man",
    "inverted_hammer_or_shooting_star",
    "engulfing",
    "harami",
    "piercing_or_dark_cloud",
    "morning_or_evening_star",
    "three_soldiers_or_crows",
    "tweezer",
    "inside_or_outside_bar",
)

DIVERGENCE_OSCILLATORS: tuple[str, ...] = (
    "RSI",
    "MACD_HISTOGRAM",
    "MONEY_FLOW_INDEX",
    "OBV_SLOPE",
    "CHAIKIN_MONEY_FLOW",
    "PPO",
    "TSI",
    "RELATIVE_VIGOR_INDEX",
)


def _geometry(row: Bar) -> dict[str, float | str]:
    open_value = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    span = max(high - low, 1e-12)
    body = abs(close - open_value)
    return {
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "span": span,
        "body": body,
        "body_ratio": body / span,
        "upper_wick_ratio": (high - max(open_value, close)) / span,
        "lower_wick_ratio": (min(open_value, close) - low) / span,
        "direction": "bullish" if close > open_value else "bearish" if close < open_value else "neutral",
    }


def _trend_before(rows: Sequence[Bar], index: int) -> str:
    start = max(0, index - 10)
    closes = [float(row["close"]) for row in rows[start:index]]
    if len(closes) < 4 or closes[0] == 0.0:
        return "unknown"
    change = closes[-1] / closes[0] - 1.0
    return "uptrend" if change >= 0.02 else "downtrend" if change <= -0.02 else "sideways"


def _candle_candidate(
    pattern: str,
    index: int,
    rows: Sequence[Bar],
    directional_bias: str,
    probability: float,
    quality: float,
    evidence: dict[str, Any],
    failure_condition: str,
) -> dict[str, Any]:
    return {
        "pattern": pattern,
        "family": "candlestick",
        "bar_index": index,
        "as_of": str(rows[index]["date"]),
        "directional_bias": directional_bias,
        "probability": round(max(0.0, min(0.95, probability)), 6),
        "evidence_quality": round(max(0.0, min(1.0, quality)), 6),
        "evidence": evidence,
        "failure_condition": failure_condition,
        "pattern_is_not_truth": True,
        "not_trade_decision": True,
    }


def detect_candlestick_patterns(rows: Sequence[Bar], scan_bars: int) -> list[dict[str, Any]]:
    """Detect recent single- and multi-bar formations without future bars."""

    if scan_bars <= 0:
        raise ValueError(f"candlestick scan window must be positive: scan_bars={scan_bars}")
    if len(rows) < 3:
        return []
    candidates: list[dict[str, Any]] = []
    start = max(2, len(rows) - scan_bars)
    for index in range(start, len(rows)):
        current = _geometry(rows[index])
        prior = _geometry(rows[index - 1])
        older = _geometry(rows[index - 2])
        trend = _trend_before(rows, index)
        body_ratio = float(current["body_ratio"])
        upper = float(current["upper_wick_ratio"])
        lower = float(current["lower_wick_ratio"])
        direction = str(current["direction"])
        evidence = {
            "body_ratio": round(body_ratio, 6),
            "upper_wick_ratio": round(upper, 6),
            "lower_wick_ratio": round(lower, 6),
            "prior_trend": trend,
        }
        if body_ratio <= 0.1:
            subtype = "long_legged_doji" if upper >= 0.35 and lower >= 0.35 else "doji"
            candidates.append(_candle_candidate(subtype, index, rows, "neutral", 0.52, 0.58, evidence, "next bars accept beyond the doji range"))
        elif body_ratio <= 0.35 and upper >= 0.2 and lower >= 0.2:
            candidates.append(_candle_candidate("spinning_top", index, rows, "neutral", 0.5, 0.52, evidence, "directional follow-through resolves indecision"))
        if body_ratio >= 0.82 and upper <= 0.1 and lower <= 0.1:
            candidates.append(_candle_candidate(f"{direction}_marubozu", index, rows, direction, 0.61, 0.69, evidence, "price closes back through the candle midpoint"))
        if body_ratio <= 0.45 and lower >= 0.55 and upper <= 0.2:
            pattern = "hammer" if trend == "downtrend" else "hanging_man" if trend == "uptrend" else "lower_rejection_candle"
            bias = "bullish" if pattern == "hammer" else "bearish" if pattern == "hanging_man" else "neutral"
            candidates.append(_candle_candidate(pattern, index, rows, bias, 0.59, 0.66, evidence, "price closes beyond the rejection wick extreme"))
        if body_ratio <= 0.45 and upper >= 0.55 and lower <= 0.2:
            pattern = "inverted_hammer" if trend == "downtrend" else "shooting_star" if trend == "uptrend" else "upper_rejection_candle"
            bias = "bullish" if pattern == "inverted_hammer" else "bearish" if pattern == "shooting_star" else "neutral"
            candidates.append(_candle_candidate(pattern, index, rows, bias, 0.59, 0.66, evidence, "price closes beyond the rejection wick extreme"))

        current_open = float(current["open"])
        current_close = float(current["close"])
        prior_open = float(prior["open"])
        prior_close = float(prior["close"])
        current_body_low = min(current_open, current_close)
        current_body_high = max(current_open, current_close)
        prior_body_low = min(prior_open, prior_close)
        prior_body_high = max(prior_open, prior_close)
        if direction == "bullish" and prior["direction"] == "bearish" and current_body_low <= prior_body_low and current_body_high >= prior_body_high:
            candidates.append(_candle_candidate("bullish_engulfing", index, rows, "bullish", 0.64, 0.72, {**evidence, "engulfed_prior_body": True}, "close falls below the engulfing candle midpoint"))
        if direction == "bearish" and prior["direction"] == "bullish" and current_body_low <= prior_body_low and current_body_high >= prior_body_high:
            candidates.append(_candle_candidate("bearish_engulfing", index, rows, "bearish", 0.64, 0.72, {**evidence, "engulfed_prior_body": True}, "close rises above the engulfing candle midpoint"))
        if current_body_low >= prior_body_low and current_body_high <= prior_body_high and str(prior["direction"]) != direction:
            candidates.append(_candle_candidate(f"{direction}_harami", index, rows, direction, 0.55, 0.61, {**evidence, "inside_prior_body": True}, "price breaks the parent candle in the opposite direction"))
        prior_midpoint = (prior_open + prior_close) / 2.0
        if prior["direction"] == "bearish" and direction == "bullish" and current_open < prior_close and current_close > prior_midpoint and current_close < prior_open:
            candidates.append(_candle_candidate("piercing_line", index, rows, "bullish", 0.6, 0.68, evidence, "close falls below the two-bar low"))
        if prior["direction"] == "bullish" and direction == "bearish" and current_open > prior_close and current_close < prior_midpoint and current_close > prior_open:
            candidates.append(_candle_candidate("dark_cloud_cover", index, rows, "bearish", 0.6, 0.68, evidence, "close rises above the two-bar high"))

        older_body = float(older["body"])
        prior_body = float(prior["body"])
        older_midpoint = (float(older["open"]) + float(older["close"])) / 2.0
        if older["direction"] == "bearish" and prior_body <= older_body * 0.45 and direction == "bullish" and current_close > older_midpoint:
            candidates.append(_candle_candidate("morning_star", index, rows, "bullish", 0.66, 0.74, {**evidence, "three_bar_reversal": True}, "close falls below the star low"))
        if older["direction"] == "bullish" and prior_body <= older_body * 0.45 and direction == "bearish" and current_close < older_midpoint:
            candidates.append(_candle_candidate("evening_star", index, rows, "bearish", 0.66, 0.74, {**evidence, "three_bar_reversal": True}, "close rises above the star high"))
        directions = (str(older["direction"]), str(prior["direction"]), direction)
        closes = (float(older["close"]), prior_close, current_close)
        if directions == ("bullish", "bullish", "bullish") and closes[0] < closes[1] < closes[2]:
            candidates.append(_candle_candidate("three_white_soldiers", index, rows, "bullish", 0.63, 0.7, {**evidence, "three_bar_progression": True}, "close breaks the three-bar midpoint"))
        if directions == ("bearish", "bearish", "bearish") and closes[0] > closes[1] > closes[2]:
            candidates.append(_candle_candidate("three_black_crows", index, rows, "bearish", 0.63, 0.7, {**evidence, "three_bar_progression": True}, "close breaks the three-bar midpoint"))

        tolerance = max(float(current["span"]), float(prior["span"])) * 0.08
        if abs(float(current["low"]) - float(prior["low"])) <= tolerance and prior["direction"] == "bearish" and direction == "bullish":
            candidates.append(_candle_candidate("tweezer_bottom", index, rows, "bullish", 0.55, 0.6, evidence, "price closes below the matched lows"))
        if abs(float(current["high"]) - float(prior["high"])) <= tolerance and prior["direction"] == "bullish" and direction == "bearish":
            candidates.append(_candle_candidate("tweezer_top", index, rows, "bearish", 0.55, 0.6, evidence, "price closes above the matched highs"))
        if float(current["high"]) < float(prior["high"]) and float(current["low"]) > float(prior["low"]):
            candidates.append(_candle_candidate("inside_bar", index, rows, "neutral", 0.54, 0.62, evidence, "range expansion resolves the compression"))
        if float(current["high"]) > float(prior["high"]) and float(current["low"]) < float(prior["low"]):
            candidates.append(_candle_candidate("outside_bar", index, rows, direction, 0.57, 0.64, evidence, "price closes back inside the parent range"))
    return sorted(candidates, key=lambda item: (-int(item["bar_index"]), -float(item["probability"]), str(item["pattern"])))


def _pivots(rows: Sequence[Bar], field: str, radius: int) -> list[tuple[int, float]]:
    output: list[tuple[int, float]] = []
    for index in range(radius, len(rows) - radius):
        value = float(rows[index][field])
        window = [float(row[field]) for row in rows[index - radius : index + radius + 1]]
        is_pivot = (field == "low" and value == min(window)) or (
            field == "high" and value == max(window)
        )
        if is_pivot:
            if (
                output
                and index - output[-1][0] <= radius
                and abs(value - output[-1][1]) <= 1e-12
            ):
                output[-1] = (index, value)
            else:
                output.append((index, value))
    return output


def _divergence_candidate(
    divergence_type: str,
    oscillator: str,
    rows: Sequence[Bar],
    first: tuple[int, float],
    second: tuple[int, float],
    first_oscillator: float,
    second_oscillator: float,
    oscillator_change: float,
) -> dict[str, Any]:
    direction = "bullish" if divergence_type.endswith("bullish") else "bearish"
    price_change = second[1] / first[1] - 1.0
    recency = max(0.0, 1.0 - (len(rows) - 1 - second[0]) / 50.0)
    magnitude = min(1.0, abs(price_change) * 12.0 + abs(oscillator_change) * 0.8)
    probability = 0.5 + 0.13 * magnitude + 0.08 * recency
    return {
        "pattern": f"{divergence_type}_divergence",
        "family": "oscillator_divergence",
        "divergence_type": divergence_type,
        "directional_bias": direction,
        "oscillator": oscillator,
        "as_of": str(rows[second[0]]["date"]),
        "probability": round(min(0.82, probability), 6),
        "evidence_quality": round(min(0.9, 0.48 + 0.22 * recency + 0.2 * magnitude), 6),
        "price_change": round(price_change, 8),
        "oscillator_normalized_change": round(oscillator_change, 8),
        "pivots": [
            {"index": first[0], "date": str(rows[first[0]]["date"]), "price": round(first[1], 8), "oscillator": round(first_oscillator, 8)},
            {"index": second[0], "date": str(rows[second[0]]["date"]), "price": round(second[1], 8), "oscillator": round(second_oscillator, 8)},
        ],
        "failure_condition": (
            "price closes below the latest pivot low without oscillator confirmation"
            if direction == "bullish"
            else "price closes above the latest pivot high without oscillator confirmation"
        ),
        "pattern_is_not_truth": True,
        "not_trade_decision": True,
    }


def detect_divergences(rows: Sequence[Bar], maximum_bars: int) -> list[dict[str, Any]]:
    """Find regular and hidden divergence at confirmed price pivots."""

    if maximum_bars < 60:
        raise ValueError(f"divergence window must contain at least 60 bars: maximum_bars={maximum_bars}")
    window = list(rows[-maximum_bars:])
    if len(window) < 60:
        return []
    low_pivots = _pivots(window, "low", 2)
    high_pivots = _pivots(window, "high", 2)
    if len(low_pivots) < 2 and len(high_pivots) < 2:
        return []
    by_name = {spec.indicator: spec for spec in ALL_TECHNICAL_SPECS}
    candidates: list[dict[str, Any]] = []
    for oscillator in DIVERGENCE_OSCILLATORS:
        spec = by_name.get(oscillator)
        if spec is None:
            continue
        series = calculate_indicator_series(spec, window)
        finite = [float(value) for value in series if value is not None]
        if len(finite) < 20:
            continue
        span = max(finite[-160:]) - min(finite[-160:])
        if span <= 1e-12:
            continue
        for pivots, side in ((low_pivots, "low"), (high_pivots, "high")):
            usable = [pivot for pivot in pivots if series[pivot[0]] is not None]
            if len(usable) < 2:
                continue
            first, second = usable[-2:]
            if second[0] - first[0] < 5 or len(window) - 1 - second[0] > 45:
                continue
            first_oscillator = float(series[first[0]])
            second_oscillator = float(series[second[0]])
            price_change = second[1] / first[1] - 1.0
            oscillator_change = (second_oscillator - first_oscillator) / span
            divergence_type: str | None = None
            if side == "low" and price_change <= -0.002 and oscillator_change >= 0.04:
                divergence_type = "regular_bullish"
            elif side == "low" and price_change >= 0.002 and oscillator_change <= -0.04:
                divergence_type = "hidden_bullish"
            elif side == "high" and price_change >= 0.002 and oscillator_change <= -0.04:
                divergence_type = "regular_bearish"
            elif side == "high" and price_change <= -0.002 and oscillator_change >= 0.04:
                divergence_type = "hidden_bearish"
            if divergence_type is not None:
                candidates.append(_divergence_candidate(divergence_type, oscillator, window, first, second, first_oscillator, second_oscillator, oscillator_change))
    return sorted(candidates, key=lambda item: (-float(item["probability"]), str(item["divergence_type"]), str(item["oscillator"])))
