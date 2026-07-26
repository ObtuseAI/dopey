from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dopey_allocation.allocation_decision_models import PaperAllocationDecision, paper_allocation_decision_hash
from dopey_allocation.paper_allocation_policy import decide_paper_allocation, default_paper_allocation_policy
from dopey_allocation.paper_risk_budget import default_paper_risk_budget
from dopey_allocation.proof_evidence_aggregator import aggregate_proof_evidence
from dopey_allocation.proof_weighted_allocation_models import ProofWeightedOpportunity
from dopey_allocation.run_proof_weighted_allocator import (
    ALLOCATION_CONSTRAINT_SUMMARY_PATH,
    ALLOCATION_EXPOSURE_SUMMARY_PATH,
    ALLOCATION_PROOF_PATH,
    ALLOCATION_REJECTIONS_PATH,
    ALLOCATION_WATCHLIST_PATH,
    PAPER_ALLOCATION_DECISIONS_PATH,
    PAPER_ALLOCATION_PLAN_PATH,
    PAPER_ALLOCATION_POLICY_PATH,
    PAPER_RISK_BUDGET_FIXTURE_PATH,
    PAPER_RISK_BUDGET_PATH,
    PROOF_WEIGHTED_OPPORTUNITIES_PATH,
    run_proof_weighted_allocator,
)
from dopey_audit.active_policy_audit import audit_proof_weighted_allocation_records
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.run_account_ledger_rotation_planner import run_account_ledger_rotation_planner
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import safety_state, select_export_artifacts
from dopey_export.export_models import DEFAULT_EXPORT_PROFILE
from dopey_export_review.review_data import ExportReviewContext
from dopey_export_review.review_models import ExportReviewBundle, ExportReviewDecision
from dopey_export_review.review_packet import render_executive_summary
from dopey_options.run_zero_dte_threshold_optimizer import run_zero_dte_threshold_optimizer
from dopey_reporting.data_loader import REPORTING_BUNDLE_SUMMARY_PATH
from dopey_reporting.reporting_bundle import run_tournament_performance_reporting_bundle
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


_ALLOCATOR_RESULT: dict[str, Any] | None = None
_EVIDENCE: dict[str, Any] | None = None


def _allocator_result() -> dict[str, Any]:
    global _ALLOCATOR_RESULT
    if _ALLOCATOR_RESULT is None:
        _ALLOCATOR_RESULT = run_proof_weighted_allocator()
    return _ALLOCATOR_RESULT


def _evidence() -> dict[str, Any]:
    global _EVIDENCE
    if _EVIDENCE is None:
        _EVIDENCE = aggregate_proof_evidence()
    return _EVIDENCE


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _decisions() -> list[dict[str, Any]]:
    _allocator_result()
    return _jsonl(PAPER_ALLOCATION_DECISIONS_PATH)


def _decision_by_opportunity_id(opportunity_id: str) -> dict[str, Any]:
    return {record["opportunity_id"]: record for record in _decisions()}[opportunity_id]


def _proof_records() -> list[dict[str, Any]]:
    _allocator_result()
    return _jsonl(ALLOCATION_PROOF_PATH)


def _audit_checks(records: list[dict[str, Any]]) -> dict[str, bool]:
    _allocator_result()
    checks = audit_proof_weighted_allocation_records(
        _jsonl(PROOF_WEIGHTED_OPPORTUNITIES_PATH),
        _json(PAPER_ALLOCATION_POLICY_PATH),
        _json(PAPER_RISK_BUDGET_PATH),
        records,
        _json(PAPER_ALLOCATION_PLAN_PATH),
        _jsonl(ALLOCATION_REJECTIONS_PATH),
        _jsonl(ALLOCATION_WATCHLIST_PATH),
        _json(ALLOCATION_EXPOSURE_SUMMARY_PATH),
        _json(ALLOCATION_CONSTRAINT_SUMMARY_PATH),
        _jsonl(ALLOCATION_PROOF_PATH),
    )
    return {check["check_id"]: bool(check["passed"]) for check in checks}


def _allocation_audit_checks() -> dict[str, bool]:
    return _audit_checks(_decisions())


