"""Chart model constants for the DOPEY chart vision engine."""
from __future__ import annotations


CHART_VISION_VERSION = "dopey-chart-vision-v1"
CHART_FEATURE_FIELDS = [
    "symbol", "date", "close", "sma_8", "sma_21", "sma_50", "sma_200",
    "vwap_proxy", "atr_14", "realized_vol_21", "bb_upper", "bb_lower",
    "rsi_14", "macd", "macd_signal", "support", "resistance",
    "trend_regime", "volatility_regime",
]

