"""Pattern detector for chart-vision records."""
from __future__ import annotations


def detect_chart_patterns(symbol: str, features: list[dict], data_tier: str) -> list[dict]:
    if len(features) < 3:
        return []
    latest = features[-1]
    previous = features[-2]
    records: list[dict] = []
    close = float(latest["close"])
    resistance = float(previous["resistance"])
    support = float(previous["support"])
    atr = max(float(latest["atr_14"]), 0.01)
    gap = float(latest["open"]) - float(previous["close"])
    if close > resistance and close - resistance > atr * 0.15:
        records.append(_pattern(symbol, latest, "breakout", "bullish", data_tier))
    if close < support and support - close > atr * 0.15:
        records.append(_pattern(symbol, latest, "breakdown", "bearish", data_tier))
    if abs(gap) > atr * 0.6:
        records.append(_pattern(symbol, latest, "gap_up" if gap > 0 else "gap_down", "bullish" if gap > 0 else "bearish", data_tier))
    if latest["trend_regime"] in {"strong_uptrend", "strong_downtrend"}:
        records.append(_pattern(symbol, latest, latest["trend_regime"], "bullish" if "up" in latest["trend_regime"] else "bearish", data_tier))
    if not records:
        records.append(_pattern(symbol, latest, "no_trade_quality_gate", "neutral", data_tier))
    return records


def _pattern(symbol: str, feature: dict, pattern_name: str, direction: str, data_tier: str) -> dict:
    return {
        "artifact_type": "chart_pattern_record",
        "symbol": symbol,
        "timestamp": feature["date"],
        "pattern_name": pattern_name,
        "direction": direction,
        "close": feature["close"],
        "support": feature["support"],
        "resistance": feature["resistance"],
        "trend_regime": feature["trend_regime"],
        "volatility_regime": feature["volatility_regime"],
        "data_tier": data_tier,
        "paper_only": True,
        "live_blocked": True,
    }

