"""Signal model constants."""
from __future__ import annotations


SIGNAL_ENGINE_VERSION = "dopey-aggressive-signal-engine-v1"
SIGNAL_FAMILIES = [
    "momentum_continuation", "trend_pullback", "breakout", "failed_breakout_fakeout_reversal",
    "volatility_squeeze", "gap_continuation", "gap_fade", "relative_strength",
    "relative_weakness", "market_regime_switch", "sector_rotation",
    "mean_reversion_after_exhaustion", "zero_dte_special_setup", "no_trade_gate",
]

