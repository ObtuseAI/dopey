"""Extended signal family registry for public-market signal mutation V4."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import record_with_hash


SIGNAL_FAMILIES_V4 = [
    # Bullish families (long call)
    ("bollinger_expansion", "bullish", "long_call"),
    ("atr_compression_breakout", "bullish", "long_call"),
    ("sector_relative_strength", "bullish", "long_call"),
    ("relative_strength_vs_spy", "bullish", "long_call"),
    ("volatility_squeeze_breakout", "bullish", "long_call"),
    ("moving_average_reclaim", "bullish", "long_call"),
    ("support_bounce", "bullish", "long_call"),
    ("high_volume_breakout", "bullish", "long_call"),
    ("trend_pullback_continuation", "bullish", "long_call"),
    ("gap_continuation", "bullish", "long_call"),
    ("resistance_breakout", "bullish", "long_call"),
    ("rsi_reclaim", "bullish", "long_call"),
    ("macd_cross_continuation", "bullish", "long_call"),
    ("atr_expansion", "bullish", "long_call"),
    # Bearish families (long put)
    ("bollinger_mean_reversion", "bearish", "long_put"),
    ("sector_relative_weakness", "bearish", "long_put"),
    ("relative_weakness_vs_spy", "bearish", "long_put"),
    ("support_failure", "bearish", "long_put"),
    ("moving_average_rejection", "bearish", "long_put"),
    ("gap_fade", "bearish", "long_put"),
    ("trend_exhaustion_reversal", "bearish", "long_put"),
    ("low_volume_fakeout", "bearish", "long_put"),
    ("volatility_squeeze_breakdown", "bearish", "long_put"),
    ("resistance_rejection", "bearish", "long_put"),
    ("rsi_failure", "bearish", "long_put"),
    ("macd_divergence_proxy", "bearish", "long_put"),
    # Neutral research-only lanes
    ("zero_dte_special_high_momentum_research_lane", "neutral", "no_trade"),
    ("no_trade_capital_preservation", "neutral", "no_trade"),
]


def public_signal_family_registry_v4() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, family in enumerate(SIGNAL_FAMILIES_V4):
        family_name, direction, trade_intent = family
        record = {
            "artifact_type": "public_signal_family_registry_v4",
            "family_rank": index + 1,
            "setup_family": family_name,
            "default_direction": direction,
            "default_trade_intent": trade_intent,
            "allowed_trade_intents": ["long_call", "long_put", "no_trade"],
            "fixture_allowed": False,
            "live_trading_enabled": False,
        }
        records.append(record_with_hash(record, "record_hash"))
    return records
