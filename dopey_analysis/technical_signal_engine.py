"""Pure technical signal calculations for offline long-call/long-put research."""
from __future__ import annotations

import math
from typing import Any

from .signal_models import (
    BreakoutSignal,
    DirectionalSetupSignal,
    FakeoutSignal,
    MarketRegimeSignal,
    MomentumSignal,
    PriceBar,
    RelativeStrengthSignal,
    SignalSeries,
    TrendPullbackSignal,
    VolatilityRegimeSignal,
    make_signal_series,
)


def compute_momentum_signal(series: SignalSeries, signal_date: str, lookback_window: int) -> MomentumSignal:
    bars = _bars_through_date(series, signal_date)
    reason_codes: list[str] = []
    if len(bars) < 21:
        reason_codes.append("insufficient_history")
    return_5d = _simple_return(bars, 5)
    return_10d = _simple_return(bars, 10)
    return_20d = _simple_return(bars, 20)
    slope = _momentum_slope(bars, 20)
    raw_value = round((return_5d * 0.35) + (return_10d * 0.30) + (return_20d * 0.25) + (slope * 0.10), 10)
    normalized = _clamp(raw_value / 0.12, -1.0, 1.0)
    direction = _direction_from_score(normalized, 0.05)
    if direction == "bullish":
        reason_codes.append("positive_momentum")
    elif direction == "bearish":
        reason_codes.append("negative_momentum")
    else:
        reason_codes.append("flat_momentum")
    record = MomentumSignal(
        artifact_type="momentum_signal",
        signal_id=_signal_id(series.symbol, signal_date, "momentum", lookback_window),
        symbol=series.symbol,
        signal_date=signal_date,
        lookback_window=lookback_window,
        signal_family="momentum",
        raw_value=raw_value,
        normalized_score=normalized,
        direction=direction,
        confidence_proxy=_confidence(normalized, reason_codes),
        data_source_tier=series.data_source_tier,
        real_history_used=series.real_history_used,
        fixture_only=series.fixture_only,
        not_real_signal_evidence=series.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        return_5d=return_5d,
        return_10d=return_10d,
        return_20d=return_20d,
        momentum_slope=slope,
        record_hash="",
    )
    return MomentumSignal(**record.to_dict())


def compute_breakout_signal(series: SignalSeries, signal_date: str, lookback_window: int) -> BreakoutSignal:
    bars = _bars_through_date(series, signal_date)
    current = bars[-1]
    prior = bars[:-1][-lookback_window:]
    reason_codes: list[str] = []
    if len(prior) < lookback_window:
        reason_codes.append("insufficient_history")
    prior_high = round(max((bar.high for bar in prior), default=current.high), 6)
    prior_low = round(min((bar.low for bar in prior), default=current.low), 6)
    average_volume = _average([float(bar.volume) for bar in bars[:-1][-20:]])
    volume_confirmed = bool(average_volume > 0.0 and current.volume >= average_volume * 1.20)
    bullish_distance = (current.close - prior_high) / prior_high if prior_high > 0.0 else 0.0
    bearish_distance = (current.close - prior_low) / prior_low if prior_low > 0.0 else 0.0
    if bullish_distance > 0.0:
        raw_value = round(bullish_distance, 10)
        direction = "bullish"
        reason_codes.append("close_above_prior_high")
    elif bearish_distance < 0.0:
        raw_value = round(bearish_distance, 10)
        direction = "bearish"
        reason_codes.append("close_below_prior_low")
    else:
        raw_value = 0.0
        direction = "neutral"
        reason_codes.append("inside_prior_range")
    if volume_confirmed:
        reason_codes.append("volume_confirmed")
    else:
        reason_codes.append("volume_not_confirmed")
    volume_boost = 0.15 if volume_confirmed and direction != "neutral" else 0.0
    normalized = _clamp((raw_value / 0.05) + (volume_boost if raw_value > 0.0 else -volume_boost if raw_value < 0.0 else 0.0), -1.0, 1.0)
    record = BreakoutSignal(
        artifact_type="breakout_signal",
        signal_id=_signal_id(series.symbol, signal_date, "breakout", lookback_window),
        symbol=series.symbol,
        signal_date=signal_date,
        lookback_window=lookback_window,
        signal_family="breakout",
        raw_value=raw_value,
        normalized_score=normalized,
        direction=direction,
        confidence_proxy=_confidence(normalized, reason_codes),
        data_source_tier=series.data_source_tier,
        real_history_used=series.real_history_used,
        fixture_only=series.fixture_only,
        not_real_signal_evidence=series.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        prior_high=prior_high,
        prior_low=prior_low,
        close_price=round(current.close, 6),
        volume=current.volume,
        average_volume_20d=round(average_volume, 6),
        volume_confirmed=volume_confirmed,
        breakout_distance=raw_value,
        record_hash="",
    )
    return BreakoutSignal(**record.to_dict())