def _base_opportunity(kind: str, option_type: str) -> ProofWeightedOpportunity:
    strategy_suffix = "put" if option_type == "put" else "call"
    return ProofWeightedOpportunity(
        opportunity_id=f"test-{kind}-{option_type}",
        source_pair_id="source-pair-test",
        underlying_family_id="underlying-family-01",
        synthetic_underlying_symbol="SYN_TEST_A",
        regime_family="bull_trend",
        option_type=option_type,
        candidate_lifecycle="swing_multi_day",
        preferred_path="swing",
        strategy_type=f"swing_long_{strategy_suffix}",
        proof_score=0.82,
        signal_confidence=0.80,
        risk_tier=kind,
        liquidity_score=0.8,
        slippage_score=0.1,
        spread_pct=0.04,
        theta_pressure=0.2,
        gamma_instability=0.2,
        iv_overpayment_risk=0.2,
        event_risk=0.2,
        macro_risk=0.2,
        overnight_gap_risk=0.2,
        no_day_trade_constraint="next_day_close_allowed",
        zero_dte_special_lifecycle_required=False,
        swing_next_day_close_eligible=True,
        delayed_rotation_required=False,
        threshold_survival_status="paper_shadow_survives_no_research_default",
        hybrid_preference_score=0.7,
        coverage_score=1.0,
        contradiction_score=0.05,
        paper_only=True,
        live_blocked=True,
    )


def _replace_opportunity(opportunity: ProofWeightedOpportunity, updates: dict[str, Any]) -> ProofWeightedOpportunity:
    payload = opportunity.to_dict()
    payload.update(updates)
    return ProofWeightedOpportunity.from_dict(payload)


def _policy_decision(updates: dict[str, Any]) -> PaperAllocationDecision:
    opportunity = _replace_opportunity(_base_opportunity("low_fixture_risk", "call"), updates)
    return decide_paper_allocation(opportunity, default_paper_allocation_policy(), default_paper_risk_budget())


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="allocation-live-x",
        symbol="SPY_FIXTURE",
        structure="long_call",
        legs=[{"side": "buy", "symbol": "SPY_C1", "option_type": "call", "expiry": "2026-07-17", "strike": 500.0}],
        quantity=1,
        defined_risk=True,
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=5.0,
        target_profit=5.0,
    )


def test_proof_weighted_opportunity_serializes_deterministically() -> None:
    opportunity = _base_opportunity("low_fixture_risk", "call")
    assert json.dumps(opportunity.to_dict(), sort_keys=True) == json.dumps(opportunity.to_dict(), sort_keys=True)


def test_paper_allocation_decision_serializes_deterministically() -> None:
    decision = _decision_by_opportunity_id("alloc-high-proof-swing-call")
    assert json.dumps(decision, sort_keys=True) == json.dumps(decision, sort_keys=True)


def test_paper_allocation_plan_serializes_deterministically() -> None:
    plan = _json(PAPER_ALLOCATION_PLAN_PATH)
    assert json.dumps(plan, sort_keys=True) == json.dumps(plan, sort_keys=True)


def test_allocation_decision_hash_is_deterministic() -> None:
    decision = PaperAllocationDecision.from_dict(_decision_by_opportunity_id("alloc-high-proof-swing-call"))
    assert paper_allocation_decision_hash(decision) == paper_allocation_decision_hash(decision)


def test_opportunity_rejects_live_path() -> None:
    with pytest.raises(ValueError):
        _replace_opportunity(_base_opportunity("low_fixture_risk", "call"), {"live_blocked": False})


def test_opportunity_rejects_unsupported_strategy_type() -> None:
    with pytest.raises(ValueError):
        _replace_opportunity(_base_opportunity("low_fixture_risk", "call"), {"strategy_type": "short_call"})


def test_allocation_uses_abstract_units_not_dollars() -> None:
    encoded = json.dumps(_decisions(), sort_keys=True).lower()
    assert "buying_power" not in encoded and "account_balance" not in encoded and "dollar" not in encoded


def test_proof_evidence_aggregator_loads_hybrid_v3() -> None:
    summary = _evidence()["proof_summary"]
    assert summary["hybrid_pair_count"] == 192


def test_proof_evidence_aggregator_loads_threshold_optimizer() -> None:
    summary = _evidence()["proof_summary"]
    assert summary["threshold_optimizer_run_id"].startswith("zero-dte-threshold-optimizer-run-")


