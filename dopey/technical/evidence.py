"""Convert every versioned technical primitive into typed evidence objects."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dopey.chronos.clocks import ClockStamp, validate_clock_stamp
from dopey.constitution.evidence_law import validate_evidence_records
from dopey_equity_swing.market_structure import Bar, resample_bars

from dopey.protocols.identity import canonical_hash

from .batch_a import IndicatorSpec, calculate_indicator_series
from .foundry import ALL_TECHNICAL_SPECS
from .structure_patterns import build_structure_pattern_evidence


PERCENTILE_WINDOWS: dict[str, int] = {
    "intraday": 1000,
    "daily": 756,
    "weekly": 260,
    "monthly": 120,
}


def _percentile(values: Sequence[float], current: float) -> float:
    if not values:
        return 0.0
    less = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return (less + 0.5 * equal) / len(values)


def _slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    window = list(values[-5:])
    x_mean = (len(window) - 1) / 2.0
    y_mean = sum(window) / len(window)
    denominator = sum((index - x_mean) ** 2 for index in range(len(window)))
    if denominator == 0.0:
        return 0.0
    numerator = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(window))
    scale = max(abs(y_mean), 1.0)
    return (numerator / denominator) / scale


def _state(indicator: str, value: float, percentile: float, slope: float) -> str:
    if indicator in {"RSI", "STOCHASTIC_RSI", "MONEY_FLOW_INDEX", "CONNORS_RSI", "ULTIMATE_OSCILLATOR", "SCHAFF_TREND_CYCLE"}:
        if value >= 80.0:
            return "overextended_high"
        if value >= 55.0:
            return "positive"
        if value <= 20.0:
            return "overextended_low"
        if value <= 45.0:
            return "negative"
        return "neutral"
    if indicator == "ADX":
        return "strong_trend" if value >= 25.0 else "developing_trend" if value >= 20.0 else "weak_trend"
    if indicator == "NORMALIZED_ATR":
        return "high_volatility" if percentile >= 0.8 else "low_volatility" if percentile <= 0.2 else "normal_volatility"
    if indicator == "BOLLINGER_PERCENT_B":
        return "above_upper_band" if value > 1.0 else "below_lower_band" if value < 0.0 else "inside_bands"
    if indicator == "WILLIAMS_R":
        return "overextended_high" if value >= -20.0 else "overextended_low" if value <= -80.0 else "neutral"
    if indicator == "CHOPPINESS_INDEX":
        return "range_dominant" if value >= 61.8 else "trend_efficient" if value <= 38.2 else "transitioning"
    if indicator == "MASS_INDEX":
        return "reversal_bulge_watch" if value >= 27.0 else "normal_range_expansion"
    if indicator in {
        "ULCER_INDEX",
        "PARKINSON_VOLATILITY",
        "GARMAN_KLASS_VOLATILITY",
        "ROGERS_SATCHELL_VOLATILITY",
        "YANG_ZHANG_VOLATILITY",
        "HISTORICAL_VOLATILITY",
        "BOLLINGER_BANDWIDTH",
        "KELTNER_WIDTH",
    }:
        return "high_or_expanding" if percentile >= 0.8 else "low_or_compressed" if percentile <= 0.2 else "normal_range"
    threshold = 0.0
    if value > threshold and slope >= 0.0:
        return "positive_accelerating"
    if value > threshold:
        return "positive_decelerating"
    if value < threshold and slope <= 0.0:
        return "negative_accelerating"
    if value < threshold:
        return "negative_improving"
    return "neutral"


def _measurement(
    symbol: str,
    timeframe: str,
    rows: Sequence[Bar],
    spec: IndicatorSpec,
    clock: ClockStamp,
) -> dict[str, Any]:
    values = calculate_indicator_series(spec, rows)
    finite = [float(value) for value in values if value is not None]
    base: dict[str, Any] = {
        "artifact_type": "technical_measurement",
        "indicator": spec.indicator,
        "symbol": symbol,
        "timeframe": timeframe,
        "formula_version": spec.formula_version,
        "required_lookback": spec.required_lookback,
        "warmup_period": spec.warmup_period,
        "missing_data_behavior": spec.missing_data_behavior,
        "normalization_method": spec.normalization_method,
        "timeframe_compatibility": list(spec.timeframe_compatibility),
        "limitations": list(spec.limitations),
        "as_of": rows[-1]["date"] if rows else "",
        "bar_count": len(rows),
        "paper_only": True,
        "live_blocked": True,
        "not_trade_decision": True,
    }
    if not finite:
        measurement = {
            **base,
            "measurement_status": "insufficient_warmup_history",
            "value": None,
            "percentile": None,
            "slope": None,
            "state": "unknown",
            "reliability": 0.0,
            "freshness": 0.0,
        }
    else:
        current = finite[-1]
        window = finite[-PERCENTILE_WINDOWS[timeframe] :]
        percentile = _percentile(window, current)
        slope = _slope(finite)
        reliability = min(1.0, len(finite) / max(spec.required_lookback * 3, 1))
        measurement = {
            **base,
            "measurement_status": "complete",
            "value": round(current, 8),
            "percentile": round(percentile, 6),
            "slope": round(slope, 8),
            "state": _state(spec.indicator, current, percentile, slope),
            "reliability": round(reliability, 6),
            "freshness": 1.0,
        }
    content_hash = canonical_hash(measurement)
    evidence = {
        "evidence_id": f"technical:{symbol}:{timeframe}:{spec.indicator}:{content_hash[:16]}",
        "content_hash": content_hash,
        "observed_at": clock.market_time,
        "source_uri": f"local://validated-history/{symbol}/{timeframe}",
        "schema_version": "dopey-technical-evidence-v1",
        "provenance": "validated_hash_pinned_history_adapter",
    }
    return {**measurement, **evidence}


def build_timeframe_measurements(
    symbol: str,
    timeframe: str,
    rows: Sequence[Bar],
    clock: ClockStamp,
    specs: Sequence[IndicatorSpec],
) -> list[dict[str, Any]]:
    if timeframe not in PERCENTILE_WINDOWS:
        raise ValueError(f"technical timeframe is unsupported: timeframe={timeframe}")
    measurements = [_measurement(symbol, timeframe, rows, spec, clock) for spec in specs]
    validate_evidence_records(measurements)
    return measurements


def _fusion_state(timeframes: dict[str, dict[str, Any]]) -> str:
    daily = timeframes.get("daily", {})
    weekly = timeframes.get("weekly", {})
    monthly = timeframes.get("monthly", {})
    states = [str(record.get("state", "unknown")) for record in (daily, weekly, monthly)]
    positive = sum(state.startswith("positive") for state in states)
    negative = sum(state.startswith("negative") for state in states)
    if positive >= 2 and "overextended_high" in states:
        return "higher_timeframe_support_with_short_term_exhaustion_risk"
    if negative >= 2 and "overextended_low" in states:
        return "higher_timeframe_weakness_with_short_term_exhaustion_risk"
    if positive >= 2:
        return "aligned_positive"
    if negative >= 2:
        return "aligned_negative"
    if positive and negative:
        return "cross_timeframe_contradiction"
    return "mixed_or_neutral"


def build_multi_timeframe_technical_evidence(
    symbol: str,
    daily_rows: Sequence[Bar],
    clock: ClockStamp,
) -> dict[str, Any]:
    validate_clock_stamp(clock)
    if not symbol.strip():
        raise ValueError("technical evidence requires a non-empty symbol")
    if not daily_rows:
        raise ValueError(f"technical evidence requires history rows: symbol={symbol}")
    maximum_warmup = max(spec.warmup_period for spec in ALL_TECHNICAL_SPECS)
    by_timeframe: dict[str, list[Bar]] = {}
    for timeframe in ("daily", "weekly", "monthly"):
        resampled = resample_bars(list(daily_rows), timeframe)
        evaluation_window = PERCENTILE_WINDOWS[timeframe] + maximum_warmup + 5
        by_timeframe[timeframe] = resampled[-evaluation_window:]
    measurements = [
        record
        for timeframe, rows in by_timeframe.items()
        for record in build_timeframe_measurements(symbol, timeframe, rows, clock, ALL_TECHNICAL_SPECS)
    ]
    validate_evidence_records(measurements)
    fusion: dict[str, str] = {}
    for spec in ALL_TECHNICAL_SPECS:
        records = {
            timeframe: next(
                record
                for record in measurements
                if record["timeframe"] == timeframe and record["indicator"] == spec.indicator
            )
            for timeframe in by_timeframe
        }
        fusion[spec.indicator] = _fusion_state(records)
    structure_pattern = build_structure_pattern_evidence(symbol, by_timeframe, clock)
    output: dict[str, Any] = {
        "artifact_type": "multi_timeframe_technical_evidence",
        "technical_evidence_version": "dopey-mtf-technical-batches-a-b-c-v2",
        "symbol": symbol,
        "as_of": daily_rows[-1]["date"],
        "timeframes": list(by_timeframe),
        "evaluation_windows": dict(PERCENTILE_WINDOWS),
        "evaluation_window_policy": "trailing_percentile_window_plus_maximum_warmup_no_future_rows",
        "indicator_count": len(ALL_TECHNICAL_SPECS),
        "measurement_count": len(measurements),
        "measurements": measurements,
        "fusion_states": fusion,
        "structure_pattern_evidence": structure_pattern,
        "structure_pattern_evidence_count": len(structure_pattern),
        "intraday_status": "unavailable_no_validated_local_intraday_history_not_synthesized",
        "intraday_adapter_status": "implemented_requires_hash_pinned_valid_real_intraday_manifest",
        "paper_only": True,
        "live_blocked": True,
        "not_trade_decision": True,
    }
    return {**output, "reproducibility_hash": canonical_hash(output)}