def compute_fakeout_signal(series: SignalSeries, signal_date: str, lookback_window: int) -> FakeoutSignal:
    bars = _bars_through_date(series, signal_date)
    reason_codes: list[str] = []
    if len(bars) < lookback_window + 2:
        reason_codes.append("insufficient_history")
    current = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else bars[-1]
    prior = bars[:-2][-lookback_window:]
    prior_high = round(max((bar.high for bar in prior), default=previous.high), 6)
    prior_low = round(min((bar.low for bar in prior), default=previous.low), 6)
    bullish_attempt = previous.close > prior_high
    bearish_attempt = previous.close < prior_low
    close_inside = prior_low < current.close < prior_high
    prior_breakout_attempt = bool(bullish_attempt or bearish_attempt)
    if bullish_attempt and close_inside:
        failed_direction = "failed_bullish_breakout"
        direction = "bearish"
        reversal = (previous.close - current.close) / previous.close if previous.close > 0.0 else 0.0
        reason_codes.extend(["prior_bullish_breakout_attempt", "close_back_inside_prior_range"])
    elif bearish_attempt and close_inside:
        failed_direction = "failed_bearish_breakdown"
        direction = "bullish"
        reversal = (current.close - previous.close) / previous.close if previous.close > 0.0 else 0.0
        reason_codes.extend(["prior_bearish_breakdown_attempt", "close_back_inside_prior_range"])
    else:
        failed_direction = "none"
        direction = "neutral"
        reversal = 0.0
        reason_codes.append("no_failed_breakout")
    raw_value = round(reversal if direction == "bullish" else -reversal if direction == "bearish" else 0.0, 10)
    normalized = _clamp(raw_value / 0.04, -1.0, 1.0)
    record = FakeoutSignal(
        artifact_type="fakeout_signal",
        signal_id=_signal_id(series.symbol, signal_date, "fakeout", lookback_window),
        symbol=series.symbol,
        signal_date=signal_date,
        lookback_window=lookback_window,
        signal_family="fakeout",
        raw_value=raw_value,
        normalized_score=normalized,
        direction=direction,
        confidence_proxy=_confidence(normalized, reason_codes),
        data_source_tier=series.data_source_tier,
        real_history_used=series.real_history_used,
        fixture_only=series.fixture_only,
        not_real_signal_evidence=series.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        prior_breakout_attempt=prior_breakout_attempt,
        close_back_inside_prior_range=close_inside,
        failed_breakout_direction=failed_direction,
        reversal_magnitude=round(abs(reversal), 10),
        prior_range_high=prior_high,
        prior_range_low=prior_low,
        record_hash="",
    )
    return FakeoutSignal(**record.to_dict())