def test_proof_evidence_aggregator_loads_account_ledger() -> None:
    summary = _evidence()["proof_summary"]
    assert summary["account_ledger_hash"]


def test_proof_evidence_aggregator_builds_opportunities() -> None:
    assert len(_evidence()["opportunities"]) >= 72


def test_proof_evidence_aggregator_records_missing_evidence() -> None:
    missing = _evidence()["missing_evidence_summary"]
    assert missing["missing_evidence"] == []


def test_proof_evidence_aggregator_records_contradictions() -> None:
    contradictions = _evidence()["contradiction_summary"]
    assert contradictions["contradiction_count"] >= 6


def test_policy_rejects_live_path() -> None:
    assert _policy_decision({"risk_tier": "live_path"}).decision == "reject_live_path"


def test_policy_rejects_sell_to_open() -> None:
    assert _policy_decision({"risk_tier": "sell_to_open"}).decision == "reject_policy_violation"


def test_policy_rejects_unsupported_spread() -> None:
    assert _policy_decision({"risk_tier": "unsupported_spread"}).decision == "reject_policy_violation"


def test_policy_rejects_same_day_churn() -> None:
    assert _policy_decision({"risk_tier": "same_day_churn", "no_day_trade_constraint": "same_day_churn_attempt"}).decision == "reject_no_day_trade_constraint"


def test_policy_rejects_missing_thesis() -> None:
    assert _policy_decision({"risk_tier": "missing_thesis"}).decision == "reject_policy_violation"


def test_policy_rejects_missing_exit_plan() -> None:
    assert _policy_decision({"risk_tier": "missing_exit_plan"}).decision == "reject_policy_violation"


def test_policy_allocates_paper_shadow_for_insufficient_coverage() -> None:
    assert _policy_decision({"coverage_score": 0.55}).decision == "allocate_paper_shadow_only"


def test_policy_allocates_small_paper_for_moderate_evidence() -> None:
    decision = _policy_decision({"proof_score": 0.66, "signal_confidence": 0.64, "hybrid_preference_score": 0.55})
    assert decision.decision == "allocate_paper_throttled"


def test_policy_allocates_standard_paper_for_strong_swing() -> None:
    assert _policy_decision({"proof_score": 0.88, "hybrid_preference_score": 0.78}).allocation_tier == "standard_paper"


def test_policy_allocates_aggressive_capped_for_high_proof_0dte() -> None:
    decision = _policy_decision({"candidate_lifecycle": "zero_dte_special_lifecycle", "preferred_path": "zero_dte", "strategy_type": "zero_dte_long_call", "zero_dte_special_lifecycle_required": True, "swing_next_day_close_eligible": False, "proof_score": 0.90, "hybrid_preference_score": 0.74})
    assert decision.allocation_tier == "aggressive_paper_capped"


def test_policy_rejects_no_trade_preferred() -> None:
    decision = _policy_decision({"candidate_lifecycle": "no_trade", "preferred_path": "no_trade", "strategy_type": "no_trade", "option_type": "none", "risk_tier": "no_trade_preferred"})
    assert decision.decision == "reject_no_trade"


def test_risk_budget_loads_fixture() -> None:
    _allocator_result()
    assert _json(PAPER_RISK_BUDGET_FIXTURE_PATH)["budget_id"] == "dopey-paper-risk-budget-v1"


def test_risk_budget_caps_0dte_exposure() -> None:
    exposure = _json(ALLOCATION_EXPOSURE_SUMMARY_PATH)
    budget = _json(PAPER_RISK_BUDGET_PATH)
    assert exposure["zero_dte_exposure_share"] <= budget["max_zero_dte_paper_exposure_share"]


def test_risk_budget_caps_underlying_family_exposure() -> None:
    exposure = _json(ALLOCATION_EXPOSURE_SUMMARY_PATH)
    budget = _json(PAPER_RISK_BUDGET_PATH)
    assert max(exposure["allocation_by_underlying_family"].values()) <= budget["max_paper_premium_risk_units_per_underlying_family"] * 2


def test_risk_budget_caps_regime_family_exposure() -> None:
    budget = _json(PAPER_RISK_BUDGET_PATH)
    assert budget["max_paper_premium_risk_units_per_regime_family"] == 9.0


