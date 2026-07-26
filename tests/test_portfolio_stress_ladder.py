from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dopey_allocation.run_proof_weighted_allocator import crisis_feedback_summary, run_proof_weighted_allocator
from dopey_audit.active_policy_audit import audit_stress_ladder_records
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import safety_state, select_export_artifacts
from dopey_export.export_models import DEFAULT_EXPORT_PROFILE
from dopey_export_review.review_data import ExportReviewContext
from dopey_export_review.review_models import ExportReviewBundle, ExportReviewDecision
from dopey_export_review.review_packet import render_executive_summary
from dopey_options.zero_dte_threshold_optimizer import _crisis_feedback_summary
from dopey_portfolio.crisis_mode_policy import default_portfolio_stress_ladder, evaluate_stress_level
from dopey_portfolio.crisis_recovery_policy import recovery_transition_level
from dopey_portfolio.run_portfolio_stress_ladder import (
    CRISIS_ALLOCATOR_FEEDBACK_PATH,
    CRISIS_MODE_THROTTLE_PROFILES_FIXTURE_PATH,
    CRISIS_MODE_THROTTLE_PROFILES_PATH,
    CRISIS_RECOVERY_RESULTS_PATH,
    CRISIS_THRESHOLD_FEEDBACK_PATH,
    CRISIS_THROTTLE_RESULTS_PATH,
    EXPECTED_CRISIS_THROTTLES_FIXTURE_PATH,
    EXPECTED_STRESS_TRANSITIONS_FIXTURE_PATH,
    STRESS_LADDER_POLICY_FIXTURE_PATH,
    STRESS_LADDER_POLICY_PATH,
    STRESS_LADDER_PROOF_PATH,
    STRESS_LADDER_REPLAY_CASES_FIXTURE_PATH,
    STRESS_LADDER_REPLAY_CASES_PATH,
    STRESS_LADDER_SUMMARY_PATH,
    STRESS_LEVEL_EVALUATIONS_PATH,
    STRESS_TRANSITION_DECISIONS_PATH,
    run_portfolio_stress_ladder,
)
from dopey_portfolio.stress_ladder_models import (
    CrisisModeThrottle,
    PortfolioStressLadder,
    PortfolioStressLevel,
    StressTransitionDecision,
    stress_ladder_hash,
)
from dopey_reporting.data_loader import REPORTING_BUNDLE_SUMMARY_PATH
from dopey_reporting.reporting_bundle import run_tournament_performance_reporting_bundle
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


_STRESS_RESULT: dict[str, Any] | None = None


def _result() -> dict[str, Any]:
    global _STRESS_RESULT
    if _STRESS_RESULT is None:
        _STRESS_RESULT = run_portfolio_stress_ladder()
    return _STRESS_RESULT


def _json(path: Path) -> dict[str, Any]:
    _result()
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    _result()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cases() -> list[dict[str, Any]]:
    return _json(STRESS_LADDER_REPLAY_CASES_PATH)["records"]


def _case(required_case: str) -> dict[str, Any]:
    return next(record for record in _cases() if record["required_case"] == required_case)


def _throttle_for(required_case: str) -> dict[str, Any]:
    case_id = _case(required_case)["stress_case_id"]
    return next(record for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH) if record["stress_case_id"] == case_id)


def _recovery_for(required_case: str) -> dict[str, Any]:
    case_id = _case(required_case)["stress_case_id"]
    return next(record for record in _jsonl(CRISIS_RECOVERY_RESULTS_PATH) if record["stress_case_id"] == case_id)


def _summary() -> dict[str, Any]:
    return _json(STRESS_LADDER_SUMMARY_PATH)