def compute_trend_pullback_signal(series: SignalSeries, signal_date: str, lookback_window: int) -> TrendPullbackSignal:
    bars = _bars_through_date(series, signal_date)
    current = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else bars[-1]
    reason_codes: list[str] = []
    if len(bars) < 21:
        reason_codes.append("insufficient_history")
    ma20 = _moving_average(bars, 20)
    ma50 = _moving_average(bars, 50) if len(bars) >= 50 else 0.0
    if ma50 == 0.0:
        reason_codes.append("ma50_insufficient_history")
    slope = _momentum_slope(bars, 20)
    uptrend = bool(ma20 > 0.0 and (ma50 == 0.0 or ma20 >= ma50) and slope > 0.0)
    downtrend = bool(ma20 > 0.0 and ma50 > 0.0 and ma20 <= ma50 and slope < 0.0)
    pullback_distance = (current.close - ma20) / ma20 if ma20 > 0.0 else 0.0
    bullish_pullback = uptrend and current.low <= ma20 * 1.015 and current.close >= ma20 and current.close > previous.close
    bearish_pullback = downtrend and current.high >= ma20 * 0.985 and current.close <= ma20 and current.close < previous.close
    if bullish_pullback:
        direction = "bullish"
        reason_codes.extend(["uptrend", "pullback_to_ma", "continuation_confirmed"])
        raw_value = abs(slope) + max(0.0, -pullback_distance)
    elif bearish_pullback:
        direction = "bearish"
        reason_codes.extend(["downtrend", "pullback_to_ma", "continuation_confirmed"])
        raw_value = -(abs(slope) + max(0.0, pullback_distance))
    else:
        direction = "neutral"
        reason_codes.append("pullback_not_confirmed")
        raw_value = slope * 0.50
    normalized = _clamp(raw_value / 0.08, -1.0, 1.0)
    record = TrendPullbackSignal(
        artifact_type="trend_pullback_signal",
        signal_id=_signal_id(series.symbol, signal_date, "trend_pullback", lookback_window),
        symbol=series.symbol,
        signal_date=signal_date,
        lookback_window=lookback_window,
        signal_family="trend_pullback",
        raw_value=round(raw_value, 10),
        normalized_score=normalized,
        direction=direction,
        confidence_proxy=_confidence(normalized, reason_codes),
        data_source_tier=series.data_source_tier,
        real_history_used=series.real_history_used,
        fixture_only=series.fixture_only,
        not_real_signal_evidence=series.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        moving_average_20d=round(ma20, 6),
        moving_average_50d=round(ma50, 6),
        trend_slope=round(slope, 10),
        pullback_to_ma_distance=round(pullback_distance, 10),
        continuation_confirmed=bool(bullish_pullback or bearish_pullback),
        record_hash="",
    )
    return TrendPullbackSignal(**record.to_dict())


def compute_volatility_regime_signal(series: SignalSeries, signal_date: str, lookback_window: int) -> VolatilityRegimeSignal:
    bars = _bars_through_date(series, signal_date)
    reason_codes: list[str] = []
    if len(bars) < max(31, lookback_window + 1):
        reason_codes.append("insufficient_history")
    realized_vol = realized_volatility(bars, lookback_window)
    short_vol = realized_volatility(bars, 10)
    long_vol = realized_volatility(bars, 30)
    vol_ratio = round(short_vol / long_vol, 10) if long_vol > 0.0 else 0.0
    recent_range = _average(_true_ranges(bars[-5:]))
    prior_range = _average(_true_ranges(bars[-25:-5]))
    range_ratio = round(recent_range / prior_range, 10) if prior_range > 0.0 else 0.0
    expansion_trigger = bool(vol_ratio >= 1.25 or range_ratio >= 1.35)
    compression_trigger = bool((0.0 < vol_ratio <= 0.78) and (0.0 < range_ratio <= 0.75))
    if expansion_trigger:
        reason_codes.append("volatility_expansion")
        raw_value = vol_ratio - 1.0
    elif compression_trigger:
        reason_codes.append("volatility_compression")
        raw_value = -(1.0 - vol_ratio)
    else:
        reason_codes.append("volatility_neutral")
        raw_value = 0.0
    normalized = _clamp(raw_value, -1.0, 1.0)
    record = VolatilityRegimeSignal(
        artifact_type="volatility_regime_signal",
        signal_id=_signal_id(series.symbol, signal_date, "volatility_regime", lookback_window),
        symbol=series.symbol,
        signal_date=signal_date,
        lookback_window=lookback_window,
        signal_family="volatility_regime",
        raw_value=round(raw_value, 10),
        normalized_score=normalized,
        direction="neutral",
        confidence_proxy=_confidence(normalized, reason_codes),
        data_source_tier=series.data_source_tier,
        real_history_used=series.real_history_used,
        fixture_only=series.fixture_only,
        not_real_signal_evidence=series.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        realized_volatility=realized_vol,
        realized_volatility_ratio=vol_ratio,
        rolling_range_compression=range_ratio,
        expansion_trigger=expansion_trigger,
        compression_trigger=compression_trigger,
        record_hash="",
    )
    return VolatilityRegimeSignal(**record.to_dict())