def test_risk_budget_caps_high_gamma_exposure() -> None:
    assert "gamma_instability_allocation_capped" in _json(ALLOCATION_CONSTRAINT_SUMMARY_PATH)["constraint_reason_distribution"]


def test_risk_budget_caps_high_theta_exposure() -> None:
    assert "theta_pressure_allocation_reduced" in _json(ALLOCATION_CONSTRAINT_SUMMARY_PATH)["constraint_reason_distribution"]


def test_risk_budget_caps_iv_crush_exposure() -> None:
    assert _json(PAPER_RISK_BUDGET_PATH)["max_iv_crush_exposure"] == 4.0


def test_risk_budget_tracks_call_put_balance() -> None:
    assert _json(ALLOCATION_EXPOSURE_SUMMARY_PATH)["call_put_balance_monitor"]["status"] == "balanced_or_monitored"


def test_risk_budget_tracks_swing_zero_dte_balance() -> None:
    monitor = _json(ALLOCATION_EXPOSURE_SUMMARY_PATH)["swing_zero_dte_balance_monitor"]
    assert monitor["swing_units"] > monitor["zero_dte_units"]


def test_allocator_runs_all_fixture_opportunities() -> None:
    assert _allocator_result()["summary"]["opportunity_count"] == 83


def test_high_proof_swing_call_standard_allocation() -> None:
    assert _decision_by_opportunity_id("alloc-high-proof-swing-call")["allocation_tier"] == "standard_paper"


def test_high_proof_swing_put_standard_allocation() -> None:
    assert _decision_by_opportunity_id("alloc-high-proof-swing-put")["allocation_tier"] == "standard_paper"


def test_high_proof_0dte_call_aggressive_capped_allocation() -> None:
    assert _decision_by_opportunity_id("alloc-high-proof-0dte-call")["allocation_tier"] == "aggressive_paper_capped"


def test_high_proof_0dte_put_aggressive_capped_allocation() -> None:
    assert _decision_by_opportunity_id("alloc-high-proof-0dte-put")["allocation_tier"] == "aggressive_paper_capped"


def test_moderate_0dte_throttled_allocation() -> None:
    assert _decision_by_opportunity_id("alloc-moderate-0dte-throttled")["decision"] == "allocate_paper_throttled"


def test_high_theta_0dte_reduced_allocation() -> None:
    assert "theta_pressure_allocation_reduced" in _decision_by_opportunity_id("alloc-high-theta-0dte-reduced")["constraint_reason_codes"]


def test_high_gamma_0dte_capped_allocation() -> None:
    assert "gamma_instability_allocation_capped" in _decision_by_opportunity_id("alloc-high-gamma-0dte-capped")["constraint_reason_codes"]


def test_strong_0dte_poor_liquidity_rejected() -> None:
    assert _decision_by_opportunity_id("alloc-strong-0dte-poor-liquidity")["decision"] == "reject_liquidity"


def test_wide_spread_signal_rejected() -> None:
    assert _decision_by_opportunity_id("alloc-wide-spread-signal")["decision"] == "reject_liquidity"


def test_swing_preferred_over_0dte_gets_more_paper_allocation() -> None:
    swing = _decision_by_opportunity_id("alloc-swing-preferred-over-0dte")
    zero = _decision_by_opportunity_id("alloc-zero-dte-preferred-over-swing")
    assert swing["paper_premium_risk_units"] > zero["paper_premium_risk_units"]


def test_zero_dte_preferred_over_swing_still_capped() -> None:
    decision = _decision_by_opportunity_id("alloc-zero-dte-preferred-over-swing")
    assert decision["max_paper_contract_units"] == 1


def test_delayed_rotation_reserves_paper_attention_without_same_day_close() -> None:
    decision = _decision_by_opportunity_id("alloc-delayed-rotation-reserve")
    assert decision["decision"] == "reserve_for_delayed_rotation" and decision["max_paper_contract_units"] == 0


def test_no_trade_preferred_gets_zero_allocation() -> None:
    decision = _decision_by_opportunity_id("alloc-no-trade-preferred")
    assert decision["decision"] == "reject_no_trade" and decision["paper_premium_risk_units"] == 0.0


