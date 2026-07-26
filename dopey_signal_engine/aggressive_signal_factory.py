"""Build aggressive long-premium signal candidates from chart features."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def generate_aggressive_signals(features_by_symbol: dict[str, dict], tier_by_symbol: dict[str, str]) -> list[dict]:
    candidates: list[dict] = []
    for symbol, feature in sorted(features_by_symbol.items()):
        if not feature:
            continue
        candidates.extend(_symbol_candidates(symbol, feature, tier_by_symbol.get(symbol, "market_vision")))
    for index, candidate in enumerate(candidates):
        candidate["signal_id"] = f"signal-{index + 1:05d}-{candidate['symbol']}-{candidate['setup_family']}"
        candidate["record_hash"] = stable_hash(candidate)
    return candidates


def _symbol_candidates(symbol: str, feature: dict, data_tier: str) -> list[dict]:
    close = float(feature["close"])
    atr = max(float(feature["atr_14"]), close * 0.01)
    rsi = float(feature["rsi_14"])
    macd = float(feature["macd"])
    macd_signal = float(feature["macd_signal"])
    trend = str(feature["trend_regime"])
    vol = str(feature["volatility_regime"])
    records: list[dict] = []
    if trend in {"strong_uptrend", "uptrend"} and macd >= macd_signal:
        records.append(_candidate(symbol, feature, "bullish", "long_call", "momentum_continuation", close + atr * 0.25, close - atr * 1.2, atr * 2.4, 0.76, 0.73, 0.34, data_tier))
        records.append(_candidate(symbol, feature, "bullish", "long_call", "trend_pullback", float(feature["sma_21"]), close - atr * 1.5, atr * 2.0, 0.68, 0.69, 0.42, data_tier))
    if trend in {"strong_downtrend", "downtrend"} and macd <= macd_signal:
        records.append(_candidate(symbol, feature, "bearish", "long_put", "relative_weakness", close - atr * 0.25, close + atr * 1.2, atr * 2.4, 0.75, 0.72, 0.36, data_tier))
        records.append(_candidate(symbol, feature, "bearish", "long_put", "failed_breakout_fakeout_reversal", float(feature["sma_21"]), close + atr * 1.5, atr * 2.0, 0.66, 0.68, 0.45, data_tier))
    if close > float(feature["resistance"]) * 0.995:
        records.append(_candidate(symbol, feature, "bullish", "long_call", "breakout", close + atr * 0.1, close - atr * 1.0, atr * 2.8, 0.71, 0.77, 0.48, data_tier))
    if close < float(feature["support"]) * 1.005:
        records.append(_candidate(symbol, feature, "bearish", "long_put", "breakdown", close - atr * 0.1, close + atr * 1.0, atr * 2.8, 0.71, 0.77, 0.48, data_tier))
    if vol == "compressed_volatility":
        direction = "bullish" if close >= float(feature["sma_50"]) else "bearish"
        records.append(_candidate(symbol, feature, direction, "long_call" if direction == "bullish" else "long_put", "volatility_squeeze", close, close - atr if direction == "bullish" else close + atr, atr * 2.2, 0.63, 0.74, 0.39, data_tier))
    if rsi > 78.0:
        records.append(_candidate(symbol, feature, "bearish", "long_put", "mean_reversion_after_exhaustion", close - atr * 0.2, close + atr * 1.0, atr * 1.8, 0.58, 0.62, 0.52, data_tier))
    if rsi < 22.0:
        records.append(_candidate(symbol, feature, "bullish", "long_call", "mean_reversion_after_exhaustion", close + atr * 0.2, close - atr * 1.0, atr * 1.8, 0.58, 0.62, 0.52, data_tier))
    records.append(_candidate(symbol, feature, "neutral", "no_trade", "no_trade_gate", close, close, 0.0, 0.35, 0.15, 0.12, data_tier))
    return records


def _candidate(symbol: str, feature: dict, direction: str, intent: str, family: str, entry: float, invalidation: float, target_move: float, confidence: float, asymmetry: float, risk: float, data_tier: str) -> dict:
    no_trade_reason = "quality_gate_reference" if intent == "no_trade" else ""
    source_type = str(feature.get("market_data_source_type", "fixture_fallback"))
    return {
        "artifact_type": "aggressive_signal_candidate",
        "symbol": symbol,
        "timestamp": feature["date"],
        "direction": direction,
        "trade_intent": intent,
        "setup_family": family,
        "entry_trigger": round(entry, 4),
        "invalidation_level": round(invalidation, 4),
        "target_move": round(target_move, 4),
        "expected_move_proxy": round(max(float(feature["atr_14"]), float(feature["close"]) * 0.01), 4),
        "volatility_regime": feature["volatility_regime"],
        "trend_regime": feature["trend_regime"],
        "confidence_score": round(confidence, 4),
        "asymmetry_score": round(asymmetry, 4),
        "liquidity_proxy_score": 0.72,
        "risk_score": round(risk, 4),
        "no_trade_reason": no_trade_reason,
        "data_tier": data_tier,
        "market_data_source_type": source_type,
        "paper_only": True,
        "live_blocked": True,
    }
