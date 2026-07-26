"""Leak-safe multi-timeframe support, resistance, and trend-channel geometry."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from statistics import median
from typing import Any, TypedDict


class Bar(TypedDict):
    date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


TIMEFRAME_CONFIG: dict[str, dict[str, float | int]] = {
    "daily": {"lookback": 252, "pivot_k": 3, "channel_lookback": 90, "weight": 0.45},
    "weekly": {"lookback": 156, "pivot_k": 2, "channel_lookback": 78, "weight": 0.35},
    "monthly": {"lookback": 84, "pivot_k": 1, "channel_lookback": 48, "weight": 0.20},
}


def normalize_history_bars(rows: list[dict[str, Any]]) -> list[Bar]:
    normalized = [
        Bar(
            date=str(row["date"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            adjusted_close=float(row.get("adjusted_close", row["close"])),
            volume=int(row["volume"]),
        )
        for row in rows
    ]
    return sorted(normalized, key=lambda row: row["date"])


def group_history_bars(rows: list[dict[str, Any]]) -> dict[str, list[Bar]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["symbol"])].append(row)
    return {symbol: normalize_history_bars(symbol_rows) for symbol, symbol_rows in sorted(grouped.items())}


def resample_bars(rows: list[Bar], timeframe: str) -> list[Bar]:
    if timeframe == "daily":
        return [Bar(**row) for row in rows]
    if timeframe not in {"weekly", "monthly"}:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    grouped: dict[str, list[Bar]] = defaultdict(list)
    for row in rows:
        parsed = date.fromisoformat(row["date"])
        if timeframe == "weekly":
            iso_year, iso_week, _ = parsed.isocalendar()
            key = f"{iso_year:04d}-W{iso_week:02d}"
        else:
            key = row["date"][:7]
        grouped[key].append(row)
    output: list[Bar] = []
    for key in sorted(grouped):
        bucket = grouped[key]
        first = bucket[0]
        last = bucket[-1]
        output.append(
            Bar(
                date=last["date"],
                open=first["open"],
                high=max(row["high"] for row in bucket),
                low=min(row["low"] for row in bucket),
                close=last["close"],
                adjusted_close=last["adjusted_close"],
                volume=sum(row["volume"] for row in bucket),
            )
        )
    return output


def average_true_range(rows: list[Bar], period: int) -> float:
    if len(rows) < 2:
        return 0.0
    ranges: list[float] = []
    start = max(1, len(rows) - period)
    for index in range(start, len(rows)):
        current = rows[index]
        prior_close = rows[index - 1]["close"]
        ranges.append(
            max(
                current["high"] - current["low"],
                abs(current["high"] - prior_close),
                abs(current["low"] - prior_close),
            )
        )
    return sum(ranges) / len(ranges) if ranges else 0.0


def confirmed_pivots(rows: list[Bar], pivot_k: int) -> list[dict[str, Any]]:
    if pivot_k < 1:
        raise ValueError(f"pivot_k must be positive: {pivot_k}")
    pivots: list[dict[str, Any]] = []
    for index in range(pivot_k, len(rows) - pivot_k):
        window = rows[index - pivot_k : index + pivot_k + 1]
        row = rows[index]
        confirmed_at = rows[index + pivot_k]["date"]
        if row["high"] == max(value["high"] for value in window):
            pivots.append(_pivot(row, index, confirmed_at, "resistance", row["high"]))
        if row["low"] == min(value["low"] for value in window):
            pivots.append(_pivot(row, index, confirmed_at, "support", row["low"]))
    return pivots


def _pivot(row: Bar, index: int, confirmed_at: str, role: str, price: float) -> dict[str, Any]:
    return {
        "pivot_date": row["date"],
        "confirmed_at": confirmed_at,
        "bar_index": index,
        "role": role,
        "price": round(price, 6),
    }


def cluster_zones(
    pivots: list[dict[str, Any]],
    current_price: float,
    atr_value: float,
    last_bar_index: int,
) -> list[dict[str, Any]]:
    tolerance = max(current_price * 0.006, atr_value * 0.55)
    ordered = sorted(pivots, key=lambda pivot: float(pivot["price"]))
    clusters: list[list[dict[str, Any]]] = []
    for pivot in ordered:
        if not clusters:
            clusters.append([pivot])
            continue
        prior_mid = sum(float(item["price"]) for item in clusters[-1]) / len(clusters[-1])
        if abs(float(pivot["price"]) - prior_mid) <= tolerance:
            clusters[-1].append(pivot)
        else:
            clusters.append([pivot])
    zones: list[dict[str, Any]] = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        prices = [float(pivot["price"]) for pivot in cluster]
        ages = [max(last_bar_index - int(pivot["bar_index"]), 0) for pivot in cluster]
        recency = sum(math.exp(-age / 80.0) for age in ages)
        support_touches = sum(pivot["role"] == "support" for pivot in cluster)
        resistance_touches = sum(pivot["role"] == "resistance" for pivot in cluster)
        mid = median(prices)
        role = "support" if mid < current_price else "resistance" if mid > current_price else "at_price"
        zones.append(
            {
                "zone_low": round(min(prices) - tolerance * 0.25, 6),
                "zone_high": round(max(prices) + tolerance * 0.25, 6),
                "zone_mid": round(mid, 6),
                "role_now": role,
                "touch_count": len(cluster),
                "support_pivot_count": support_touches,
                "resistance_pivot_count": resistance_touches,
                "recency_score": round(min(recency / 3.0, 1.0), 6),
                "strength_score": round(min(0.18 * len(cluster) + 0.45 * min(recency / 3.0, 1.0), 1.0), 6),
                "distance_pct": round((mid - current_price) / current_price, 6),
            }
        )
    return sorted(zones, key=lambda zone: abs(float(zone["distance_pct"])))


def theil_sen_line(points: list[tuple[int, float]]) -> tuple[float, float, float]:
    if len(points) < 2:
        return 0.0, points[0][1] if points else 0.0, 0.0
    slopes = [
        (second_y - first_y) / (second_x - first_x)
        for first_index, (first_x, first_y) in enumerate(points)
        for second_x, second_y in points[first_index + 1 :]
        if second_x != first_x
    ]
    slope = median(slopes) if slopes else 0.0
    intercept = median([value - slope * index for index, value in points])
    residuals = [abs(value - (intercept + slope * index)) for index, value in points]
    return slope, intercept, median(residuals) if residuals else 0.0


def trend_channel(rows: list[Bar], pivots: list[dict[str, Any]], lookback: int) -> dict[str, Any]:
    if len(rows) < 20:
        return _missing_channel("insufficient_timeframe_history")
    start_index = max(len(rows) - lookback, 0)
    supports = [
        (int(pivot["bar_index"]), float(pivot["price"]))
        for pivot in pivots
        if pivot["role"] == "support" and int(pivot["bar_index"]) >= start_index
    ]
    resistances = [
        (int(pivot["bar_index"]), float(pivot["price"]))
        for pivot in pivots
        if pivot["role"] == "resistance" and int(pivot["bar_index"]) >= start_index
    ]
    if len(supports) < 2 or len(resistances) < 2:
        return _missing_channel("insufficient_confirmed_channel_pivots")
    lower_slope, lower_intercept, lower_residual = theil_sen_line(supports)
    upper_slope, upper_intercept, upper_residual = theil_sen_line(resistances)
    current_index = len(rows) - 1
    lower = lower_intercept + lower_slope * current_index
    upper = upper_intercept + upper_slope * current_index
    if upper <= lower:
        return _missing_channel("channel_bounds_crossed")
    current = rows[-1]["close"]
    width = upper - lower
    position = (current - lower) / width
    normalized_lower_slope = lower_slope / current if current else 0.0
    normalized_upper_slope = upper_slope / current if current else 0.0
    if normalized_lower_slope > 0.0004 and normalized_upper_slope > 0.0004:
        direction = "uptrend"
    elif normalized_lower_slope < -0.0004 and normalized_upper_slope < -0.0004:
        direction = "downtrend"
    else:
        direction = "sideways_or_divergent"
    residual_pct = (lower_residual + upper_residual) / max(2.0 * width, 1e-9)
    quality = min(1.0, 0.35 + 0.08 * min(len(supports) + len(resistances), 6) + 0.35 * max(0.0, 1.0 - residual_pct))
    return {
        "channel_status": "confirmed",
        "direction": direction,
        "lower_bound": round(lower, 6),
        "upper_bound": round(upper, 6),
        "width_pct": round(width / current, 6) if current else 0.0,
        "channel_position": round(position, 6),
        "lower_slope_pct_per_bar": round(normalized_lower_slope, 8),
        "upper_slope_pct_per_bar": round(normalized_upper_slope, 8),
        "support_pivots_used": len(supports),
        "resistance_pivots_used": len(resistances),
        "quality_score": round(quality, 6),
    }


def _missing_channel(reason: str) -> dict[str, Any]:
    return {
        "channel_status": "unconfirmed",
        "reason": reason,
        "direction": "unknown",
        "lower_bound": 0.0,
        "upper_bound": 0.0,
        "width_pct": 0.0,
        "channel_position": 0.5,
        "lower_slope_pct_per_bar": 0.0,
        "upper_slope_pct_per_bar": 0.0,
        "support_pivots_used": 0,
        "resistance_pivots_used": 0,
        "quality_score": 0.0,
    }


def analyze_timeframe(rows: list[Bar], timeframe: str) -> dict[str, Any]:
    config = TIMEFRAME_CONFIG[timeframe]
    resampled = resample_bars(rows, timeframe)
    lookback = int(config["lookback"])
    scoped = resampled[-lookback:]
    if len(scoped) < 20:
        return {
            "timeframe": timeframe,
            "timeframe_status": "insufficient_history",
            "bar_count": len(scoped),
            "weight": float(config["weight"]),
        }
    pivot_k = int(config["pivot_k"])
    pivots = confirmed_pivots(scoped, pivot_k)
    atr_value = average_true_range(scoped, 14)
    current = scoped[-1]["close"]
    zones = cluster_zones(pivots, current, atr_value, len(scoped) - 1)
    channel = trend_channel(scoped, pivots, int(config["channel_lookback"]))
    nearest_support = next((zone for zone in zones if float(zone["zone_mid"]) < current), None)
    nearest_resistance = next((zone for zone in zones if float(zone["zone_mid"]) > current), None)
    return {
        "timeframe": timeframe,
        "timeframe_status": "analyzed",
        "bar_count": len(scoped),
        "as_of_date": scoped[-1]["date"],
        "current_price": round(current, 6),
        "atr": round(atr_value, 6),
        "atr_pct": round(atr_value / current, 6) if current else 0.0,
        "confirmed_pivot_count": len(pivots),
        "zones": zones,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "channel": channel,
        "weight": float(config["weight"]),
    }


def analyze_multi_timeframe_structure(symbol: str, rows: list[Bar]) -> dict[str, Any]:
    timeframes = [analyze_timeframe(rows, timeframe) for timeframe in TIMEFRAME_CONFIG]
    analyzed = [record for record in timeframes if record.get("timeframe_status") == "analyzed"]
    if not analyzed:
        return {
            "artifact_type": "multi_timeframe_market_structure",
            "symbol": symbol,
            "structure_status": "insufficient_history",
            "timeframes": timeframes,
            "paper_only": True,
            "live_blocked": True,
        }
    direction_value = {"uptrend": 1.0, "downtrend": -1.0, "sideways_or_divergent": 0.0, "unknown": 0.0}
    weighted_direction = sum(
        float(record["weight"])
        * direction_value[str(record["channel"]["direction"])]
        * float(record["channel"]["quality_score"])
        for record in analyzed
    )
    weight_sum = sum(float(record["weight"]) for record in analyzed)
    agreement = weighted_direction / weight_sum if weight_sum else 0.0
    daily = next(record for record in analyzed if record["timeframe"] == "daily")
    current = float(daily["current_price"])
    confluence_zones = merge_timeframe_zones(analyzed, current, float(daily["atr"]))
    nearest_support = next((zone for zone in confluence_zones if float(zone["zone_mid"]) < current), None)
    nearest_resistance = next((zone for zone in confluence_zones if float(zone["zone_mid"]) > current), None)
    direction = "bullish" if agreement >= 0.25 else "bearish" if agreement <= -0.25 else "neutral"
    return {
        "artifact_type": "multi_timeframe_market_structure",
        "symbol": symbol,
        "structure_status": "complete",
        "as_of_date": daily["as_of_date"],
        "current_price": current,
        "daily_atr": daily["atr"],
        "daily_atr_pct": daily["atr_pct"],
        "timeframes": timeframes,
        "multi_timeframe_direction": direction,
        "multi_timeframe_agreement_score": round(agreement, 6),
        "bullish_timeframe_count": sum(record["channel"]["direction"] == "uptrend" for record in analyzed),
        "bearish_timeframe_count": sum(record["channel"]["direction"] == "downtrend" for record in analyzed),
        "confluence_zones": confluence_zones,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "intraday_timeframes_status": "unavailable_no_local_intraday_history_not_synthesized",
        "leak_policy": "pivots become usable only at confirmed_at; current analysis uses validated bars through as_of_date",
        "paper_only": True,
        "live_blocked": True,
    }


def merge_timeframe_zones(
    timeframes: list[dict[str, Any]],
    current_price: float,
    daily_atr: float,
) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    for timeframe in timeframes:
        for zone in timeframe.get("zones", []):
            raw.append(
                {
                    **zone,
                    "timeframe": timeframe["timeframe"],
                    "timeframe_weight": timeframe["weight"],
                }
            )
    tolerance = max(current_price * 0.008, daily_atr * 0.65)
    ordered = sorted(raw, key=lambda zone: float(zone["zone_mid"]))
    groups: list[list[dict[str, Any]]] = []
    for zone in ordered:
        if not groups:
            groups.append([zone])
            continue
        group_mid = sum(float(item["zone_mid"]) for item in groups[-1]) / len(groups[-1])
        if abs(float(zone["zone_mid"]) - group_mid) <= tolerance:
            groups[-1].append(zone)
        else:
            groups.append([zone])
    merged: list[dict[str, Any]] = []
    for group in groups:
        weights = [float(zone["timeframe_weight"]) * max(float(zone["strength_score"]), 0.1) for zone in group]
        total_weight = sum(weights)
        mid = sum(float(zone["zone_mid"]) * weight for zone, weight in zip(group, weights)) / total_weight
        timeframes_present = sorted({str(zone["timeframe"]) for zone in group})
        confluence = min(1.0, sum(float(zone["timeframe_weight"]) for zone in group) + 0.12 * (len(timeframes_present) - 1))
        merged.append(
            {
                "zone_low": round(min(float(zone["zone_low"]) for zone in group), 6),
                "zone_high": round(max(float(zone["zone_high"]) for zone in group), 6),
                "zone_mid": round(mid, 6),
                "role_now": "support" if mid < current_price else "resistance" if mid > current_price else "at_price",
                "timeframes": timeframes_present,
                "source_zone_count": len(group),
                "touch_count": sum(int(zone["touch_count"]) for zone in group),
                "confluence_score": round(confluence, 6),
                "distance_pct": round((mid - current_price) / current_price, 6),
            }
        )
    return sorted(merged, key=lambda zone: abs(float(zone["distance_pct"])))