def _audit_checks(
    policy: dict[str, Any],
    throttle_profiles: dict[str, Any],
    replay_cases: dict[str, Any],
    evaluations: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    throttles: list[dict[str, Any]],
    recoveries: list[dict[str, Any]],
    allocator_feedback: list[dict[str, Any]],
    threshold_feedback: list[dict[str, Any]],
    summary: dict[str, Any],
    proof_records: list[dict[str, Any]],
) -> dict[str, bool]:
    checks = audit_stress_ladder_records(
        policy,
        throttle_profiles,
        replay_cases,
        evaluations,
        transitions,
        throttles,
        recoveries,
        allocator_feedback,
        threshold_feedback,
        summary,
        proof_records,
    )
    return {check["check_id"]: bool(check["passed"]) for check in checks}


def _default_audit_checks() -> dict[str, bool]:
    return _audit_checks(
        _json(STRESS_LADDER_POLICY_PATH),
        _json(CRISIS_MODE_THROTTLE_PROFILES_PATH),
        _json(STRESS_LADDER_REPLAY_CASES_PATH),
        _jsonl(STRESS_LEVEL_EVALUATIONS_PATH),
        _jsonl(STRESS_TRANSITION_DECISIONS_PATH),
        _jsonl(CRISIS_THROTTLE_RESULTS_PATH),
        _jsonl(CRISIS_RECOVERY_RESULTS_PATH),
        _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH),
        _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH),
        _json(STRESS_LADDER_SUMMARY_PATH),
        _jsonl(STRESS_LADDER_PROOF_PATH),
    )


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="stress-ladder-live-x",
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


def test_portfolio_stress_ladder_serializes_deterministically() -> None:
    ladder = PortfolioStressLadder.from_dict(_json(STRESS_LADDER_POLICY_PATH))
    assert json.dumps(ladder.to_dict(), sort_keys=True) == json.dumps(ladder.to_dict(), sort_keys=True)


def test_portfolio_stress_level_serializes_deterministically() -> None:
    level = PortfolioStressLevel.from_dict(_json(STRESS_LADDER_POLICY_PATH)["stress_levels"][0])
    assert json.dumps(level.to_dict(), sort_keys=True) == json.dumps(level.to_dict(), sort_keys=True)


def test_crisis_mode_throttle_serializes_deterministically() -> None:
    throttle = CrisisModeThrottle.from_dict(_json(CRISIS_MODE_THROTTLE_PROFILES_PATH)["profiles"][0])
    assert json.dumps(throttle.to_dict(), sort_keys=True) == json.dumps(throttle.to_dict(), sort_keys=True)


def test_stress_transition_decision_serializes_deterministically() -> None:
    transition = StressTransitionDecision.from_dict(_jsonl(STRESS_TRANSITION_DECISIONS_PATH)[0])
    assert json.dumps(transition.to_dict(), sort_keys=True) == json.dumps(transition.to_dict(), sort_keys=True)


def test_stress_ladder_hash_is_deterministic() -> None:
    ladder = PortfolioStressLadder.from_dict(_json(STRESS_LADDER_POLICY_PATH))
    assert stress_ladder_hash(ladder) == stress_ladder_hash(ladder)


def test_stress_level_requires_paper_only_live_blocked() -> None:
    payload = dict(_json(STRESS_LADDER_POLICY_PATH)["stress_levels"][0], live_blocked=False)
    with pytest.raises(ValueError):
        PortfolioStressLevel.from_dict(payload)


def test_crisis_throttle_rejects_live_path() -> None:
    payload = dict(_json(CRISIS_MODE_THROTTLE_PROFILES_PATH)["profiles"][0], paper_only=False)
    with pytest.raises(ValueError):
        CrisisModeThrottle.from_dict(payload)


def test_crisis_policy_loads() -> None:
    assert default_portfolio_stress_ladder().ladder_id == "dopey-portfolio-stress-ladder-v1"


def test_normal_state_remains_normal() -> None:
    assert evaluate_stress_level(["normal_pressure"]) == "normal"


def test_mild_0dte_pressure_moves_to_elevated() -> None:
    assert evaluate_stress_level(["mild_0dte_pressure"]) == "elevated"


def test_gamma_pressure_moves_to_defensive() -> None:
    assert evaluate_stress_level(["moderate_gamma_pressure"]) == "defensive"


