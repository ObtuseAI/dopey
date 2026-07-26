"""Stdlib indicator engine for market-vision charts."""
from __future__ import annotations

import math


def build_indicator_rows(symbol: str, rows: list[dict]) -> list[dict]:
    closes = [_float(row["close"]) for row in rows]
    highs = [_float(row["high"]) for row in rows]
    lows = [_float(row["low"]) for row in rows]
    volumes = [_float(row["volume"]) for row in rows]
    output: list[dict] = []
    for index, row in enumerate(rows):
        close = closes[index]
        atr = _atr(highs, lows, closes, index, 14)
        rv = _realized_vol(closes, index, 21)
        sma_21 = _sma(closes, index, 21)
        sma_50 = _sma(closes, index, 50)
        sma_200 = _sma(closes, index, 200)
        std_20 = _std(closes, index, 20)
        macd = _ema(closes, index, 12) - _ema(closes, index, 26)
        macd_signal = _macd_signal(closes, index)
        support = min(lows[max(0, index - 30):index + 1]) if rows else 0.0
        resistance = max(highs[max(0, index - 30):index + 1]) if rows else 0.0
        feature = {
            "artifact_type": "chart_feature_record",
            "symbol": symbol,
            "date": row["date"],
            "open": _round(_float(row["open"])),
            "high": _round(highs[index]),
            "low": _round(lows[index]),
            "close": _round(close),
            "volume": int(volumes[index]),
            "sma_8": _round(_sma(closes, index, 8)),
            "sma_21": _round(sma_21),
            "sma_50": _round(sma_50),
            "sma_200": _round(sma_200),
            "vwap_proxy": _round(_vwap_proxy(closes, volumes, index, 21)),
            "atr_14": _round(atr),
            "realized_vol_21": _round(rv),
            "bb_upper": _round(sma_21 + 2.0 * std_20),
            "bb_lower": _round(sma_21 - 2.0 * std_20),
            "rsi_14": _round(_rsi(closes, index, 14)),
            "macd": _round(macd),
            "macd_signal": _round(macd_signal),
            "support": _round(support),
            "resistance": _round(resistance),
            "trend_regime": _trend_regime(close, sma_21, sma_50, sma_200),
            "volatility_regime": _volatility_regime(rv),
            "paper_only": True,
            "live_blocked": True,
        }
        output.append(feature)
    return output


def latest_feature(features: list[dict]) -> dict:
    if not features:
        return {}
    return features[-1]


def _float(value: object) -> float:
    return float(value)


def _round(value: float) -> float:
    return round(value, 6)


def _window(values: list[float], index: int, period: int) -> list[float]:
    return values[max(0, index - period + 1):index + 1]


def _sma(values: list[float], index: int, period: int) -> float:
    items = _window(values, index, period)
    return sum(items) / len(items) if items else 0.0


def _std(values: list[float], index: int, period: int) -> float:
    items = _window(values, index, period)
    if len(items) < 2:
        return 0.0
    mean = sum(items) / len(items)
    return math.sqrt(sum((value - mean) ** 2 for value in items) / (len(items) - 1))


def _ema(values: list[float], index: int, period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    start = max(0, index - period * 3)
    ema = values[start]
    for value in values[start + 1:index + 1]:
        ema = value * alpha + ema * (1.0 - alpha)
    return ema


def _macd_signal(values: list[float], index: int) -> float:
    macd_values: list[float] = []
    start = max(0, index - 35)
    for cursor in range(start, index + 1):
        macd_values.append(_ema(values, cursor, 12) - _ema(values, cursor, 26))
    return _ema(macd_values, len(macd_values) - 1, 9) if macd_values else 0.0


def _rsi(values: list[float], index: int, period: int) -> float:
    if index == 0:
        return 50.0
    start = max(1, index - period + 1)
    gains = 0.0
    losses = 0.0
    for cursor in range(start, index + 1):
        change = values[cursor] - values[cursor - 1]
        if change >= 0:
            gains += change
        else:
            losses += abs(change)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(highs: list[float], lows: list[float], closes: list[float], index: int, period: int) -> float:
    start = max(0, index - period + 1)
    values: list[float] = []
    for cursor in range(start, index + 1):
        previous_close = closes[cursor - 1] if cursor > 0 else closes[cursor]
        values.append(max(highs[cursor] - lows[cursor], abs(highs[cursor] - previous_close), abs(lows[cursor] - previous_close)))
    return sum(values) / len(values) if values else 0.0


def _realized_vol(values: list[float], index: int, period: int) -> float:
    start = max(1, index - period + 1)
    returns: list[float] = []
    for cursor in range(start, index + 1):
        returns.append(math.log(values[cursor] / values[cursor - 1]))
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    daily = math.sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))
    return daily * math.sqrt(252.0)


def _vwap_proxy(closes: list[float], volumes: list[float], index: int, period: int) -> float:
    close_window = _window(closes, index, period)
    volume_window = _window(volumes, index, period)
    denominator = sum(volume_window)
    if denominator <= 0:
        return close_window[-1] if close_window else 0.0
    return sum(close * volume for close, volume in zip(close_window, volume_window)) / denominator


def _trend_regime(close: float, sma_21: float, sma_50: float, sma_200: float) -> str:
    if close > sma_21 > sma_50 > sma_200:
        return "strong_uptrend"
    if close > sma_50 and sma_21 > sma_50:
        return "uptrend"
    if close < sma_21 < sma_50 < sma_200:
        return "strong_downtrend"
    if close < sma_50 and sma_21 < sma_50:
        return "downtrend"
    return "mixed"


def _volatility_regime(realized_vol: float) -> str:
    if realized_vol >= 0.45:
        return "high_volatility"
    if realized_vol >= 0.25:
        return "elevated_volatility"
    if realized_vol <= 0.12:
        return "compressed_volatility"
    return "normal_volatility"

