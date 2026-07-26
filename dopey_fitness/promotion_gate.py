"""Promotion gate for truth-gated diagnostic fitness."""
from __future__ import annotations

from typing import Any

from .fitness_models import FitnessPromotionGate


FORBIDDEN_ACTIVE_FIELDS: frozenset[str] = frozenset({
    "broker_connection",
    "credentials_used",
    "scheduler_enabled",
    "real_sizing_used",
    "order_path_enabled",
    "live_order_path_enabled",
    "live_trading_enabled",
})


def evaluate_fitness_promotion_gate(
    truth_summary: dict[str, Any],
    truth_decision: dict[str, Any],
    backtest_summary: dict[str, Any],
    validation_summary: dict[str, Any],
    active_boundary_scan: dict[str, Any],
) -> dict[str, Any]:
    blocked_codes: list[str] = []
    statistical_promotion_allowed = bool(truth_decision.get("promotion_allowed", truth_summary.get("promotion_allowed", False)))
    real_sample_size = int(truth_decision.get("real_sample_size", truth_summary.get("real_sample_size", 0)))
    quote_priced_trade_count = int(truth_decision.get("quote_priced_trade_count", backtest_summary.get("quote_priced_trade_count", 0)))
    real_history_used = bool(backtest_summary.get("real_history_used", False))
    real_option_chain_used = bool(any(record for record in [truth_decision.get("real_option_chain_used"), backtest_summary.get("real_option_chain_used")] if record))
    if statistical_promotion_allowed is False:
        blocked_codes.append("statistical_truth_promotion_false")
    if real_sample_size < 30:
        blocked_codes.append("insufficient_real_sample")
    if real_history_used is False:
        blocked_codes.append("missing_real_history")
    if quote_priced_trade_count == 0:
        blocked_codes.append("no_quote_priced_data")
    if bool(truth_summary.get("not_real_statistical_evidence", True)):
        blocked_codes.append("not_real_statistical_evidence")
    if bool(backtest_summary.get("not_real_backtest_evidence", True)):
        blocked_codes.append("not_real_backtest_evidence")
    if bool(truth_summary.get("not_profitability_claim", True)) or bool(backtest_summary.get("not_profitability_claim", True)):
        blocked_codes.append("not_profitability_claim")
    if bool(truth_summary.get("not_live_ready", True)) or bool(backtest_summary.get("not_live_ready", True)):
        blocked_codes.append("not_live_ready")
    if _full_pytest_timeout_misclassified_as_pass(validation_summary):
        blocked_codes.append("full_pytest_timeout_misclassified_as_pass")
    blocked_codes.extend(_active_boundary_blocks(active_boundary_scan))
    promotion_allowed = statistical_promotion_allowed and not blocked_codes
    status = "real_data_fitness_ready" if promotion_allowed else "truth_gate_blocked"
    block_reason = _promotion_block_reason(truth_summary, blocked_codes)
    gate = FitnessPromotionGate(
        artifact_type="fitness_promotion_gate",
        fitness_version="",
        promotion_gate_status=status,
        promotion_allowed=promotion_allowed,
        strategy_promoted=False,
        promotion_block_reason=block_reason,
        real_sample_size=real_sample_size,
        quote_priced_trade_count=quote_priced_trade_count,
        real_history_used=real_history_used,
        real_option_chain_used=real_option_chain_used,
        blocked_reason_codes=blocked_codes,
        terminal_block=bool("full_pytest_timeout_misclassified_as_pass" in blocked_codes or any(code.startswith("active_boundary_") for code in blocked_codes)),
        manual_review_required=False,
        not_real_fitness_evidence=True,
        not_real_statistical_evidence=bool(truth_summary.get("not_real_statistical_evidence", True)),
        not_real_backtest_evidence=bool(backtest_summary.get("not_real_backtest_evidence", True)),
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        gate_hash="",
    )
    return gate.to_dict()


def _promotion_block_reason(truth_summary: dict[str, Any], blocked_codes: list[str]) -> str:
    if str(truth_summary.get("truth_status", "")) == "fixture_model_statistics_only":
        return "fixture_model_statistics_only"
    if blocked_codes:
        return blocked_codes[0]
    return ""


def _full_pytest_timeout_misclassified_as_pass(validation_summary: dict[str, Any]) -> bool:
    if bool(validation_summary.get("timeout_recorded_as_pass", False)):
        return True
    full_suite = validation_summary.get("full_suite", {})
    if isinstance(full_suite, dict) and full_suite.get("status") == "pass" and bool(full_suite.get("timed_out", False)):
        return True
    return False


def _active_boundary_blocks(active_boundary_scan: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for field_name in sorted(FORBIDDEN_ACTIVE_FIELDS):
        if bool(active_boundary_scan.get(field_name, False)):
            output.append(f"active_boundary_{field_name}")
    return output

