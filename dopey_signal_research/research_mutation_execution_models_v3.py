"""Mutation execution models V3."""
from __future__ import annotations

MUTATION_EXECUTION_TYPES = (
    "broaden_symbols",
    "broaden_sectors",
    "repair_holdout_weakness",
    "repair_split_weakness",
    "repair_profit_factor",
    "repair_expectancy",
    "reduce_drawdown",
    "reduce_outlier_dependence",
    "add_no_trade_filter",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "risk_filter_retune",
    "relative_strength_threshold_retune",
    "volatility_threshold_retune",
    "volume_threshold_retune",
    "stop_target_retune",
)

V2_TO_V3_MUTATION_MAP = {
    "symbol_expansion": "broaden_symbols",
    "sector_expansion": "broaden_sectors",
    "regime_expansion": "repair_holdout_weakness",
    "holdout_repair": "repair_holdout_weakness",
    "split_pass_repair": "repair_split_weakness",
    "profit_factor_repair": "repair_profit_factor",
    "expectancy_repair": "repair_expectancy",
    "dte_retune": "dte_retune",
    "moneyness_retune": "moneyness_retune",
    "exit_policy_retune": "exit_policy_retune",
    "risk_filter_tightening": "risk_filter_retune",
    "filter_loosening": "risk_filter_retune",
    "relative_strength_threshold_retune": "relative_strength_threshold_retune",
    "volatility_threshold_retune": "volatility_threshold_retune",
    "volume_threshold_retune": "volume_threshold_retune",
    "stop_target_retune": "stop_target_retune",
    "no_trade_filter_injection": "add_no_trade_filter",
}

MUTATION_INTENDED_FIX = {
    "broaden_symbols": "expand symbol coverage without forcing low-quality trades",
    "broaden_sectors": "expand sector coverage with selective filters",
    "repair_holdout_weakness": "improve holdout survival via selective entry filters",
    "repair_split_weakness": "improve split pass rate via cohort stability",
    "repair_profit_factor": "tighten entries and exits to lift profit factor",
    "repair_expectancy": "remove negative-expectancy slices",
    "reduce_drawdown": "add drawdown-aware no-trade filters",
    "reduce_outlier_dependence": "penalize one-symbol outlier dependence",
    "add_no_trade_filter": "inject regime/overextension no-trade guards",
    "dte_retune": "retune DTE bucket for repair axis",
    "moneyness_retune": "retune moneyness for repair axis",
    "exit_policy_retune": "retune exit policy for repair axis",
    "risk_filter_retune": "tighten risk filters",
    "relative_strength_threshold_retune": "retune relative strength confirmation",
    "volatility_threshold_retune": "retune volatility regime filters",
    "volume_threshold_retune": "retune volume dry-up / confirmation thresholds",
    "stop_target_retune": "retune stop/target profile",
}

MUTATION_EVALUATION_AXIS = {
    "repair_profit_factor": "profit_factor",
    "repair_holdout_weakness": "holdout_survival",
    "repair_split_weakness": "split_pass_rate",
    "repair_expectancy": "expectancy",
    "reduce_drawdown": "max_drawdown",
    "reduce_outlier_dependence": "outlier_dependence",
    "add_no_trade_filter": "no_trade_filter_benefit",
    "broaden_symbols": "symbol_coverage",
    "broaden_sectors": "sector_coverage",
}

SOURCE_REJECTION_BY_MUTATION = {
    "repair_profit_factor": "profit_factor_below_threshold",
    "repair_holdout_weakness": "holdout_survival_failed",
    "repair_split_weakness": "split_pass_rate_below_threshold",
    "repair_expectancy": "expectancy_not_positive",
    "add_no_trade_filter": "net_pnl_not_positive",
}
