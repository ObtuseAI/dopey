"""Equity-first directional swing thesis construction."""
from __future__ import annotations

import math
from typing import Any

from .market_structure import Bar, average_true_range


SECTOR_ETF_BY_THEME: dict[str, str] = {
    "ai": "XLK",
    "quantum": "XLK",
    "financials": "XLF",
    "energy": "XLE",
    "consumer": "XLY",
    "defensive": "XLP",
    "healthcare": "XLV",
    "industrials": "XLI",
    "utilities": "XLU",
    "crypto": "IBIT",
}


def _validated_support_score(
    evidence: dict[str, Any],
    field: str,
) -> float | None:
    value = evidence.get(field)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        return None
    return float(value)


def technical_confirmation(
    rows: list[Bar],
    benchmark_rows: list[Bar],
    sector_rows: list[Bar] | None,
    structure: dict[str, Any],
) -> dict[str, Any]:
    closes = [row["close"] for row in rows]
    if len(closes) < 200:
        return {
            "technical_status": "insufficient_200_bar_history",
            "bullish_score": 0.0,
            "bearish_score": 0.0,
        }
    current = closes[-1]
    returns = {horizon: _return(closes, horizon) for horizon in (5, 20, 60, 126)}
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200
    rsi = _rsi(closes, 14)
    volume_z = _z_score([float(row["volume"]) for row in rows], 20)
    benchmark_rs20 = returns[20] - _return([row["close"] for row in benchmark_rows], 20)
    benchmark_rs60 = returns[60] - _return([row["close"] for row in benchmark_rows], 60)
    sector_rs20 = returns[20] - _return([row["close"] for row in sector_rows], 20) if sector_rows else 0.0
    structure_agreement = float(structure.get("multi_timeframe_agreement_score", 0.0))
    structure_bull = _clamp01(0.5 + structure_agreement * 0.5)
    structure_bear = _clamp01(0.5 - structure_agreement * 0.5)
    ma_bull = sum((current > ma20, ma20 > ma50, ma50 > ma200)) / 3.0
    ma_bear = sum((current < ma20, ma20 < ma50, ma50 < ma200)) / 3.0
    momentum_bull = _clamp01(
        0.25 * _scale_signed(returns[20], 0.12)
        + 0.25 * _scale_signed(returns[60], 0.25)
        + 0.20 * _scale_signed(benchmark_rs60, 0.15)
        + 0.15 * _scale_signed(sector_rs20, 0.10)
        + 0.15 * _clamp01((rsi - 35.0) / 35.0)
    )
    momentum_bear = _clamp01(
        0.25 * _scale_signed(-returns[20], 0.12)
        + 0.25 * _scale_signed(-returns[60], 0.25)
        + 0.20 * _scale_signed(-benchmark_rs60, 0.15)
        + 0.15 * _scale_signed(-sector_rs20, 0.10)
        + 0.15 * _clamp01((65.0 - rsi) / 35.0)
    )
    volume_bull = _clamp01(0.5 + math.copysign(min(abs(volume_z) / 3.0, 0.5), returns[5]) if returns[5] else 0.5)
    volume_bear = _clamp01(1.0 - volume_bull)
    bullish = _clamp01(0.42 * structure_bull + 0.25 * ma_bull + 0.23 * momentum_bull + 0.10 * volume_bull)
    bearish = _clamp01(0.42 * structure_bear + 0.25 * ma_bear + 0.23 * momentum_bear + 0.10 * volume_bear)
    return {
        "technical_status": "complete",
        "bullish_score": round(bullish, 6),
        "bearish_score": round(bearish, 6),
        "structure_bullish_score": round(structure_bull, 6),
        "structure_bearish_score": round(structure_bear, 6),
        "ma_alignment_bullish": round(ma_bull, 6),
        "ma_alignment_bearish": round(ma_bear, 6),
        "momentum_bullish": round(momentum_bull, 6),
        "momentum_bearish": round(momentum_bear, 6),
        "return_5d": round(returns[5], 6),
        "return_20d": round(returns[20], 6),
        "return_60d": round(returns[60], 6),
        "return_126d": round(returns[126], 6),
        "relative_strength_spy_20d": round(benchmark_rs20, 6),
        "relative_strength_spy_60d": round(benchmark_rs60, 6),
        "relative_strength_sector_20d": round(sector_rs20, 6),
        "rsi_14": round(rsi, 4),
        "volume_z_20": round(volume_z, 4),
        "ma20": round(ma20, 6),
        "ma50": round(ma50, 6),
        "ma200": round(ma200, 6),
    }


