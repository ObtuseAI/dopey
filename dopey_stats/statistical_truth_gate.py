"""Claim-blocking decision gate for DOPEY statistical truth outputs."""
from __future__ import annotations

from typing import Any

from .statistical_metric_calculator import REAL_EVIDENCE_MIN_TRADES
from .statistical_truth_models import StatisticalTruthDecision


def evaluate_statistical_truth_decision(
    backtest_summary: dict[str, Any],
    sample_profile: dict[str, Any],
    metric_set: dict[str, Any],
    bootstrap_ci: dict[str, Any],
    multiple_testing: dict[str, Any],
    deflated_sharpe: dict[str, Any],
    backtest_quality_flags: list[dict[str, Any]],
    safety_leaks: list[str],
) -> dict[str, Any]:
    blocked = _blocked_reason_codes(
        backtest_summary,
        sample_profile,
        bootstrap_ci,
        multiple_testing,
        deflated_sharpe,
        backtest_quality_flags,
        safety_leaks,
    )
    terminal_block = bool(safety_leaks) or "full_pytest_timeout_recorded_as_pass" in blocked
    if terminal_block:
        truth_status = "terminal_block"
        truth_decision = "terminal_block"
    elif not bool(backtest_summary.get("real_history_used", False)):
        truth_status = "fixture_model_statistics_only"
        truth_decision = "hold_fixture_validation_only"
    elif int(sample_profile.get("real_sample_size", 0)) < REAL_EVIDENCE_MIN_TRADES:
        truth_status = "insufficient_real_sample"
        truth_decision = "insufficient_real_evidence"
    else:
        truth_status = "manual_review_required"
        truth_decision = "manual_review_required"
    decision = StatisticalTruthDecision(
        artifact_type="statistical_truth_decision",
        statistical_truth_version="",
        truth_status=truth_status,
        truth_decision=truth_decision,
        sample_count=int(metric_set.get("sample_count", 0)),
        real_sample_size=int(sample_profile.get("real_sample_size", 0)),
        quote_priced_trade_count=int(backtest_summary.get("quote_priced_trade_count", 0)),
        promotion_allowed=False,
        significance_claim_allowed=False,
        real_alpha_claim_allowed=False,
        profitability_claim_allowed=False,
        live_readiness_claim_allowed=False,
        blocked_reason_codes=blocked,
        manual_review_required=truth_decision == "manual_review_required",
        terminal_block=terminal_block,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        not_real_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        decision_hash="",
    )
    return decision.to_dict()


def _blocked_reason_codes(
    backtest_summary: dict[str, Any],
    sample_profile: dict[str, Any],
    bootstrap_ci: dict[str, Any],
    multiple_testing: dict[str, Any],
    deflated_sharpe: dict[str, Any],
    backtest_quality_flags: list[dict[str, Any]],
    safety_leaks: list[str],
) -> list[str]:
    codes: set[str] = set()
    if not bool(backtest_summary.get("real_history_used", False)):
        codes.add("missing_real_history_blocks_real_evidence")
    if int(backtest_summary.get("quote_priced_trade_count", 0)) == 0:
        codes.add("missing_real_options_chain_blocks_real_options_edge")
    if bool(backtest_summary.get("not_real_backtest_evidence", True)):
        codes.add("not_real_backtest_evidence_blocks_promotion")
    if bool(backtest_summary.get("not_profitability_claim", True)):
        codes.add("not_profitability_claim_blocks_profitability_claim")
    if int(sample_profile.get("real_sample_size", 0)) < REAL_EVIDENCE_MIN_TRADES:
        codes.add("insufficient_real_sample_blocks_significance")
    if bool(bootstrap_ci.get("insufficient_real_sample", True)):
        codes.add("bootstrap_insufficient_real_sample")
    if bool(multiple_testing.get("p_values_blocked", True)):
        codes.add("multiple_testing_p_values_blocked")
    if bool(deflated_sharpe.get("diagnostic_only", True)):
        codes.add("deflated_sharpe_diagnostic_only")
    for flag in backtest_quality_flags:
        reason = str(flag.get("reason_code", ""))
        if reason in {"missing_real_history", "missing_real_option_chain", "not_real_backtest_evidence"}:
            codes.add(reason)
    for leak in safety_leaks:
        codes.add(f"safety_leak_{leak}")
    return sorted(codes)