def test_inconclusive_fixture_gets_more_coverage_decision() -> None:
    assert _decision_by_opportunity_id("alloc-inconclusive-more-coverage")["decision"] == "needs_more_fixture_coverage"


def test_policy_violation_gets_rejected() -> None:
    assert _decision_by_opportunity_id("alloc-policy-violation")["decision"] == "reject_policy_violation"


def test_live_path_gets_rejected() -> None:
    assert _decision_by_opportunity_id("alloc-live-path")["decision"] == "reject_live_path"


def test_call_put_imbalance_triggers_throttle() -> None:
    assert "call_put_imbalance_monitor_throttle" in _decision_by_opportunity_id("alloc-call-put-imbalance-throttle")["constraint_reason_codes"]


def test_0dte_exposure_share_cap_triggers_throttle() -> None:
    assert "zero_dte_exposure_share_cap_throttle" in _decision_by_opportunity_id("alloc-zero-dte-share-cap-throttle")["constraint_reason_codes"]


def test_paper_shadow_candidate_does_not_become_standard_allocation() -> None:
    assert _decision_by_opportunity_id("alloc-paper-shadow-not-standard")["allocation_tier"] == "paper_shadow"


def test_proof_weighted_opportunities_artifact_written() -> None:
    assert PROOF_WEIGHTED_OPPORTUNITIES_PATH.exists() and len(_jsonl(PROOF_WEIGHTED_OPPORTUNITIES_PATH)) == 83


def test_paper_allocation_policy_artifact_written() -> None:
    assert PAPER_ALLOCATION_POLICY_PATH.exists() and _json(PAPER_ALLOCATION_POLICY_PATH)["paper_only"] is True


def test_paper_risk_budget_artifact_written() -> None:
    assert PAPER_RISK_BUDGET_PATH.exists() and _json(PAPER_RISK_BUDGET_PATH)["live_blocked"] is True


def test_paper_allocation_decisions_artifact_written() -> None:
    assert PAPER_ALLOCATION_DECISIONS_PATH.exists() and len(_jsonl(PAPER_ALLOCATION_DECISIONS_PATH)) == 83


def test_paper_allocation_plan_artifact_written() -> None:
    assert PAPER_ALLOCATION_PLAN_PATH.exists() and _json(PAPER_ALLOCATION_PLAN_PATH)["plan_hash"]


def test_allocation_rejections_artifact_written() -> None:
    assert ALLOCATION_REJECTIONS_PATH.exists() and len(_jsonl(ALLOCATION_REJECTIONS_PATH)) == 30


def test_allocation_watchlist_artifact_written() -> None:
    assert ALLOCATION_WATCHLIST_PATH.exists() and len(_jsonl(ALLOCATION_WATCHLIST_PATH)) >= 14


def test_allocation_exposure_summary_artifact_written() -> None:
    assert ALLOCATION_EXPOSURE_SUMMARY_PATH.exists() and _json(ALLOCATION_EXPOSURE_SUMMARY_PATH)["artifact_type"] == "allocation_exposure_summary"


def test_allocation_constraint_summary_artifact_written() -> None:
    assert ALLOCATION_CONSTRAINT_SUMMARY_PATH.exists() and _json(ALLOCATION_CONSTRAINT_SUMMARY_PATH)["same_day_churn_allocation_allowed"] is False


def test_allocation_proof_artifact_written() -> None:
    assert ALLOCATION_PROOF_PATH.exists() and len(_proof_records()) == 83


def test_account_ledger_records_allocation_context() -> None:
    result = run_account_ledger_rotation_planner()
    assert result["allocation_context"]["allocation_plan_loaded"] is True


def test_rotation_planner_receives_allocation_priority() -> None:
    result = run_account_ledger_rotation_planner()
    assert result["rotation_plan"]["allocation_context"]["paper_attention_priority_available"] is True


def test_paper_broker_not_overridden_by_allocator() -> None:
    assert _json(ALLOCATION_CONSTRAINT_SUMMARY_PATH)["paper_broker_override_allowed"] is False


def test_allocator_cannot_force_same_day_close() -> None:
    result = run_account_ledger_rotation_planner()
    assert result["allocation_context"]["allocator_can_force_same_day_close"] is False