def compute_relative_strength_signal(
    series: SignalSeries,
    benchmark_series: SignalSeries | None,
    signal_date: str,
    lookback_window: int,
) -> RelativeStrengthSignal:
    bars = _bars_through_date(series, signal_date)
    symbol_return = _simple_return(bars, lookback_window)
    reason_codes: list[str] = []
    if len(bars) < lookback_window + 1:
        reason_codes.append("insufficient_history")
    if benchmark_series is None:
        benchmark_symbol = ""
        benchmark_return = 0.0
        relative_return = 0.0
        normalized = 0.0
        direction = "neutral"
        missing_benchmark = True
        reason_codes.append("missing_benchmark")
    else:
        benchmark_bars = _bars_through_date(benchmark_series, signal_date)
        benchmark_symbol = benchmark_series.symbol
        benchmark_return = _simple_return(benchmark_bars, lookback_window)
        relative_return = round(symbol_return - benchmark_return, 10)
        normalized = _clamp(relative_return / 0.08, -1.0, 1.0)
        direction = _direction_from_score(normalized, 0.05)
        missing_benchmark = False
        if direction == "bullish":
            reason_codes.append("outperforming_benchmark")
        elif direction == "bearish":
            reason_codes.append("underperforming_benchmark")
        else:
            reason_codes.append("benchmark_inline")
    record = RelativeStrengthSignal(
        artifact_type="relative_strength_signal",
        signal_id=_signal_id(series.symbol, signal_date, "relative_strength", lookback_window),
        symbol=series.symbol,
        signal_date=signal_date,
        lookback_window=lookback_window,
        signal_family="relative_strength",
        raw_value=relative_return,
        normalized_score=normalized,
        direction=direction,
        confidence_proxy=_confidence(normalized, reason_codes),
        data_source_tier=series.data_source_tier,
        real_history_used=series.real_history_used,
        fixture_only=series.fixture_only,
        not_real_signal_evidence=series.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        symbol_return=symbol_return,
        benchmark_symbol=benchmark_symbol,
        benchmark_return=benchmark_return,
        relative_return=relative_return,
        relative_strength_rank=round(normalized, 6),
        missing_benchmark=missing_benchmark,
        record_hash="",
    )
    return RelativeStrengthSignal(**record.to_dict())


def compute_market_regime_signal(series: SignalSeries, signal_date: str, lookback_window: int) -> MarketRegimeSignal:
    bars = _bars_through_date(series, signal_date)
    reason_codes: list[str] = []
    if len(bars) < 50:
        reason_codes.append("insufficient_history")
        label = "insufficient_history"
        trend_state = "insufficient_history"
        volatility_state = "insufficient_history"
        drawdown_state = "insufficient_history"
        risk_proxy_state = "risk_unknown"
        direction = "neutral"
        raw_value = 0.0
        realized_vol = realized_volatility(bars, max(2, min(20, len(bars) - 1)))
        drawdown = 0.0
    else:
        current = bars[-1]
        ma20 = _moving_average(bars, 20)
        ma50 = _moving_average(bars, 50)
        slope = _momentum_slope(bars, 20)
        realized_vol = realized_volatility(bars, min(lookback_window, len(bars) - 1))
        drawdown = _drawdown(bars, lookback_window)
        if current.close >= ma20 >= ma50 and slope > 0.0:
            trend_state = "trend_up"
            direction = "bullish"
        elif current.close <= ma20 <= ma50 and slope < 0.0:
            trend_state = "trend_down"
            direction = "bearish"
        else:
            trend_state = "chop"
            direction = "neutral"
        volatility_state = "high_vol" if realized_vol >= 0.22 else "low_vol"
        drawdown_state = "drawdown" if drawdown <= -0.08 else "contained_drawdown"
        risk_proxy_state = "risk_on" if direction == "bullish" and drawdown > -0.08 else "risk_off" if direction == "bearish" or drawdown <= -0.08 else "risk_neutral"
        label = _regime_label(trend_state, volatility_state)
        raw_value = slope - abs(drawdown)
        reason_codes.extend([trend_state, volatility_state, drawdown_state, risk_proxy_state])
    normalized = _clamp(raw_value / 0.08, -1.0, 1.0)
    record = MarketRegimeSignal(
        artifact_type="market_regime_signal",
        signal_id=_signal_id(series.symbol, signal_date, "market_regime", lookback_window),
        symbol=series.symbol,
        signal_date=signal_date,
        lookback_window=lookback_window,
        signal_family="market_regime",
        raw_value=round(raw_value, 10),
        normalized_score=normalized,
        direction=direction,
        confidence_proxy=_confidence(normalized, reason_codes),
        data_source_tier=series.data_source_tier,
        real_history_used=series.real_history_used,
        fixture_only=series.fixture_only,
        not_real_signal_evidence=series.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        trend_state=trend_state,
        volatility_state=volatility_state,
        drawdown_state=drawdown_state,
        risk_proxy_state=risk_proxy_state,
        regime_label=label,
        drawdown=round(drawdown, 10),
        realized_volatility=realized_vol,
        record_hash="",
    )
    return MarketRegimeSignal(**record.to_dict())


