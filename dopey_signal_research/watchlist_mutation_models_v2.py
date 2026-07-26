"""Watchlist mutation models V2."""
from __future__ import annotations

MUTATION_TYPES = (
    "symbol_expansion",
    "sector_expansion",
    "regime_expansion",
    "holdout_repair",
    "split_pass_repair",
    "profit_factor_repair",
    "expectancy_repair",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "risk_filter_tightening",
    "filter_loosening",
    "relative_strength_threshold_retune",
    "volatility_threshold_retune",
    "volume_threshold_retune",
    "stop_target_retune",
    "no_trade_filter_injection",
)
