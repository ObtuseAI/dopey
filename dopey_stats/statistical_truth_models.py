"""Typed records for DOPEY's statistical truth layer."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


STATISTICAL_TRUTH_VERSION = "dopey-statistical-truth-layer-v1"
ALLOWED_TRUTH_STATUSES: frozenset[str] = frozenset({
    "fixture_model_statistics_only",
    "insufficient_real_sample",
    "real_sample_statistics_ready",
    "manual_review_required",
    "terminal_block",
})
ALLOWED_TRUTH_DECISIONS: frozenset[str] = frozenset({
    "hold_fixture_validation_only",
    "insufficient_real_evidence",
    "manual_review_required",
    "eligible_for_fitness_function_replacement_after_real_data",
    "terminal_block",
})
TRUTH_HASH_FIELDS: frozenset[str] = frozenset({
    "record_hash",
    "input_hash",
    "profile_hash",
    "metric_hash",
    "ci_hash",
    "comparison_hash",
    "adjustment_hash",
    "result_hash",
    "decision_hash",
    "flag_hash",
    "proof_hash",
    "run_hash",
    "reproducibility_hash",
})


@dataclass(frozen=True)
class StatisticalTruthInput:
    artifact_type: str
    statistical_truth_version: str
    backtest_summary_path: str
    backtest_trade_records_path: str
    backtest_quality_flags_path: str
    backtest_status: str
    history_dataset_status: str
    real_history_used: bool
    real_option_chain_used: bool
    quote_priced_trade_count: int
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        record["real_history_used"] = bool(record["real_history_used"])
        record["real_option_chain_used"] = bool(record["real_option_chain_used"])
        record["quote_priced_trade_count"] = int(record["quote_priced_trade_count"])
        _force_safety_flags(record)
        record["input_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class BacktestSampleProfile:
    artifact_type: str
    statistical_truth_version: str
    sample_count: int
    real_sample_size: int
    fixture_model_sample_size: int
    distinct_symbol_count: int
    distinct_signal_family_count: int
    distinct_strategy_count: int
    date_span_days: int
    minimum_trades_for_fixture_diagnostic: int
    minimum_trades_for_real_evidence: int
    minimum_regimes_for_real_evidence: int
    minimum_distinct_symbols_for_real_evidence: int
    minimum_date_span_days_for_real_evidence: int
    fixture_diagnostic_threshold_met: bool
    real_evidence_thresholds_met: bool
    promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    profile_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        _force_safety_flags(record)
        record["promotion_allowed"] = False
        record["profile_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class BacktestMetricSet:
    artifact_type: str
    statistical_truth_version: str
    sample_count: int
    win_count: int
    loss_count: int
    flat_count: int
    win_rate: float
    average_model_unit_pnl: float
    median_model_unit_pnl: float
    total_model_unit_pnl: float
    stddev_model_unit_pnl: float
    downside_deviation_model_units: float
    sharpe_like_model_units: float
    sortino_like_model_units: float
    max_drawdown_model_units: float
    average_win_model_units: float
    average_loss_model_units: float
    payoff_ratio_model_units: float
    expectancy_model_units: float
    profit_factor_model_units: float
    longest_win_streak: int
    longest_loss_streak: int
    real_sample_size: int
    promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    metric_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        _force_safety_flags(record)
        record["promotion_allowed"] = False
        record["metric_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class BootstrapConfidenceInterval:
    artifact_type: str
    statistical_truth_version: str
    seed: int
    iterations: int
    sample_count: int
    insufficient_sample: bool
    insufficient_real_sample: bool
    mean_pnl_ci: list[float]
    win_rate_ci: list[float]
    drawdown_ci: list[float]
    median_pnl_ci: list[float]
    significance_claim_allowed: bool
    real_alpha_claim_allowed: bool
    promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    ci_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        _force_safety_flags(record)
        record["significance_claim_allowed"] = False
        record["real_alpha_claim_allowed"] = False
        record["promotion_allowed"] = False
        record["ci_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class BaselineComparison:
    artifact_type: str
    statistical_truth_version: str
    baseline_name: str
    sample_count: int
    tested_metric: str
    observed_value: float
    baseline_value: float
    delta: float
    diagnostic_only: bool
    real_evidence: bool
    superiority_claim_allowed: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    comparison_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        record["diagnostic_only"] = True
        record["real_evidence"] = False
        record["superiority_claim_allowed"] = False
        _force_safety_flags(record)
        record["comparison_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class MultipleTestingAdjustment:
    artifact_type: str
    statistical_truth_version: str
    strategy_family_count: int
    tested_signal_family_count: int
    p_values_blocked: bool
    bonferroni_adjustment_applied: bool
    benjamini_hochberg_adjustment_applied: bool
    adjusted_p_values: dict[str, float | None]
    significance_claim_allowed: bool
    real_alpha_claim_allowed: bool
    promotion_allowed: bool
    diagnostic_only: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    adjustment_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        record["p_values_blocked"] = True
        record["significance_claim_allowed"] = False
        record["real_alpha_claim_allowed"] = False
        record["promotion_allowed"] = False
        record["diagnostic_only"] = True
        _force_safety_flags(record)
        record["adjustment_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class DeflatedSharpeResult:
    artifact_type: str
    statistical_truth_version: str
    observed_sharpe_like_model_units: float
    strategy_family_count: int
    tested_signal_family_count: int
    diagnostic_only: bool
    deflated_sharpe_model_units: float
    p_value: float | None
    significance_claim_allowed: bool
    real_alpha_claim_allowed: bool
    promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = _rounded(asdict(self))
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        record["diagnostic_only"] = True
        record["p_value"] = None
        record["significance_claim_allowed"] = False
        record["real_alpha_claim_allowed"] = False
        record["promotion_allowed"] = False
        _force_safety_flags(record)
        record["result_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class StatisticalTruthDecision:
    artifact_type: str
    statistical_truth_version: str
    truth_status: str
    truth_decision: str
    sample_count: int
    real_sample_size: int
    quote_priced_trade_count: int
    promotion_allowed: bool
    significance_claim_allowed: bool
    real_alpha_claim_allowed: bool
    profitability_claim_allowed: bool
    live_readiness_claim_allowed: bool
    blocked_reason_codes: list[str]
    manual_review_required: bool
    terminal_block: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    not_real_backtest_evidence: bool
    not_profitability_claim: bool
    not_live_ready: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        record["truth_status"] = validate_truth_status(str(record["truth_status"]))
        record["truth_decision"] = validate_truth_decision(str(record["truth_decision"]))
        record["blocked_reason_codes"] = sorted(str(code) for code in record["blocked_reason_codes"])
        record["promotion_allowed"] = False
        record["significance_claim_allowed"] = False
        record["real_alpha_claim_allowed"] = False
        record["profitability_claim_allowed"] = False
        record["live_readiness_claim_allowed"] = False
        record["not_real_backtest_evidence"] = True
        record["not_profitability_claim"] = True
        record["not_live_ready"] = True
        _force_safety_flags(record)
        record["decision_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class StatisticalTruthQualityFlag:
    artifact_type: str
    flag_id: str
    severity: str
    reason_code: str
    message: str
    fixture_only: bool
    model_priced: bool
    quote_priced: bool
    real_history_used: bool
    real_option_chain_used: bool
    promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["fixture_only"] = True
        record["model_priced"] = bool(record["model_priced"])
        record["quote_priced"] = False
        record["real_history_used"] = False
        record["real_option_chain_used"] = False
        record["promotion_allowed"] = False
        _force_safety_flags(record)
        record["flag_hash"] = stable_truth_hash(record)
        return record


@dataclass(frozen=True)
class StatisticalTruthProofRecord:
    artifact_type: str
    proof_id: str
    statistical_truth_version: str
    truth_status: str
    truth_decision: str
    sample_count: int
    real_sample_size: int
    significance_claim_allowed: bool
    real_alpha_claim_allowed: bool
    profitability_claim_allowed: bool
    live_readiness_claim_allowed: bool
    promotion_allowed: bool
    no_broker: bool
    no_credentials: bool
    no_scheduler: bool
    no_real_sizing: bool
    no_orders: bool
    paper_only: bool
    live_blocked: bool
    not_real_statistical_evidence: bool
    next_recommended_target: str
    proof_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["statistical_truth_version"] = STATISTICAL_TRUTH_VERSION
        record["truth_status"] = validate_truth_status(str(record["truth_status"]))
        record["truth_decision"] = validate_truth_decision(str(record["truth_decision"]))
        record["significance_claim_allowed"] = False
        record["real_alpha_claim_allowed"] = False
        record["profitability_claim_allowed"] = False
        record["live_readiness_claim_allowed"] = False
        record["promotion_allowed"] = False
        record["no_broker"] = True
        record["no_credentials"] = True
        record["no_scheduler"] = True
        record["no_real_sizing"] = True
        record["no_orders"] = True
        _force_safety_flags(record)
        record["proof_hash"] = stable_truth_hash(record)
        return record


def stable_truth_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_strip_hash_fields(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_truth_status(status: str) -> str:
    if status not in ALLOWED_TRUTH_STATUSES:
        raise ValueError(f"unsupported truth_status: {status}")
    return status


def validate_truth_decision(decision: str) -> str:
    if decision not in ALLOWED_TRUTH_DECISIONS:
        raise ValueError(f"unsupported truth_decision: {decision}")
    return decision


def _force_safety_flags(record: dict[str, Any]) -> None:
    record["paper_only"] = True
    record["live_blocked"] = True
    record["not_real_statistical_evidence"] = True


def _rounded(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_hash_fields(item)
            for key, item in value.items()
            if key not in TRUTH_HASH_FIELDS
        }
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