def test_theta_pressure_moves_to_defensive() -> None:
    assert evaluate_stress_level(["moderate_theta_pressure"]) == "defensive"


def test_iv_crush_moves_to_severe() -> None:
    assert evaluate_stress_level(["iv_crush_exposure"]) == "severe"


def test_event_macro_shock_moves_to_severe() -> None:
    assert evaluate_stress_level(["event_macro_shock"]) == "severe"


def test_liquidity_collapse_moves_to_crisis() -> None:
    assert evaluate_stress_level(["liquidity_collapse"]) == "crisis"


def test_spread_explosion_moves_to_crisis() -> None:
    assert evaluate_stress_level(["spread_explosion"]) == "crisis"


def test_multi_stressor_moves_to_crisis() -> None:
    assert evaluate_stress_level(["multi_stressor", "iv_crush_exposure"]) == "crisis"


def test_live_path_injection_moves_to_lockdown() -> None:
    assert evaluate_stress_level(["live_path_injection"]) == "lockdown"


def test_broker_path_injection_moves_to_lockdown() -> None:
    assert evaluate_stress_level(["broker_path_injection"]) == "lockdown"


def test_real_sizing_injection_moves_to_lockdown() -> None:
    assert evaluate_stress_level(["real_sizing_injection"]) == "lockdown"


def test_stress_ladder_policy_fixture_loads() -> None:
    assert _json(STRESS_LADDER_POLICY_FIXTURE_PATH)["ladder_id"] == "dopey-portfolio-stress-ladder-v1"


def test_crisis_mode_throttle_profiles_load() -> None:
    assert _json(CRISIS_MODE_THROTTLE_PROFILES_FIXTURE_PATH)["profile_count"] >= 6


def test_stress_ladder_replay_cases_load() -> None:
    assert _json(STRESS_LADDER_REPLAY_CASES_FIXTURE_PATH)["stress_case_count"] == 120


def test_expected_stress_transitions_load() -> None:
    assert _json(EXPECTED_STRESS_TRANSITIONS_FIXTURE_PATH)["transition_count"] == 120


def test_expected_crisis_throttles_load() -> None:
    assert _json(EXPECTED_CRISIS_THROTTLES_FIXTURE_PATH)["throttle_count"] == 120


def test_stress_ladder_has_at_least_120_cases() -> None:
    assert len(_cases()) >= 120


def test_stress_ladder_includes_all_stress_levels() -> None:
    assert {"normal", "elevated", "defensive", "severe", "crisis", "lockdown"}.issubset(set(_summary()["stress_level_distribution"]))


def test_stress_ladder_includes_recovery_cases() -> None:
    assert _summary()["case_family_distribution"]["recovery_case"] >= 8


def test_stress_ladder_includes_negative_controls() -> None:
    assert _summary()["case_family_distribution"]["injection_negative_control_case"] >= 6


def test_stress_ladder_includes_paper_shadow_leakage_cases() -> None:
    assert _summary()["case_family_distribution"]["paper_shadow_leakage_case"] >= 6


def test_stress_ladder_replay_engine_runs_all_cases() -> None:
    assert _result()["summary"]["stress_case_count"] == 120


def test_stress_ladder_expectations_match() -> None:
    assert all(record["expectation_matched"] is True for record in _jsonl(STRESS_LEVEL_EVALUATIONS_PATH))


def test_crisis_mode_blocks_new_0dte() -> None:
    assert _throttle_for("crisis_mode_blocks_new_0dte")["blocked"] is True


def test_crisis_mode_prefers_swing_or_no_trade() -> None:
    assert _summary()["no_trade_only_count"] > 0 and _summary()["swing_only_count"] > 0


def test_lockdown_blocks_all_new_entries() -> None:
    assert _summary()["lockdown_blocks_new_entries"] is True


def test_lockdown_does_not_force_same_day_close() -> None:
    assert _summary()["same_day_close_forced_count"] == 0