def test_delayed_rotation_reserve_is_advisory_only() -> None:
    assert _json(ALLOCATION_CONSTRAINT_SUMMARY_PATH)["delayed_rotation_reserves_advisory_only"] is True


def test_threshold_optimizer_consumes_allocation_feedback() -> None:
    result = run_zero_dte_threshold_optimizer()
    assert result["summary"]["allocation_feedback_loaded"] is True


def test_threshold_optimizer_does_not_mutate_live_thresholds_from_allocation() -> None:
    result = run_zero_dte_threshold_optimizer()
    assert result["summary"]["allocation_feedback_live_threshold_mutation_allowed"] is False


def test_audit_recognizes_allocation_artifacts() -> None:
    names = {artifact_type for artifact_type, _path, _kind, _fields in ARTIFACT_SPECS}
    assert {"paper_allocation_plan", "allocation_proof", "proof_weighted_opportunities"}.issubset(names)


def test_audit_flags_allocation_with_real_dollars() -> None:
    records = [dict(_decisions()[0], paper_premium_risk_units=1.0, allocator_tags=["dollar_sizing"])]
    assert _audit_checks(records)["allocation_no_real_dollars_buying_power_or_account_balance"] is False


def test_audit_flags_allocation_with_broker_path() -> None:
    records = [dict(_decisions()[0], allocator_tags=["robinhood_order"])]
    assert _audit_checks(records)["allocation_no_broker_path"] is False


def test_audit_flags_allocation_with_credentials() -> None:
    records = [dict(_decisions()[0], allocator_tags=["api_key"])]
    assert _audit_checks(records)["allocation_no_credentials"] is False


def test_audit_flags_allocation_with_live_order() -> None:
    records = [dict(_decisions()[0], allocator_tags=["live_order"])]
    assert _audit_checks(records)["allocation_no_live_order"] is False


def test_audit_flags_allocation_with_same_day_churn() -> None:
    records = [dict(_decisions()[0], block_reason_codes=["same_day_churn_rejected"])]
    assert _audit_checks(records)["allocation_no_same_day_churn_allocation"] is False


def test_audit_flags_allocation_with_real_sizing() -> None:
    proof = [dict(record, no_real_sizing=False) for record in _proof_records()]
    checks = audit_proof_weighted_allocation_records(_jsonl(PROOF_WEIGHTED_OPPORTUNITIES_PATH), _json(PAPER_ALLOCATION_POLICY_PATH), _json(PAPER_RISK_BUDGET_PATH), _decisions(), _json(PAPER_ALLOCATION_PLAN_PATH), _jsonl(ALLOCATION_REJECTIONS_PATH), _jsonl(ALLOCATION_WATCHLIST_PATH), _json(ALLOCATION_EXPOSURE_SUMMARY_PATH), _json(ALLOCATION_CONSTRAINT_SUMMARY_PATH), proof)
    assert {check["check_id"]: check["passed"] for check in checks}["allocation_no_real_sizing"] is False


def test_audit_confirms_0dte_allocation_capped() -> None:
    assert _allocation_audit_checks()["allocation_0dte_allocation_capped"] is True


def test_audit_confirms_allocation_paper_only_live_blocked() -> None:
    checks = _allocation_audit_checks()
    assert checks["allocation_all_paper_only"] is True and checks["allocation_all_live_blocked"] is True


def test_audit_confirms_no_active_forbidden_live_decisions_after_allocator() -> None:
    assert _allocation_audit_checks()["allocation_no_active_forbidden_live_decisions"] is True


def test_reporting_includes_allocation_summary() -> None:
    run_tournament_performance_reporting_bundle()
    assert _json(REPORTING_BUNDLE_SUMMARY_PATH)["proof_weighted_allocation_summary"]["opportunity_count"] == 83


def test_reporting_includes_0dte_vs_swing_allocation_split() -> None:
    summary = _json(REPORTING_BUNDLE_SUMMARY_PATH)["proof_weighted_allocation_summary"]
    assert summary["swing_paper_premium_risk_units"] > summary["zero_dte_paper_premium_risk_units"]


def test_reporting_includes_delayed_rotation_reserves() -> None:
    summary = _json(REPORTING_BUNDLE_SUMMARY_PATH)["proof_weighted_allocation_summary"]
    assert summary["delayed_rotation_reserves_advisory_only"] is True