def build_equity_swing_thesis(
    symbol: str,
    rows: list[Bar],
    structure: dict[str, Any],
    technical: dict[str, Any],
    fundamental: dict[str, Any],
    earnings_date: str | None,
) -> dict[str, Any]:
    current = float(structure.get("current_price", rows[-1]["close"]))
    atr_value = float(structure.get("daily_atr", average_true_range(rows, 14)))
    bullish_technical = float(technical.get("bullish_score", 0.0))
    bearish_technical = float(technical.get("bearish_score", 0.0))
    bullish_fundamental_value = _validated_support_score(
        fundamental,
        "bullish_support_score",
    )
    bearish_fundamental_value = _validated_support_score(
        fundamental,
        "bearish_support_score",
    )
    fundamental_evidence_complete = (
        bullish_fundamental_value is not None
        and bearish_fundamental_value is not None
    )
    bullish_fundamental = (
        bullish_fundamental_value
        if bullish_fundamental_value is not None
        else 0.0
    )
    bearish_fundamental = (
        bearish_fundamental_value
        if bearish_fundamental_value is not None
        else 0.0
    )
    bullish = 0.78 * bullish_technical + 0.22 * bullish_fundamental
    bearish = 0.78 * bearish_technical + 0.22 * bearish_fundamental
    support = structure.get("nearest_support")
    resistance = structure.get("nearest_resistance")
    setup_bull = _setup_quality("bullish", structure, current, atr_value)
    setup_bear = _setup_quality("bearish", structure, current, atr_value)
    reason_codes: list[str] = []
    if not fundamental_evidence_complete:
        reason_codes.append("missing_or_invalid_fundamental_support_scores")
    if bullish >= 0.62 and bullish - bearish >= 0.10 and bullish_technical >= 0.60 and bullish_fundamental >= 0.48 and setup_bull["quality"] >= 0.42:
        direction = "bullish"
        trade_intent = "long_call"
        setup = setup_bull
        reason_codes.extend(["equity_technical_direction_bullish", "fundamental_not_contradictory", str(setup["setup_type"])])
    elif bearish >= 0.62 and bearish - bullish >= 0.10 and bearish_technical >= 0.60 and bearish_fundamental >= 0.48 and setup_bear["quality"] >= 0.42:
        direction = "bearish"
        trade_intent = "long_put"
        setup = setup_bear
        reason_codes.extend(["equity_technical_direction_bearish", "fundamental_not_contradictory", str(setup["setup_type"])])
    else:
        direction = "neutral"
        trade_intent = "no_trade"
        setup = setup_bull if bullish >= bearish else setup_bear
        reason_codes.append("equity_confluence_gate_not_cleared")
    invalidation, target = _structure_prices(direction, current, atr_value, support, resistance, structure)
    if trade_intent != "no_trade" and (invalidation is None or target is None):
        trade_intent = "no_trade"
        reason_codes.append("missing_confirmed_structure_invalidation_or_target")
    reward_risk = _reward_risk(direction, current, invalidation, target)
    if trade_intent != "no_trade" and reward_risk < 1.35:
        trade_intent = "no_trade"
        reason_codes.append("structure_reward_risk_below_1_35")
    expected_hold = _expected_hold_days(current, target, atr_value)
    return {
        "artifact_type": "equity_first_swing_thesis",
        "symbol": symbol,
        "as_of_date": rows[-1]["date"],
        "thesis_status": "actionable_shadow_thesis" if trade_intent != "no_trade" else "no_trade",
        "direction": direction,
        "trade_intent": trade_intent,
        "setup_type": setup["setup_type"],
        "setup_quality_score": round(float(setup["quality"]), 6),
        "equity_bullish_score": round(bullish, 6),
        "equity_bearish_score": round(bearish, 6),
        "technical_weight": 0.78,
        "fundamental_weight": 0.22,
        "options_direction_weight": 0.0,
        "direction_source_policy": "stock_technicals_and_fundamentals_only_options_select_contract_after_direction",
        "entry_reference_price": round(current, 6),
        "invalidation_price": round(invalidation, 6) if invalidation is not None else None,
        "target_price": round(target, 6) if target is not None else None,
        "reward_risk_ratio": round(reward_risk, 6),
        "expected_hold_trading_days": expected_hold,
        "earnings_date": earnings_date,
        "reason_codes": reason_codes,
        "technical_confirmation": technical,
        "fundamental_confirmation": fundamental,
        "structure_reference": {
            "multi_timeframe_direction": structure.get("multi_timeframe_direction"),
            "multi_timeframe_agreement_score": structure.get("multi_timeframe_agreement_score"),
            "nearest_support": support,
            "nearest_resistance": resistance,
        },
        "not_edge_evidence": True,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _setup_quality(direction: str, structure: dict[str, Any], current: float, atr_value: float) -> dict[str, float | str]:
    daily = next(
        (record for record in structure.get("timeframes", []) if record.get("timeframe") == "daily"),
        {},
    )
    channel = daily.get("channel", {})
    position = float(channel.get("channel_position", 0.5))
    channel_quality = float(channel.get("quality_score", 0.0))
    support = structure.get("nearest_support")
    resistance = structure.get("nearest_resistance")
    if direction == "bullish":
        zone = support
        channel_fit = _clamp01((0.55 - position) / 0.55) if channel.get("direction") == "uptrend" else 0.0
        setup_type = "channel_support_pullback" if channel_fit >= 0.35 else "support_bounce"
    else:
        zone = resistance
        channel_fit = _clamp01((position - 0.45) / 0.55) if channel.get("direction") == "downtrend" else 0.0
        setup_type = "channel_resistance_rally" if channel_fit >= 0.35 else "resistance_rejection"
    if zone is None or atr_value <= 0.0:
        zone_fit = 0.0
    else:
        distance_atr = abs(float(zone["zone_mid"]) - current) / atr_value
        zone_fit = _clamp01(1.0 - distance_atr / 3.0) * float(zone.get("confluence_score", 0.0))
    quality = 0.55 * zone_fit + 0.45 * channel_fit * channel_quality
    return {"setup_type": setup_type, "quality": quality}


def _structure_prices(
    direction: str,
    current: float,
    atr_value: float,
    support: dict[str, Any] | None,
    resistance: dict[str, Any] | None,
    structure: dict[str, Any],
) -> tuple[float | None, float | None]:
    daily = next((record for record in structure.get("timeframes", []) if record.get("timeframe") == "daily"), {})
    channel = daily.get("channel", {})
    if direction == "bullish":
        base = float(support["zone_low"]) if support else float(channel.get("lower_bound", 0.0))
        target = float(resistance["zone_mid"]) if resistance else float(channel.get("upper_bound", 0.0))
        invalidation = base - 0.35 * atr_value if 0.0 < base < current else None
        return invalidation, target if target > current else None
    if direction == "bearish":
        base = float(resistance["zone_high"]) if resistance else float(channel.get("upper_bound", 0.0))
        target = float(support["zone_mid"]) if support else float(channel.get("lower_bound", 0.0))
        invalidation = base + 0.35 * atr_value if base > current else None
        return invalidation, target if 0.0 < target < current else None
    return None, None


def _reward_risk(direction: str, current: float, invalidation: float | None, target: float | None) -> float:
    if invalidation is None or target is None:
        return 0.0
    reward = target - current if direction == "bullish" else current - target
    risk = current - invalidation if direction == "bullish" else invalidation - current
    return reward / risk if reward > 0.0 and risk > 0.0 else 0.0


def _expected_hold_days(current: float, target: float | None, atr_value: float) -> int:
    if target is None or atr_value <= 0.0:
        return 0
    atr_units = abs(target - current) / atr_value
    return max(5, min(30, int(math.ceil(atr_units * 4.0))))


def _return(values: list[float], horizon: int) -> float:
    if len(values) <= horizon or values[-horizon - 1] <= 0.0:
        return 0.0
    return values[-1] / values[-horizon - 1] - 1.0


def _rsi(closes: list[float], period: int) -> float:
    if len(closes) <= period:
        return 50.0
    changes = [later - earlier for earlier, later in zip(closes[-period - 1 :], closes[-period:])]
    gains = sum(max(change, 0.0) for change in changes) / period
    losses = sum(max(-change, 0.0) for change in changes) / period
    if losses == 0.0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gains / losses)


def _z_score(values: list[float], period: int) -> float:
    if len(values) <= period:
        return 0.0
    history = values[-period - 1 : -1]
    mean = sum(history) / len(history)
    variance = sum((value - mean) ** 2 for value in history) / max(len(history) - 1, 1)
    deviation = math.sqrt(variance)
    return (values[-1] - mean) / deviation if deviation > 0.0 else 0.0


def _scale_signed(value: float, scale: float) -> float:
    return _clamp01(0.5 + value / max(2.0 * scale, 1e-9))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