def map_directional_setup_signal(signal_record: dict[str, Any]) -> DirectionalSetupSignal:
    direction = str(signal_record["direction"])
    normalized = round(float(signal_record["normalized_score"]), 6)
    confidence = round(float(signal_record["confidence_proxy"]), 6)
    reason_codes = [str(code) for code in signal_record.get("reason_codes", [])]
    source_family = str(signal_record["signal_family"])
    if direction == "bullish" and confidence >= 0.20 and normalized > 0.0:
        candidate_strategy = "long_call"
        option_structure = "long_call"
        long_call = True
        long_put = False
        no_trade = False
        reason_codes.append("bullish_setup_long_call_only")
    elif direction == "bearish" and confidence >= 0.20 and normalized < 0.0:
        candidate_strategy = "long_put"
        option_structure = "long_put"
        long_call = False
        long_put = True
        no_trade = False
        reason_codes.append("bearish_setup_long_put_only")
    else:
        candidate_strategy = "no_trade"
        option_structure = "none"
        long_call = False
        long_put = False
        no_trade = True
        reason_codes.append("neutral_or_low_confidence_no_trade")
    record = DirectionalSetupSignal(
        artifact_type="directional_setup_signal",
        signal_id=f"{signal_record['signal_id']}-directional-setup",
        symbol=str(signal_record["symbol"]),
        signal_date=str(signal_record["signal_date"]),
        lookback_window=int(signal_record["lookback_window"]),
        signal_family="directional_setup",
        raw_value=round(float(signal_record["raw_value"]), 10),
        normalized_score=normalized,
        direction=direction,
        confidence_proxy=confidence,
        data_source_tier=str(signal_record["data_source_tier"]),
        real_history_used=bool(signal_record["real_history_used"]),
        fixture_only=bool(signal_record["fixture_only"]),
        not_real_signal_evidence=bool(signal_record["not_real_signal_evidence"]),
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        source_signal_id=str(signal_record["signal_id"]),
        source_signal_family=source_family,
        candidate_strategy=candidate_strategy,
        option_structure=option_structure,
        long_call_candidate=long_call,
        long_put_candidate=long_put,
        no_trade=no_trade,
        spread_created=False,
        short_vol_created=False,
        naked_selling_created=False,
        same_day_churn_allowed=False,
        real_sizing_used=False,
        broker_required=False,
        record_hash="",
    )
    return DirectionalSetupSignal(**record.to_dict())


def realized_volatility(bars: list[PriceBar], lookback_window: int) -> float:
    if lookback_window < 2:
        raise ValueError("lookback_window must be at least 2")
    scoped = bars[-(lookback_window + 1):]
    returns = _daily_returns(scoped)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return round(math.sqrt(max(0.0, variance)) * math.sqrt(252.0), 10)