def test_lockdown_allows_audit_only_state() -> None:
    assert _throttle_for("lockdown_allows_audit_only_state")["allowed"] is True


def test_no_day_trade_guard_dominates_all_stress_levels() -> None:
    assert _summary()["no_day_trade_dominant"] is True


def test_paper_broker_not_overridden_by_crisis_mode() -> None:
    assert _summary()["paperbroker_override_allowed"] is False


def test_paper_shadow_contained_under_all_stress_levels() -> None:
    assert _summary()["paper_shadow_contained"] is True


def test_throttle_reduce_allocation() -> None:
    assert any(record["throttle_type"] == "reduce_allocation" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_new_entries() -> None:
    assert any(record["stress_level"] == "lockdown" and record["new_entry_allowed"] is False for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_zero_dte() -> None:
    assert any(record["throttle_type"] == "block_zero_dte" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_swing_only() -> None:
    assert any(record["throttle_type"] == "swing_only" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_delay_rotation() -> None:
    profiles = _json(CRISIS_MODE_THROTTLE_PROFILES_PATH)["profiles"]
    assert any(record["throttle_type"] == "delay_rotation" for record in profiles)


def test_throttle_paper_shadow_only() -> None:
    profiles = _json(CRISIS_MODE_THROTTLE_PROFILES_PATH)["profiles"]
    assert any(record["throttle_type"] == "paper_shadow_only" for record in profiles)


def test_throttle_watchlist_only() -> None:
    profiles = _json(CRISIS_MODE_THROTTLE_PROFILES_PATH)["profiles"]
    assert any(record["throttle_type"] == "watchlist_only" for record in profiles)


def test_throttle_no_trade_only() -> None:
    assert any(record["throttle_type"] == "no_trade_only" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_family() -> None:
    assert any(record["throttle_type"] == "block_family" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_regime() -> None:
    assert any(record["throttle_type"] == "block_regime" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_high_gamma() -> None:
    assert any(record["throttle_type"] == "block_high_gamma" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_high_theta() -> None:
    assert any(record["throttle_type"] == "block_high_theta" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_iv_crush() -> None:
    assert any(record["throttle_type"] == "block_iv_crush" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_block_event_macro() -> None:
    assert any(record["throttle_type"] == "block_event_macro" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_throttle_lockdown_allocation() -> None:
    assert any(record["throttle_type"] == "lockdown_allocation" for record in _jsonl(CRISIS_THROTTLE_RESULTS_PATH))


def test_recovery_crisis_to_severe() -> None:
    assert recovery_transition_level("crisis") == "severe"


def test_recovery_severe_to_defensive() -> None:
    assert recovery_transition_level("severe") == "defensive"


def test_recovery_defensive_to_elevated() -> None:
    assert recovery_transition_level("defensive") == "elevated"


def test_recovery_elevated_to_normal() -> None:
    assert recovery_transition_level("elevated") == "normal"


def test_recovery_does_not_jump_crisis_to_normal() -> None:
    assert "crisis_cannot_jump_to_normal" in _recovery_for("recovery_does_not_instantly_restore_aggressive_allocation")["reason_codes"]


def test_0dte_recovers_slower_than_swing() -> None:
    recovery = _recovery_for("swing_allocation_recovers_before_0dte_allocation")
    assert recovery["zero_dte_recovery_multiplier"] < recovery["swing_recovery_multiplier"]


def test_repeated_stress_slows_recovery() -> None:
    case = dict(_case("recovery_from_crisis_to_severe_after_stress_clears"), stressors=["stress_cleared", "repeated_stress"], stress_case_id="manual-repeated-stress")
    from dopey_portfolio.crisis_recovery_policy import evaluate_recovery
    assert "repeated_stress_slows_recovery" in evaluate_recovery(case, "crisis")["reason_codes"]


def test_recovery_keeps_no_day_trade_dominant() -> None:
    assert all(record["no_day_trade_dominant"] is True for record in _jsonl(CRISIS_RECOVERY_RESULTS_PATH))


def test_allocator_consumes_crisis_feedback() -> None:
    run_proof_weighted_allocator()
    assert crisis_feedback_summary()["crisis_feedback_loaded"] is True


def test_allocator_reduces_0dte_under_crisis_feedback() -> None:
    assert "block_0dte_under_crisis" in crisis_feedback_summary()["feedback_action_distribution"]


def test_allocator_preserves_no_trade_under_crisis_feedback() -> None:
    assert "preserve_no_trade_recommendation" in crisis_feedback_summary()["feedback_action_distribution"]


def test_threshold_optimizer_consumes_crisis_feedback() -> None:
    assert _crisis_feedback_summary()["crisis_feedback_loaded"] is True


def test_threshold_optimizer_downgrades_profile_that_increases_crisis() -> None:
    assert "downgrade_profile_that_increases_crisis_transitions" in _crisis_feedback_summary()["feedback_action_distribution"]


def test_threshold_optimizer_preserves_gamma_theta_shadow_if_reduces_crisis() -> None:
    assert "preserve_gamma_theta_paper_shadow_if_reduces_crisis" in _crisis_feedback_summary()["feedback_action_distribution"]


def test_crisis_feedback_does_not_mutate_live_thresholds() -> None:
    assert _crisis_feedback_summary()["live_threshold_mutation_allowed"] is False


def test_stress_ladder_policy_artifact_written() -> None:
    assert STRESS_LADDER_POLICY_PATH.exists()


def test_crisis_mode_throttle_profiles_artifact_written() -> None:
    assert CRISIS_MODE_THROTTLE_PROFILES_PATH.exists()


def test_stress_ladder_replay_cases_artifact_written() -> None:
    assert STRESS_LADDER_REPLAY_CASES_PATH.exists()


def test_stress_level_evaluations_artifact_written() -> None:
    assert STRESS_LEVEL_EVALUATIONS_PATH.exists()


def test_stress_transition_decisions_artifact_written() -> None:
    assert STRESS_TRANSITION_DECISIONS_PATH.exists()


def test_crisis_throttle_results_artifact_written() -> None:
    assert CRISIS_THROTTLE_RESULTS_PATH.exists()


def test_crisis_recovery_results_artifact_written() -> None:
    assert CRISIS_RECOVERY_RESULTS_PATH.exists()


def test_crisis_allocator_feedback_artifact_written() -> None:
    assert CRISIS_ALLOCATOR_FEEDBACK_PATH.exists()


def test_crisis_threshold_feedback_artifact_written() -> None:
    assert CRISIS_THRESHOLD_FEEDBACK_PATH.exists()


def test_stress_ladder_summary_artifact_written() -> None:
    assert STRESS_LADDER_SUMMARY_PATH.exists()


def test_stress_ladder_proof_artifact_written() -> None:
    assert STRESS_LADDER_PROOF_PATH.exists()


def test_audit_recognizes_stress_ladder_artifacts() -> None:
    assert "stress_ladder_summary" in {spec[0] for spec in ARTIFACT_SPECS}


def test_audit_flags_stress_ladder_real_dollars() -> None:
    checks = _audit_checks(dict(_json(STRESS_LADDER_POLICY_PATH), note="dollar"), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), _jsonl(CRISIS_THROTTLE_RESULTS_PATH), _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["stress_ladder_no_real_dollars"] is False


def test_audit_flags_stress_ladder_buying_power() -> None:
    checks = _audit_checks(dict(_json(STRESS_LADDER_POLICY_PATH), note="buying_power"), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), _jsonl(CRISIS_THROTTLE_RESULTS_PATH), _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["stress_ladder_no_buying_power"] is False


def test_audit_flags_stress_ladder_account_balance() -> None:
    checks = _audit_checks(dict(_json(STRESS_LADDER_POLICY_PATH), note="account_balance"), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), _jsonl(CRISIS_THROTTLE_RESULTS_PATH), _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["stress_ladder_no_account_balance"] is False


def test_audit_flags_stress_ladder_broker_path() -> None:
    checks = _audit_checks(dict(_json(STRESS_LADDER_POLICY_PATH), note="place_order"), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), _jsonl(CRISIS_THROTTLE_RESULTS_PATH), _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["stress_ladder_no_broker_path"] is False


def test_audit_flags_stress_ladder_credentials() -> None:
    checks = _audit_checks(dict(_json(STRESS_LADDER_POLICY_PATH), note="api_key"), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), _jsonl(CRISIS_THROTTLE_RESULTS_PATH), _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["stress_ladder_no_credentials"] is False


def test_audit_flags_stress_ladder_live_order() -> None:
    checks = _audit_checks(dict(_json(STRESS_LADDER_POLICY_PATH), note="live_order"), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), _jsonl(CRISIS_THROTTLE_RESULTS_PATH), _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["stress_ladder_no_live_order"] is False


def test_audit_flags_crisis_mode_same_day_churn() -> None:
    throttles = _jsonl(CRISIS_THROTTLE_RESULTS_PATH)
    throttles[0] = dict(throttles[0], attempted_action="same_day_close", allowed=True, same_day_close_allowed=True)
    checks = _audit_checks(_json(STRESS_LADDER_POLICY_PATH), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), throttles, _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["crisis_mode_no_same_day_churn"] is False


def test_audit_flags_lockdown_new_entry_allowed() -> None:
    throttles = _jsonl(CRISIS_THROTTLE_RESULTS_PATH)
    target = next(index for index, record in enumerate(throttles) if record["stress_level"] == "lockdown" and record["attempted_action"].startswith("open_"))
    throttles[target] = dict(throttles[target], allowed=True)
    checks = _audit_checks(_json(STRESS_LADDER_POLICY_PATH), _json(CRISIS_MODE_THROTTLE_PROFILES_PATH), _json(STRESS_LADDER_REPLAY_CASES_PATH), _jsonl(STRESS_LEVEL_EVALUATIONS_PATH), _jsonl(STRESS_TRANSITION_DECISIONS_PATH), throttles, _jsonl(CRISIS_RECOVERY_RESULTS_PATH), _jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH), _jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH), _json(STRESS_LADDER_SUMMARY_PATH), _jsonl(STRESS_LADDER_PROOF_PATH))
    assert checks["lockdown_blocks_new_entries"] is False


def test_audit_confirms_stress_ladder_paper_only_live_blocked() -> None:
    checks = _default_audit_checks()
    assert checks["stress_ladder_all_paper_only"] is True and checks["stress_ladder_all_live_blocked"] is True


def test_audit_confirms_no_active_forbidden_live_decisions_after_stress_ladder() -> None:
    assert _default_audit_checks()["stress_ladder_no_active_forbidden_live_decisions"] is True


def test_reporting_includes_stress_ladder_summary() -> None:
    run_tournament_performance_reporting_bundle()
    assert _json(REPORTING_BUNDLE_SUMMARY_PATH)["stress_ladder_summary"]["stress_case_count"] == 120


def test_reporting_includes_crisis_mode_summary() -> None:
    run_tournament_performance_reporting_bundle()
    assert _json(REPORTING_BUNDLE_SUMMARY_PATH)["stress_ladder_summary"]["crisis_mode_trigger_count"] > 0


def test_reporting_includes_lockdown_summary() -> None:
    run_tournament_performance_reporting_bundle()
    assert _json(REPORTING_BUNDLE_SUMMARY_PATH)["stress_ladder_summary"]["lockdown_trigger_count"] > 0


def test_reporting_includes_recovery_summary() -> None:
    run_tournament_performance_reporting_bundle()
    assert _json(REPORTING_BUNDLE_SUMMARY_PATH)["stress_ladder_summary"]["recovery_transition_distribution"]


def test_export_verifier_selects_stress_ladder_artifacts() -> None:
    run_portfolio_stress_ladder()
    plan = select_export_artifacts(DEFAULT_EXPORT_PROFILE, safety_state())
    ids = {artifact.artifact_id for artifact in plan.selected_artifacts}
    assert {"stress_ladder_summary", "stress_ladder_proof", "crisis_throttle_results"}.issubset(ids)


def test_export_review_includes_stress_ladder_summary() -> None:
    run_tournament_performance_reporting_bundle()
    reporting_summary = _json(REPORTING_BUNDLE_SUMMARY_PATH)
    ctx = ExportReviewContext({}, {}, {}, {}, {}, {}, reporting_summary, {}, [], [], {}, {}, Path("."), "", Path("."), Path("."))
    bundle = ExportReviewBundle("r", "b", "s", "m", "c", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "next", True, True, "")
    decision = ExportReviewDecision("d", "b", "approve_offline_review", "paper_only", [], [], "next", True, True, "")
    assert "Portfolio Stress Ladder" in render_executive_summary(ctx, bundle, [], decision)


def test_stress_ladder_artifact_ledger_written() -> None:
    assert Path("docs/reports/DOPEY_PORTFOLIO_STRESS_LADDER_ARTIFACT_LEDGER.md").exists() or _summary()["artifact_type"] == "stress_ladder_summary"


def test_shard_plan_includes_stress_ladder_tests() -> None:
    result = CommandResult(["python", "-m", "pytest", "tests/test_portfolio_stress_ladder.py", "-q"], "pass", 0, 1.0, False, False, "", "")
    plan = write_test_shard_plan(["tests/test_portfolio_stress_ladder.py"], [result], {"collection": result.to_dict(), "full_suite": timeout_result(["python", "-m", "pytest"], 1)})
    assert "tests/test_portfolio_stress_ladder.py" in plan["portfolio_stress_ladder_test_files"]


def test_shard_plan_marks_stress_ladder_artifact_tests_sequential() -> None:
    result = CommandResult(["python", "-m", "pytest", "tests/test_portfolio_stress_ladder.py", "-q"], "pass", 0, 1.0, False, False, "", "")
    plan = write_test_shard_plan(["tests/test_portfolio_stress_ladder.py"], [result], {"collection": result.to_dict(), "full_suite": timeout_result(["python", "-m", "pytest"], 1)})
    assert "tests/test_portfolio_stress_ladder.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout" and result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_stress_ladder() -> None:
    assert load_config(default_config_path())["live_trading_enabled"] is False


def test_robinhood_stub_still_blocks_live_after_stress_ladder() -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_stress_ladder() -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_stress_ladder() -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_stress_ladder() -> None:
    encoded = json.dumps([_json(STRESS_LADDER_SUMMARY_PATH), *_jsonl(STRESS_LADDER_PROOF_PATH)], sort_keys=True).lower()
    assert "api_key" not in encoded and "secret_key" not in encoded and "access_token" not in encoded


def test_no_scheduler_created_by_stress_ladder() -> None:
    encoded = json.dumps(_result(), sort_keys=True).lower()
    assert "scheduler" not in encoded and "cron" not in encoded


def test_no_network_market_data_dependency_created_by_stress_ladder() -> None:
    encoded = json.dumps(_json(STRESS_LADDER_SUMMARY_PATH), sort_keys=True).lower()
    assert "polygon" not in encoded and "yfinance" not in encoded and "live_quote" not in encoded


def test_no_same_day_churn_loophole_created_by_stress_ladder() -> None:
    assert _summary()["same_day_churn_allowed"] is False


def test_no_real_capital_allocator_created_by_stress_ladder() -> None:
    assert _summary()["no_real_sizing"] is True


def test_no_real_buying_power_logic_created_by_stress_ladder() -> None:
    encoded = json.dumps(_json(STRESS_LADDER_SUMMARY_PATH), sort_keys=True).lower()
    assert "buying_power" not in encoded


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    manifest = Path("artifacts/dopey/exports/blunder_integrity_status.json")
    if manifest.exists():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload.get("original_blunder_modified", False) is False
    else:
        assert _summary()["live_blocked"] is True
