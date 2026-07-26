"""Probabilistic structure, pattern, volume-profile, and regime evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from dopey.chronos.clocks import ClockStamp
from dopey.constitution.evidence_law import validate_evidence_records
from dopey.protocols.identity import canonical_hash
from dopey_equity_swing.market_structure import Bar

from .candle_intelligence import (
    CANDLESTICK_PATTERN_FAMILIES,
    DIVERGENCE_OSCILLATORS,
    detect_candlestick_patterns,
    detect_divergences,
)


SUPPORTED_PATTERN_FAMILIES: tuple[str, ...] = (
    "flag_or_pennant",
    "triangle",
    "wedge",
    "rectangle",
    "double_top_or_bottom",
    "head_and_shoulders",
    "cup_and_handle",
    "gap_continuation_or_exhaustion",
    "candlestick_taxonomy",
    "regular_oscillator_divergence",
    "hidden_oscillator_divergence",
)


def _slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2.0
    y_mean = sum(values) / len(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    return 0.0 if denominator == 0.0 or y_mean == 0.0 else (
        sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
    ) / abs(y_mean)


def _swing_points(rows: Sequence[Bar], radius: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for index in range(radius, len(rows) - radius):
        window = rows[index - radius : index + radius + 1]
        high = float(rows[index]["high"])
        low = float(rows[index]["low"])
        if high == max(float(row["high"]) for row in window):
            highs.append((index, high))
        if low == min(float(row["low"]) for row in window):
            lows.append((index, low))
    return highs, lows


def _market_structure(rows: Sequence[Bar]) -> dict[str, Any]:
    highs, lows = _swing_points(rows[-160:], 2)
    if len(highs) < 2 or len(lows) < 2:
        state = "insufficient_swing_structure"
    elif highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]:
        state = "higher_high_higher_low"
    elif highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]:
        state = "lower_high_lower_low"
    else:
        state = "mixed_or_transitioning"
    prior = rows[-21:-1] if len(rows) >= 21 else rows[:-1]
    close = float(rows[-1]["close"])
    prior_high = max((float(row["high"]) for row in prior), default=close)
    prior_low = min((float(row["low"]) for row in prior), default=close)
    break_state = "bullish_break_of_structure" if close > prior_high else "bearish_break_of_structure" if close < prior_low else "inside_prior_structure"
    return {
        "state": state,
        "break_state": break_state,
        "latest_swing_highs": [round(value, 8) for _, value in highs[-3:]],
        "latest_swing_lows": [round(value, 8) for _, value in lows[-3:]],
        "support_levels": [round(value, 8) for _, value in lows[-5:]],
        "resistance_levels": [round(value, 8) for _, value in highs[-5:]],
    }


def _candidate(pattern: str, probability: float, quality: float, evidence: Mapping[str, Any], failure: str) -> dict[str, Any]:
    return {
        "pattern": pattern,
        "probability": round(max(0.0, min(0.95, probability)), 6),
        "evidence_quality": round(max(0.0, min(1.0, quality)), 6),
        "evidence": dict(evidence),
        "failure_condition": failure,
        "pattern_is_not_truth": True,
    }


def _pattern_candidates(rows: Sequence[Bar]) -> list[dict[str, Any]]:
    if len(rows) < 60:
        return []
    close = float(rows[-1]["close"])
    recent = rows[-20:]
    highs = [float(row["high"]) for row in recent]
    lows = [float(row["low"]) for row in recent]
    closes = [float(row["close"]) for row in rows]
    range_fraction = (max(highs) - min(lows)) / close if close > 0.0 else 1.0
    high_slope = _slope(highs)
    low_slope = _slope(lows)
    candidates: list[dict[str, Any]] = []
    if range_fraction <= 0.08 and abs(high_slope) < 0.002 and abs(low_slope) < 0.002:
        candidates.append(_candidate("rectangle", 0.62, 0.65, {"range_fraction": range_fraction}, "close leaves range and fails retest"))
    convergence = high_slope - low_slope
    if convergence < -0.001:
        candidates.append(_candidate("triangle", 0.58, 0.6, {"high_slope": high_slope, "low_slope": low_slope}, "range expands instead of converging"))
    if high_slope * low_slope > 0.0 and convergence < -0.0005:
        candidates.append(_candidate("wedge", 0.54, 0.55, {"high_slope": high_slope, "low_slope": low_slope}, "parallel channel persists without convergence"))
    impulse = closes[-21] / closes[-31] - 1.0
    consolidation = closes[-1] / closes[-11] - 1.0
    if abs(impulse) >= 0.08 and abs(consolidation) <= abs(impulse) * 0.45:
        candidates.append(_candidate("flag_or_pennant", 0.6, 0.58, {"impulse_return": impulse, "consolidation_return": consolidation}, "retracement exceeds half of impulse"))
    swing_highs, swing_lows = _swing_points(rows[-100:], 2)
    if len(swing_highs) >= 2:
        top_distance = abs(swing_highs[-1][1] / swing_highs[-2][1] - 1.0)
        if top_distance <= 0.025 and swing_highs[-1][0] - swing_highs[-2][0] >= 5:
            candidates.append(_candidate("double_top", 0.57, 0.56, {"peak_distance": top_distance}, "price closes decisively above both peaks"))
    if len(swing_lows) >= 2:
        bottom_distance = abs(swing_lows[-1][1] / swing_lows[-2][1] - 1.0)
        if bottom_distance <= 0.025 and swing_lows[-1][0] - swing_lows[-2][0] >= 5:
            candidates.append(_candidate("double_bottom", 0.57, 0.56, {"trough_distance": bottom_distance}, "price closes decisively below both troughs"))
    if len(swing_highs) >= 3:
        left, head, right = swing_highs[-3:]
        shoulder_distance = abs(left[1] / right[1] - 1.0)
        if head[1] > max(left[1], right[1]) * 1.02 and shoulder_distance <= 0.04:
            candidates.append(_candidate("head_and_shoulders", 0.55, 0.5, {"shoulder_distance": shoulder_distance}, "head level is reclaimed after neckline break"))
    if len(swing_lows) >= 3:
        left, head, right = swing_lows[-3:]
        shoulder_distance = abs(left[1] / right[1] - 1.0)
        if head[1] < min(left[1], right[1]) * 0.98 and shoulder_distance <= 0.04:
            candidates.append(_candidate("inverse_head_and_shoulders", 0.55, 0.5, {"shoulder_distance": shoulder_distance}, "head low is lost after neckline break"))
    cup_window = closes[-60:]
    left = sum(cup_window[:5]) / 5.0
    middle = min(cup_window[15:45])
    right = sum(cup_window[-10:-5]) / 5.0
    if middle < min(left, right) * 0.9 and abs(right / left - 1.0) <= 0.06:
        candidates.append(_candidate("cup_and_handle", 0.52, 0.48, {"rim_distance": abs(right / left - 1.0)}, "handle closes below the cup midpoint"))
    prior = rows[-2]
    current = rows[-1]
    gap = float(current["open"]) / float(prior["close"]) - 1.0
    if abs(gap) >= 0.015:
        filled = float(current["low"]) <= float(prior["close"]) <= float(current["high"])
        candidates.append(_candidate(
            "gap_exhaustion" if filled else "gap_continuation",
            0.6 if not filled else 0.55,
            0.65,
            {"gap_return": gap, "same_bar_fill": filled},
            "gap classification reverses after subsequent settlement bars",
        ))
    return sorted(candidates, key=lambda record: (-float(record["probability"]), str(record["pattern"])))


def _volume_profile(rows: Sequence[Bar], bin_count: int) -> dict[str, Any]:
    window = rows[-120:]
    minimum = min(float(row["low"]) for row in window)
    maximum = max(float(row["high"]) for row in window)
    if maximum == minimum:
        return {"status": "degenerate_price_range", "point_of_control": minimum, "value_area": [minimum, maximum], "bins": []}
    width = (maximum - minimum) / bin_count
    volumes = [0.0] * bin_count
    for row in window:
        typical = (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3.0
        index = min(bin_count - 1, int((typical - minimum) / width))
        volumes[index] += float(row["volume"])
    total = sum(volumes)
    order = sorted(range(bin_count), key=lambda index: (-volumes[index], index))
    selected: list[int] = []
    accumulated = 0.0
    for index in order:
        selected.append(index)
        accumulated += volumes[index]
        if total == 0.0 or accumulated / total >= 0.7:
            break
    point = order[0]
    return {
        "status": "complete_daily_bar_volume_profile_proxy",
        "point_of_control": round(minimum + (point + 0.5) * width, 8),
        "value_area": [round(minimum + min(selected) * width, 8), round(minimum + (max(selected) + 1) * width, 8)],
        "bin_count": bin_count,
        "limitations": ["bar_volume_assigned_to_typical_price_not_price_level_tape"],
    }


def _regime_statistics(rows: Sequence[Bar]) -> dict[str, Any]:
    closes = [float(row["close"]) for row in rows[-121:]]
    returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = sum((value - mean) ** 2 for value in returns) / max(len(returns) - 1, 1)
    deviation = math.sqrt(variance)
    skew = sum((value - mean) ** 3 for value in returns) / max(len(returns) * deviation ** 3, 1e-12)
    kurtosis = sum((value - mean) ** 4 for value in returns) / max(len(returns) * deviation ** 4, 1e-12) - 3.0
    lag_numerator = sum((returns[index] - mean) * (returns[index - 1] - mean) for index in range(1, len(returns)))
    lag_denominator = sum((value - mean) ** 2 for value in returns)
    autocorrelation = 0.0 if lag_denominator == 0.0 else lag_numerator / lag_denominator
    peak = closes[0]
    maximum_drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        maximum_drawdown = min(maximum_drawdown, close / peak - 1.0)
    return {
        "sample_count": len(returns),
        "annualized_volatility": round(deviation * math.sqrt(252.0), 8),
        "skewness": round(skew, 8),
        "excess_kurtosis": round(kurtosis, 8),
        "lag_one_autocorrelation": round(autocorrelation, 8),
        "maximum_drawdown": round(maximum_drawdown, 8),
    }


def build_structure_pattern_evidence(
    symbol: str,
    rows_by_timeframe: Mapping[str, Sequence[Bar]],
    clock: ClockStamp,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for timeframe, rows in rows_by_timeframe.items():
        candlestick_patterns = detect_candlestick_patterns(rows, 12)
        divergences = detect_divergences(rows, 260)
        body: dict[str, Any] = {
            "artifact_type": "technical_structure_pattern_evidence",
            "structure_pattern_version": "dopey-structure-pattern-v2",
            "symbol": symbol,
            "timeframe": timeframe,
            "as_of": str(rows[-1]["date"]),
            "market_structure": _market_structure(rows),
            "pattern_candidates": _pattern_candidates(rows),
            "candlestick_patterns": candlestick_patterns,
            "candlestick_pattern_families": list(CANDLESTICK_PATTERN_FAMILIES),
            "divergences": divergences,
            "divergence_oscillators": list(DIVERGENCE_OSCILLATORS),
            "supported_pattern_families": list(SUPPORTED_PATTERN_FAMILIES),
            "volume_profile": _volume_profile(rows, 12),
            "regime_statistics": _regime_statistics(rows),
            "patterns_are_probabilistic_not_truth": True,
            "paper_only": True,
            "live_blocked": True,
            "not_trade_decision": True,
        }
        content_hash = canonical_hash(body)
        records.append(
            {
                **body,
                "evidence_id": f"structure:{symbol}:{timeframe}:{content_hash[:16]}",
                "content_hash": content_hash,
                "observed_at": clock.market_time,
                "source_uri": f"local://validated-history/{symbol}/{timeframe}/structure",
                "schema_version": "dopey-structure-pattern-v2",
                "provenance": "deterministic_probabilistic_heuristics_on_hash_pinned_history",
            }
        )
    validate_evidence_records(records)
    return records
