"""Profitable slice mining models V4."""
from __future__ import annotations

SLICE_DIMENSIONS_V4 = (
    "family",
    "cohort",
    "subfamily",
    "symbol",
    "sector",
    "regime",
    "year",
    "month",
    "direction",
    "DTE",
    "moneyness",
    "exit_policy",
    "hold_window",
    "stop_target_bucket",
    "relative_strength_bucket",
    "volatility_bucket",
    "volume_bucket",
    "trend_state",
    "holdout_partition",
    "split_partition",
    "slippage_stress",
    "theta_stress",
    "iv_shock_stress",
)

PROFITABLE_KEEP_CRITERIA = {
    "min_trade_count": 30,
    "min_pf": 1.05,
    "min_win_rate": 0.40,
    "min_symbol_count": 5,
    "min_sector_count": 4,
    "min_split_pass_rate": 0.50,
}

LOSS_DRIVER_CRITERIA = {
    "min_trade_count_for_loss_attribution": 20,
    "negative_pf_threshold": 0.95,
    "negative_expectancy_threshold": 0.0,
    "max_drawdown_threshold": 200.0,
}

RETUNE_RECOMMENDATION_THRESHOLDS = {
    "pf_between": (0.95, 1.10),
    "holdout_below": 0.55,
    "split_pass_below": 0.55,
    "concentration_share_above": 0.30,
}

PRUNE_RECOMMENDATION_THRESHOLDS = {
    "min_trade_count": 20,
    "negative_pf_threshold": 0.90,
    "negative_expectancy_threshold": -0.10,
    "min_symbol_count_loss_attribution": 1,
}
