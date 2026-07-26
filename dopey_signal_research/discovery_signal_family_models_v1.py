"""Discovery signal family models V1."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryFamilyTemplate:
    family_id: str
    direction: str
    family_type: str
    feature_rules: tuple[tuple[str, str, float], ...]
    exit_policy: str
    dte: int
    moneyness: str


FAMILY_TEMPLATES: tuple[DiscoveryFamilyTemplate, ...] = (
    DiscoveryFamilyTemplate("continuation|pullback|high_volume", "bullish", "continuation", (("continuation", "pullback_continuation", 1.0), ("volume", "volume_percentile", 1.0)), "trend_follow", 14, "1pct_otm"),
    DiscoveryFamilyTemplate("continuation|breakout|rel_strength", "bullish", "continuation", (("continuation", "breakout_continuation", 1.0), ("relative_strength", "vs_spy", 0.01)), "trend_follow", 21, "ATM"),
    DiscoveryFamilyTemplate("reversal|overextension|mean_revert", "bearish", "reversal", (("reversal", "overextension", 0.03), ("reversal", "mean_reversion_pressure", 0.01)), "invalidation_strict", 14, "2pct_otm"),
    DiscoveryFamilyTemplate("reversal|failed_trend|put", "bearish", "reversal", (("trend_structure", "trend_failure", 1.0), ("volatility", "realized_vol_percentile", 0.5)), "theta_protective", 10, "1pct_otm"),
    DiscoveryFamilyTemplate("relative_strength|sector_lead", "bullish", "relative_strength", (("relative_strength", "vs_spy", 0.015), ("relative_strength", "rolling_relative_rank", 0.01)), "trend_follow", 21, "1pct_otm"),
    DiscoveryFamilyTemplate("relative_strength|weakness_put", "bearish", "relative_strength", (("relative_strength", "vs_spy", -0.015), ("regime", "risk_on_proxy", 0.0)), "invalidation_strict", 14, "2pct_otm"),
    DiscoveryFamilyTemplate("volatility|compression_break|call", "bullish", "volatility", (("volatility", "vol_compression_percentile", 0.6), ("price_structure", "compression_10d", 0.04)), "volatility_expansion_hunter", 21, "ATM"),
    DiscoveryFamilyTemplate("volatility|expansion_put", "bearish", "volatility", (("volatility", "realized_vol_percentile", 0.65), ("price_structure", "range_expansion", 0.02)), "theta_protective", 10, "1pct_otm"),
    DiscoveryFamilyTemplate("regime|risk_on|continuation", "bullish", "regime", (("regime", "risk_on_proxy", 1.0), ("trend_structure", "trend_persistence", 1.0)), "trend_follow", 30, "1pct_otm"),
    DiscoveryFamilyTemplate("regime|risk_off|put", "bearish", "regime", (("regime", "broad_market_regime", -1.0), ("risk_filter", "avoid_poor_regime_alignment", 0.0)), "invalidation_strict", 14, "2pct_otm"),
    DiscoveryFamilyTemplate("volume|climax_reversal", "bearish", "volume", (("volume", "volume_climax", 1.0), ("price_structure", "wick_rejection_proxy", 0.2)), "theta_protective", 7, "ATM"),
    DiscoveryFamilyTemplate("volume|dry_up_breakout", "bullish", "volume", (("volume", "volume_dry_up", 1.0), ("continuation", "breakout_continuation", 1.0)), "trend_follow", 14, "1pct_otm"),
    DiscoveryFamilyTemplate("hybrid|continuation_reversal_filter", "bullish", "hybrid", (("continuation", "pullback_continuation", 1.0), ("reversal", "overextension", 0.0)), "trend_follow", 21, "1pct_otm"),
    DiscoveryFamilyTemplate("no_trade|thin_volume_filter", "no_trade", "no_trade_filter", (("risk_filter", "avoid_thin_volume", 1.0),), "invalidation_strict", 14, "ATM"),
    DiscoveryFamilyTemplate("no_trade|overextended_filter", "no_trade", "no_trade_filter", (("risk_filter", "avoid_overextended_move", 1.0),), "invalidation_strict", 14, "ATM"),
)