def series_from_rows(rows: list[dict[str, Any]], data_source_tier: str, real_history_used: bool, fixture_only: bool) -> SignalSeries:
    bars = [
        PriceBar.from_dict({
            "artifact_type": "price_bar",
            "symbol": row["symbol"],
            "date": row["date"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "adjusted_close": row.get("adjusted_close", row["close"]),
            "volume": row["volume"],
            "data_source_tier": data_source_tier,
            "real_history_used": real_history_used,
            "fixture_only": fixture_only,
            "not_real_signal_evidence": not real_history_used,
            "paper_only": True,
            "live_blocked": True,
            "record_hash": "",
        })
        for row in rows
    ]
    symbol = bars[0].symbol if bars else ""
    return make_signal_series(symbol, bars, data_source_tier, real_history_used, fixture_only, not real_history_used)


def _bars_through_date(series: SignalSeries, signal_date: str) -> list[PriceBar]:
    bars = [bar for bar in sorted(series.bars, key=lambda item: item.date) if bar.date <= signal_date]
    if not bars:
        raise ValueError(f"no bars at or before {signal_date} for {series.symbol}")
    if bars[-1].date != signal_date:
        raise ValueError(f"signal_date {signal_date} is missing for {series.symbol}")
    return bars


def _simple_return(bars: list[PriceBar], lookback_window: int) -> float:
    if len(bars) <= lookback_window:
        return 0.0
    start = bars[-(lookback_window + 1)].close
    end = bars[-1].close
    if start <= 0.0:
        return 0.0
    return round((end / start) - 1.0, 10)


def _momentum_slope(bars: list[PriceBar], lookback_window: int) -> float:
    if len(bars) <= lookback_window:
        return 0.0
    scoped = bars[-(lookback_window + 1):]
    start = scoped[0].close
    end = scoped[-1].close
    if start <= 0.0 or lookback_window <= 0:
        return 0.0
    return round(((end - start) / start) / lookback_window, 10)


def _moving_average(bars: list[PriceBar], lookback_window: int) -> float:
    if len(bars) < lookback_window:
        return 0.0
    return round(_average([bar.close for bar in bars[-lookback_window:]]), 6)


def _daily_returns(bars: list[PriceBar]) -> list[float]:
    output: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        if previous.close > 0.0:
            output.append((current.close / previous.close) - 1.0)
    return output


def _true_ranges(bars: list[PriceBar]) -> list[float]:
    return [
        ((bar.high - bar.low) / bar.close) if bar.close > 0.0 else 0.0
        for bar in bars
    ]


def _drawdown(bars: list[PriceBar], lookback_window: int) -> float:
    scoped = bars[-lookback_window:] if len(bars) >= lookback_window else bars
    max_close = max((bar.close for bar in scoped), default=0.0)
    current_close = scoped[-1].close if scoped else 0.0
    if max_close <= 0.0:
        return 0.0
    return round((current_close / max_close) - 1.0, 10)


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _direction_from_score(score: float, threshold: float) -> str:
    if score > threshold:
        return "bullish"
    if score < -threshold:
        return "bearish"
    return "neutral"


def _confidence(normalized_score: float, reason_codes: list[str]) -> float:
    penalty = 0.35 if "insufficient_history" in reason_codes else 0.0
    return round(_clamp(abs(normalized_score) - penalty, 0.0, 1.0), 6)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return round(max(minimum, min(maximum, value)), 6)


def _regime_label(trend_state: str, volatility_state: str) -> str:
    if trend_state == "trend_up" and volatility_state == "low_vol":
        return "trend_up_low_vol"
    if trend_state == "trend_up" and volatility_state == "high_vol":
        return "trend_up_high_vol"
    if trend_state == "trend_down" and volatility_state == "high_vol":
        return "trend_down_high_vol"
    if trend_state == "trend_down" and volatility_state == "low_vol":
        return "chop_low_vol"
    if volatility_state == "low_vol":
        return "chop_low_vol"
    return "chop_high_vol"


def _signal_id(symbol: str, signal_date: str, family: str, lookback_window: int) -> str:
    return f"{symbol.lower()}-{signal_date}-{family}-{lookback_window}"