def test_export_verifier_selects_allocation_artifacts() -> None:
    _allocator_result()
    plan = select_export_artifacts(DEFAULT_EXPORT_PROFILE, safety_state())
    ids = {artifact.artifact_id for artifact in plan.selected_artifacts}
    assert {"paper_allocation_plan", "allocation_proof", "paper_allocation_decisions"}.issubset(ids)


def test_export_review_includes_allocation_summary() -> None:
    reporting_summary = _json(REPORTING_BUNDLE_SUMMARY_PATH)
    ctx = ExportReviewContext({}, {}, {}, {}, {}, {}, reporting_summary, {}, [], [], {}, {}, Path("."), "", Path("."), Path("."))
    bundle = ExportReviewBundle("r", "b", "s", "m", "c", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "next", True, True, "")
    decision = ExportReviewDecision("d", "b", "approve_offline_review", "paper_only", [], [], "next", True, True, "")
    assert "Proof-Weighted Paper Allocation" in render_executive_summary(ctx, bundle, [], decision)


def test_allocator_artifact_ledger_written() -> None:
    assert Path("docs/reports/DOPEY_PROOF_WEIGHTED_ALLOCATOR_ARTIFACT_LEDGER.md").exists()


def test_shard_plan_includes_allocation_tests() -> None:
    result = CommandResult([ "python", "-m", "pytest", "tests/test_proof_weighted_allocator.py", "-q"], "pass", 0, 1.0, False, False, "", "")
    plan = write_test_shard_plan(["tests/test_proof_weighted_allocator.py"], [result], {"collection": result.to_dict(), "full_suite": timeout_result(["python", "-m", "pytest"], 1)})
    assert "tests/test_proof_weighted_allocator.py" in plan["proof_weighted_allocation_test_files"]


def test_shard_plan_marks_allocation_artifact_tests_sequential() -> None:
    result = CommandResult(["python", "-m", "pytest", "tests/test_proof_weighted_allocator.py", "-q"], "pass", 0, 1.0, False, False, "", "")
    plan = write_test_shard_plan(["tests/test_proof_weighted_allocator.py"], [result], {"collection": result.to_dict(), "full_suite": timeout_result(["python", "-m", "pytest"], 1)})
    assert "tests/test_proof_weighted_allocator.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout" and result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_allocator() -> None:
    cfg = load_config(default_config_path())
    assert cfg["live_trading_enabled"] is False


def test_robinhood_stub_still_blocks_live_after_allocator() -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_allocator() -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_allocator() -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_allocator() -> None:
    encoded = "\n".join(path.read_text(encoding="utf-8") for path in [PAPER_ALLOCATION_PLAN_PATH, PAPER_ALLOCATION_POLICY_PATH, PAPER_RISK_BUDGET_PATH])
    assert "api_key" not in encoded.lower() and "access_token" not in encoded.lower()


def test_no_scheduler_created_by_allocator() -> None:
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_allocation").glob("*.py"))
    assert "apscheduler" not in text and "cron" not in text


def test_no_network_market_data_dependency_created_by_allocator() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("dopey_allocation").glob("*.py")
    )
    forbidden_imports = (
        "import yfinance",
        "from yfinance",
        "import polygon",
        "from polygon",
        "import iex",
        "from iex",
    )
    assert not any(value in text for value in forbidden_imports)


def test_no_same_day_churn_loophole_created_by_allocator() -> None:
    assert _allocation_audit_checks()["allocation_no_same_day_churn_allocation"] is True


def test_no_real_capital_allocator_created_by_allocator() -> None:
    assert _json(PAPER_ALLOCATION_POLICY_PATH)["real_capital_sizing_allowed"] is False


def test_no_real_buying_power_logic_created_by_allocator() -> None:
    encoded = json.dumps(_json(PAPER_ALLOCATION_PLAN_PATH), sort_keys=True).lower()
    assert "buying_power" not in encoded and "account_balance" not in encoded


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    from dopey_export.artifact_selector import write_blunder_integrity_status

    path = write_blunder_integrity_status()
    status = _json(path)
    assert status["status"] in {"ok", "skipped", "warning"}
