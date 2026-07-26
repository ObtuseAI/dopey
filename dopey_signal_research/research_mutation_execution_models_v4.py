"""V3 mutation queue execution models for V4.

Mirrors the V3 execution categories but extended to map each V3 mutation
type to its intended repair axis and to record why any mutation is
skipped.
"""
from __future__ import annotations

MUTATION_EXECUTION_TYPES_V4 = (
    "profit_factor_repair",
    "holdout_repair",
    "split_repair",
    "expectancy_repair",
    "drawdown_repair",
    "no_trade_filter_injection",
    "symbol_pruning",
    "sector_pruning",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "risk_filter_retune",
    "relative_strength_threshold_retune",
    "volatility_threshold_retune",
    "volume_threshold_retune",
    "stop_target_retune",
    "family_template_split",
)

V3_MUTATION_TO_REPAIR_AXIS = {
    "profit_factor_repair": "profit_factor",
    "holdout_repair": "holdout_survival",
    "split_repair": "split_pass_rate",
    "expectancy_repair": "expectancy",
    "drawdown_repair": "max_drawdown",
    "no_trade_filter_injection": "no_trade_filter_benefit",
    "symbol_pruning": "symbol_coverage",
    "sector_pruning": "sector_coverage",
}

MUTATION_INTENDED_FIX_V4 = {
    "profit_factor_repair": "tighten entries and exits; prune negative-expectancy slices; lift PF above 1.10",
    "holdout_repair": "tighten pre-entry filters; improve holdout survival to >= 0.55",
    "split_repair": "stabilize cohort across splits; reduce single-window dependence",
    "expectancy_repair": "remove negative-expectancy slices; require positive expectancy",
    "drawdown_repair": "add drawdown-aware no-trade guards; cap max drawdown",
    "no_trade_filter_injection": "inject pre-entry no-trade filters that match the V3 loss drivers",
    "symbol_pruning": "prune symbols with sample-supported negative PF",
    "sector_pruning": "prune sectors with sample-supported negative PF",
    "dte_retune": "retune DTE bucket selection for repair axis",
    "moneyness_retune": "retune moneyness selection for repair axis",
    "exit_policy_retune": "retune exit policy for repair axis",
    "risk_filter_retune": "tighten risk filter for repair axis",
    "relative_strength_threshold_retune": "retune RS threshold for repair axis",
    "volatility_threshold_retune": "retune volatility threshold for repair axis",
    "volume_threshold_retune": "retune volume threshold for repair axis",
    "stop_target_retune": "retune stop/target profile for repair axis",
    "family_template_split": "split continuation/volume into separate evaluated subfamilies",
}

MUTATION_EVALUATION_AXIS_V4 = {
    "profit_factor_repair": "profit_factor",
    "holdout_repair": "holdout_survival",
    "split_repair": "split_pass_rate",
    "expectancy_repair": "expectancy",
    "drawdown_repair": "max_drawdown",
    "no_trade_filter_injection": "no_trade_filter_benefit",
    "symbol_pruning": "symbol_coverage",
    "sector_pruning": "sector_coverage",
    "dte_retune": "dte_bucket",
    "moneyness_retune": "moneyness_bucket",
    "exit_policy_retune": "exit_policy",
    "risk_filter_retune": "risk_filter",
    "relative_strength_threshold_retune": "relative_strength",
    "volatility_threshold_retune": "volatility",
    "volume_threshold_retune": "volume",
    "stop_target_retune": "stop_target",
    "family_template_split": "subfamily_separation",
}

SOURCE_REJECTION_BY_MUTATION_V4 = {
    "profit_factor_repair": "profit_factor_below_threshold",
    "holdout_repair": "holdout_survival_failed",
    "split_repair": "split_pass_rate_below_threshold",
    "expectancy_repair": "expectancy_not_positive",
    "drawdown_repair": "drawdown_above_threshold",
    "no_trade_filter_injection": "net_pnl_not_positive",
    "symbol_pruning": "negative_pf_symbol",
    "sector_pruning": "negative_pf_sector",
}

CANDIDATE_PLAN_BASE = {
    "profit_factor_repair": 700,
    "holdout_repair": 600,
    "split_repair": 600,
    "expectancy_repair": 550,
    "drawdown_repair": 500,
    "no_trade_filter_injection": 800,
    "symbol_pruning": 400,
    "sector_pruning": 400,
    "dte_retune": 450,
    "moneyness_retune": 450,
    "exit_policy_retune": 450,
    "risk_filter_retune": 450,
    "relative_strength_threshold_retune": 400,
    "volatility_threshold_retune": 400,
    "volume_threshold_retune": 400,
    "stop_target_retune": 400,
    "family_template_split": 600,
}
