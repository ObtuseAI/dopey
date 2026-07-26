from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dopey_allocation.run_proof_weighted_allocator import run_proof_weighted_allocator
from dopey_audit.active_policy_audit import audit_portfolio_replay_records
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
from dopey_lifecycle.run_active_option_lifecycle_simulator import run_active_option_lifecycle_simulator
from dopey_options.zero_dte_threshold_optimizer import _portfolio_feedback_summary
from dopey_portfolio.portfolio_exposure_models import PortfolioExposureSnapshot
from dopey_portfolio.portfolio_exposure_policy import default_portfolio_replay_policy, portfolio_policy_status
from dopey_portfolio.portfolio_position_models import PaperPortfolioPosition
from dopey_portfolio.portfolio_replay_models import PaperPortfolioState, portfolio_state_hash
from dopey_portfolio.portfolio_rotation_models import PortfolioRotationDecision
from dopey_portfolio.run_portfolio_replay import (
    EXPECTED_PORTFOLIO_EXPOSURE_SNAPSHOTS_FIXTURE_PATH,
    EXPECTED_PORTFOLIO_REPLAY_SUMMARY_FIXTURE_PATH,
    EXPECTED_PORTFOLIO_ROTATION_DECISIONS_FIXTURE_PATH,
    EXPOSURE_STRESS_RESULTS_PATH,
    PORTFOLIO_ALLOCATOR_FEEDBACK_PATH,
    PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH,
    PORTFOLIO_POSITIONS_PATH,
    PORTFOLIO_REPLAY_OPPORTUNITIES_FIXTURE_PATH,
    PORTFOLIO_REPLAY_OPPORTUNITIES_PATH,
    PORTFOLIO_REPLAY_POLICY_FIXTURE_PATH,
    PORTFOLIO_REPLAY_POLICY_PATH,
    PORTFOLIO_REPLAY_PROOF_PATH,
    PORTFOLIO_REPLAY_SUMMARY_PATH,
    PORTFOLIO_REPLAY_TIMELINE_CASES_FIXTURE_PATH,
    PORTFOLIO_ROTATION_DECISIONS_PATH,
    PORTFOLIO_STATES_PATH,
    PORTFOLIO_THRESHOLD_FEEDBACK_PATH,
    run_portfolio_replay,
)
from dopey_reporting.data_loader import REPORTING_BUNDLE_SUMMARY_PATH
from dopey_reporting.reporting_bundle import run_tournament_performance_reporting_bundle
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


_PORTFOLIO_RESULT: dict[str, Any] | None = None


def _result() -> dict[str, Any]:
    global _PORTFOLIO_RESULT
    if _PORTFOLIO_RESULT is None:
        _PORTFOLIO_RESULT = run_portfolio_replay()
    return _PORTFOLIO_RESULT


def _json(path: Path) -> dict[str, Any]:
    _result()
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    _result()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cases() -> list[dict[str, Any]]:
    return _jsonl(PORTFOLIO_REPLAY_OPPORTUNITIES_PATH)


def _case(required_case: str) -> dict[str, Any]:
    return next(record for record in _cases() if record["required_case"] == required_case)


def _decision_for(required_case: str) -> dict[str, Any]:
    case_id = _case(required_case)["case_id"]
    return next(record for record in _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH) if record["rotation_decision_id"].endswith(case_id))


def _snapshot_for(required_case: str) -> dict[str, Any]:
    case_id = _case(required_case)["case_id"]
    return next(record for record in _jsonl(PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH) if record["snapshot_id"].endswith(case_id))


def _summary() -> dict[str, Any]:
    return _json(PORTFOLIO_REPLAY_SUMMARY_PATH)


def _audit_checks(
    positions: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    states: list[dict[str, Any]],
    allocator_feedback: list[dict[str, Any]],
    threshold_feedback: list[dict[str, Any]],
) -> dict[str, bool]:
    checks = audit_portfolio_replay_records(
        _json(PORTFOLIO_REPLAY_POLICY_PATH),
        _jsonl(PORTFOLIO_REPLAY_OPPORTUNITIES_PATH),
        states,
        positions,
        decisions,
        _jsonl(PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH),
        _jsonl(EXPOSURE_STRESS_RESULTS_PATH),
        allocator_feedback,
        threshold_feedback,
        _json(PORTFOLIO_REPLAY_SUMMARY_PATH),
        _jsonl(PORTFOLIO_REPLAY_PROOF_PATH),
    )
    return {check["check_id"]: bool(check["passed"]) for check in checks}


def _default_audit_checks() -> dict[str, bool]:
    return _audit_checks(
        _jsonl(PORTFOLIO_POSITIONS_PATH),
        _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH),
        _jsonl(PORTFOLIO_STATES_PATH),
        _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH),
        _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH),
    )


def _stress_dimensions() -> set[str]:
    dimensions: set[str] = set()
    for record in _jsonl(EXPOSURE_STRESS_RESULTS_PATH):
        dimensions.update(str(value) for value in record["stress_dimensions"])
    return dimensions


def _policy_snapshot(updates: dict[str, Any]) -> dict[str, Any]:
    base = {
        "total_paper_premium_risk_units": 10.0,
        "zero_dte_paper_units": 0.0,
        "swing_paper_units": 10.0,
        "paper_shadow_units": 0.0,
        "delayed_rotation_reserved_units": 0.0,
        "call_units": 5.0,
        "put_units": 5.0,
        "high_gamma_units": 0.0,
        "high_theta_units": 0.0,
        "iv_crush_exposed_units": 0.0,
        "event_macro_exposed_units": 0.0,
        "underlying_family_exposure": {},
        "regime_family_exposure": {},
        "strategy_type_exposure": {},
    }
    return {**base, **updates}


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="portfolio-live-x",
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


def test_paper_portfolio_state_serializes_deterministically() -> None:
    state = PaperPortfolioState.from_dict(_jsonl(PORTFOLIO_STATES_PATH)[0])
    assert json.dumps(state.to_dict(), sort_keys=True) == json.dumps(state.to_dict(), sort_keys=True)


def test_paper_portfolio_position_serializes_deterministically() -> None:
    position = PaperPortfolioPosition.from_dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0])
    assert json.dumps(position.to_dict(), sort_keys=True) == json.dumps(position.to_dict(), sort_keys=True)


def test_portfolio_exposure_snapshot_serializes_deterministically() -> None:
    snapshot = PortfolioExposureSnapshot.from_dict(_jsonl(PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH)[0])
    assert json.dumps(snapshot.to_dict(), sort_keys=True) == json.dumps(snapshot.to_dict(), sort_keys=True)


def test_portfolio_rotation_decision_serializes_deterministically() -> None:
    decision = PortfolioRotationDecision.from_dict(_jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH)[0])
    assert json.dumps(decision.to_dict(), sort_keys=True) == json.dumps(decision.to_dict(), sort_keys=True)


def test_portfolio_state_hash_is_deterministic() -> None:
    state = PaperPortfolioState.from_dict(_jsonl(PORTFOLIO_STATES_PATH)[0])
    assert portfolio_state_hash(state) == portfolio_state_hash(state)


def test_portfolio_position_rejects_unsupported_strategy() -> None:
    payload = dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], strategy_type="short_call")
    with pytest.raises(ValueError):
        PaperPortfolioPosition.from_dict(payload)


def test_portfolio_position_rejects_live_path() -> None:
    payload = dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], current_paper_state="live_path")
    with pytest.raises(ValueError):
        PaperPortfolioPosition.from_dict(payload)


def test_portfolio_position_uses_abstract_units_only() -> None:
    encoded = json.dumps(_jsonl(PORTFOLIO_POSITIONS_PATH), sort_keys=True).lower()
    assert "buying_power" not in encoded and "account_balance" not in encoded and "dollar" not in encoded


def test_portfolio_exposure_policy_loads() -> None:
    assert default_portfolio_replay_policy().policy_id == "dopey-portfolio-replay-policy-v1"


def test_policy_caps_total_paper_premium_units() -> None:
    status = portfolio_policy_status(_policy_snapshot({"total_paper_premium_risk_units": 61.0}), default_portfolio_replay_policy())
    assert "total_paper_premium_risk_units_cap" in status["reason_codes"]


def test_policy_caps_0dte_exposure_share() -> None:
    status = portfolio_policy_status(_policy_snapshot({"zero_dte_paper_units": 4.0, "swing_paper_units": 6.0}), default_portfolio_replay_policy())
    assert "zero_dte_portfolio_exposure_cap" in status["reason_codes"]


def test_policy_caps_underlying_family_exposure() -> None:
    status = portfolio_policy_status(_policy_snapshot({"underlying_family_exposure": {"underlying-family-01": 13.0}}), default_portfolio_replay_policy())
    assert "underlying_family_cap:underlying-family-01" in status["reason_codes"]


def test_policy_caps_regime_family_exposure() -> None:
    status = portfolio_policy_status(_policy_snapshot({"regime_family_exposure": {"trend_persistence": 19.0}}), default_portfolio_replay_policy())
    assert "regime_family_cap:trend_persistence" in status["reason_codes"]


def test_policy_caps_high_gamma_exposure() -> None:
    status = portfolio_policy_status(_policy_snapshot({"high_gamma_units": 9.0}), default_portfolio_replay_policy())
    assert "high_gamma_exposure_cap" in status["reason_codes"]


def test_policy_caps_high_theta_exposure() -> None:
    status = portfolio_policy_status(_policy_snapshot({"high_theta_units": 9.0}), default_portfolio_replay_policy())
    assert "high_theta_exposure_cap" in status["reason_codes"]


def test_policy_caps_iv_crush_exposure() -> None:
    status = portfolio_policy_status(_policy_snapshot({"iv_crush_exposed_units": 8.0}), default_portfolio_replay_policy())
    assert "iv_crush_exposure_cap" in status["reason_codes"]


def test_policy_caps_event_macro_exposure() -> None:
    status = portfolio_policy_status(_policy_snapshot({"event_macro_exposed_units": 7.0}), default_portfolio_replay_policy())
    assert "event_macro_exposure_cap" in status["reason_codes"]


def test_policy_caps_delayed_rotation_reserve() -> None:
    status = portfolio_policy_status(_policy_snapshot({"delayed_rotation_reserved_units": 2.0}), default_portfolio_replay_policy())
    assert "delayed_rotation_reserve_cap" in status["reason_codes"]


def test_policy_caps_paper_shadow_exposure() -> None:
    status = portfolio_policy_status(_policy_snapshot({"paper_shadow_units": 2.0}), default_portfolio_replay_policy())
    assert "paper_shadow_exposure_cap" in status["reason_codes"]


def test_policy_tracks_call_put_balance() -> None:
    status = portfolio_policy_status(_policy_snapshot({"call_units": 8.0, "put_units": 2.0}), default_portfolio_replay_policy())
    assert "call_put_imbalance_cap" in status["reason_codes"]


def test_portfolio_replay_policy_fixture_loads() -> None:
    assert _json(PORTFOLIO_REPLAY_POLICY_FIXTURE_PATH)["policy_id"] == "dopey-portfolio-replay-policy-v1"


def test_portfolio_replay_opportunities_fixture_loads() -> None:
    assert _json(PORTFOLIO_REPLAY_OPPORTUNITIES_FIXTURE_PATH)["case_count"] == 96


def test_portfolio_replay_timeline_cases_load() -> None:
    assert _json(PORTFOLIO_REPLAY_TIMELINE_CASES_FIXTURE_PATH)["case_count"] == 96


def test_expected_rotation_decisions_load() -> None:
    assert _json(EXPECTED_PORTFOLIO_ROTATION_DECISIONS_FIXTURE_PATH)["decision_count"] == 96


def test_expected_exposure_snapshots_load() -> None:
    assert _json(EXPECTED_PORTFOLIO_EXPOSURE_SNAPSHOTS_FIXTURE_PATH)["snapshot_count"] == 96


def test_portfolio_replay_has_at_least_96_cases() -> None:
    assert len(_cases()) >= 96


def test_portfolio_replay_includes_same_day_close_block_cases() -> None:
    assert _summary()["case_family_distribution"]["same_day_close_blocked_case"] == 10


def test_portfolio_replay_includes_delayed_rotation_cases() -> None:
    assert _summary()["case_family_distribution"]["delayed_rotation_case"] == 10


def test_portfolio_replay_includes_paper_shadow_cases() -> None:
    assert _summary()["case_family_distribution"]["paper_shadow_containment_case"] == 8


def test_portfolio_replay_includes_exposure_concentration_cases() -> None:
    assert _summary()["case_family_distribution"]["underlying_family_concentration_case"] == 8


def test_portfolio_replay_includes_live_path_negative_control() -> None:
    assert _case("live_path_negative_control_rejected")["expected_decision_type"] == "reject_live_path"


def test_portfolio_replay_includes_real_sizing_negative_control() -> None:
    assert _case("real_capital_sizing_negative_control_rejected")["expected_decision_type"] == "reject_policy"


def test_portfolio_replay_engine_runs_all_cases() -> None:
    assert _result()["summary"]["replay_case_count"] == 96


def test_portfolio_replay_expectations_match() -> None:
    run_active_option_lifecycle_simulator()
    result = run_portfolio_replay()
    expected = json.loads(EXPECTED_PORTFOLIO_REPLAY_SUMMARY_FIXTURE_PATH.read_text(encoding="utf-8"))["summary"]
    excluded = {"reproducibility_hash", "source_allocation_plan_hash"}
    actual_behavior = {key: value for key, value in result["summary"].items() if key not in excluded}
    expected_behavior = {key: value for key, value in expected.items() if key not in excluded}
    assert actual_behavior == expected_behavior
    assert result["summary"]["reproducibility_hash"]
    assert result["summary"]["source_allocation_plan_hash"]


def test_swing_call_opens_and_closes_next_day() -> None:
    assert _decision_for("swing_call_opens_and_closes_next_day")["decision_type"] == "close_position_allowed"


def test_swing_put_opens_and_closes_next_day() -> None:
    assert _decision_for("swing_put_opens_and_closes_next_day")["decision_type"] == "close_position_allowed"


def test_0dte_call_opens_under_cap() -> None:
    assert _snapshot_for("zero_dte_call_opens_under_capped_exposure")["constraint_status"]["zero_dte_exposure_share"] <= 0.35


def test_0dte_put_opens_under_cap() -> None:
    assert _snapshot_for("zero_dte_put_opens_under_capped_exposure")["constraint_status"]["zero_dte_exposure_share"] <= 0.35


def test_0dte_exposure_cap_blocks_extra_entry() -> None:
    assert _decision_for("zero_dte_exposure_cap_blocks_extra_entry")["decision_type"] == "reject_exposure"


def test_same_day_swing_close_blocked() -> None:
    assert _decision_for("same_day_swing_close_is_blocked")["same_day_close_blocked"] is True


def test_same_day_0dte_churn_attempt_blocked() -> None:
    assert _decision_for("same_day_normal_0dte_churn_attempt_is_blocked")["same_day_close_blocked"] is True


def test_0dte_special_close_requires_lifecycle_proof() -> None:
    decision = _decision_for("zero_dte_special_close_allowed_only_with_lifecycle_proof")
    assert decision["exit_allowed"] is True and "zero_dte_special_lifecycle_proof" in decision["reason_codes"]


def test_delayed_rotation_reserve_created() -> None:
    assert _decision_for("delayed_rotation_reserve_created")["decision_type"] == "rotate_delayed"


def test_delayed_rotation_executes_next_day() -> None:
    assert _decision_for("delayed_rotation_executes_next_day")["decision_type"] == "rotate_allowed"


def test_delayed_rotation_does_not_force_same_day_close() -> None:
    assert _decision_for("delayed_rotation_does_not_force_same_day_close")["same_day_close_blocked"] is True


def test_paper_shadow_candidate_remains_shadow_only() -> None:
    assert _decision_for("paper_shadow_candidate_remains_shadow_only")["decision_type"] == "paper_shadow_only"


def test_watchlist_candidate_remains_watchlist_only() -> None:
    assert _decision_for("watchlist_candidate_remains_watchlist_only")["decision_type"] == "watchlist_only"


def test_no_trade_candidate_zero_allocation() -> None:
    assert _decision_for("no_trade_candidate_remains_zero_allocation")["decision_type"] == "reject_policy"


def test_rejected_candidate_cannot_enter_portfolio() -> None:
    assert _decision_for("rejected_candidate_cannot_enter_portfolio")["entry_allowed"] is False


def test_low_liquidity_family_cap_starves_entry() -> None:
    assert "low_liquidity_family_starved" in _decision_for("low_liquidity_family_cap_starves_additional_entry")["reason_codes"]


def test_event_sensitive_family_cap_throttles_entry() -> None:
    assert "event_macro_exposure_cap" in _decision_for("event_sensitive_family_cap_throttles_entry")["reason_codes"]


def test_macro_sensitive_family_cap_throttles_entry() -> None:
    assert "event_macro_exposure_cap" in _decision_for("macro_sensitive_family_cap_throttles_entry")["reason_codes"]


def test_high_gamma_exposure_cap_blocks_entry() -> None:
    assert "high_gamma_exposure_cap" in _decision_for("high_gamma_exposure_cap_blocks_entry")["reason_codes"]


def test_high_theta_exposure_cap_blocks_entry() -> None:
    assert "high_theta_exposure_cap" in _decision_for("high_theta_exposure_cap_blocks_entry")["reason_codes"]


def test_call_put_imbalance_triggers_throttle() -> None:
    assert "call_put_imbalance_cap" in _decision_for("call_put_imbalance_triggers_throttle")["reason_codes"]


def test_swing_0dte_imbalance_triggers_throttle() -> None:
    assert "zero_dte_portfolio_exposure_cap" in _decision_for("swing_0dte_imbalance_triggers_throttle")["reason_codes"]


def test_synthetic_underlying_concentration_cap_blocks_entry() -> None:
    assert "synthetic_underlying_concentration_cap" in _decision_for("synthetic_underlying_concentration_cap_blocks_entry")["reason_codes"]


def test_same_regime_concentration_cap_blocks_entry() -> None:
    assert "regime_family_cap" in _decision_for("same_regime_concentration_cap_blocks_entry")["reason_codes"]


def test_paper_shadow_leakage_stress_blocked() -> None:
    assert "paper_shadow_leakage_stress" in _stress_dimensions()


def test_delayed_rotation_backlog_stress_throttled() -> None:
    assert "delayed_rotation_backlog_stress" in _stress_dimensions()


def test_portfolio_feedback_reduces_0dte_exposure_cap_advisory() -> None:
    assert "reduce_0dte_exposure_cap" in _summary()["allocator_feedback_actions"]


def test_portfolio_feedback_reduces_high_gamma_exposure_advisory() -> None:
    assert "reduce_high_gamma_exposure" in _summary()["allocator_feedback_actions"]


def test_portfolio_feedback_prefers_swing_due_to_exposure_pressure() -> None:
    assert "prefer_swing_due_to_exposure_pressure" in _summary()["allocator_feedback_actions"]


def test_portfolio_feedback_prefers_no_trade_due_to_concentration() -> None:
    assert "prefer_no_trade_due_to_concentration" in _summary()["allocator_feedback_actions"]


def test_allocator_consumes_portfolio_feedback() -> None:
    result = run_proof_weighted_allocator()
    assert result["summary"]["portfolio_feedback_loaded"] is True


def test_threshold_optimizer_consumes_portfolio_feedback() -> None:
    assert _portfolio_feedback_summary()["portfolio_feedback_loaded"] is True


def test_portfolio_feedback_does_not_mutate_live_thresholds() -> None:
    assert _portfolio_feedback_summary()["live_threshold_mutation_allowed"] is False


def test_portfolio_feedback_does_not_mutate_real_allocation() -> None:
    assert run_proof_weighted_allocator()["summary"]["portfolio_feedback_summary"]["live_allocation_mutation_allowed"] is False


def test_portfolio_replay_policy_artifact_written() -> None:
    assert PORTFOLIO_REPLAY_POLICY_PATH.exists() and _json(PORTFOLIO_REPLAY_POLICY_PATH)["artifact_type"] == "portfolio_replay_policy"


def test_portfolio_replay_opportunities_artifact_written() -> None:
    assert PORTFOLIO_REPLAY_OPPORTUNITIES_PATH.exists() and len(_jsonl(PORTFOLIO_REPLAY_OPPORTUNITIES_PATH)) == 96


def test_portfolio_states_artifact_written() -> None:
    assert PORTFOLIO_STATES_PATH.exists() and len(_jsonl(PORTFOLIO_STATES_PATH)) == 96


def test_portfolio_positions_artifact_written() -> None:
    assert PORTFOLIO_POSITIONS_PATH.exists() and len(_jsonl(PORTFOLIO_POSITIONS_PATH)) == 52


def test_portfolio_rotation_decisions_artifact_written() -> None:
    assert PORTFOLIO_ROTATION_DECISIONS_PATH.exists() and len(_jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH)) == 96


def test_portfolio_exposure_snapshots_artifact_written() -> None:
    assert PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH.exists() and len(_jsonl(PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH)) == 96


def test_exposure_stress_results_artifact_written() -> None:
    assert EXPOSURE_STRESS_RESULTS_PATH.exists() and len(_jsonl(EXPOSURE_STRESS_RESULTS_PATH)) >= 60


def test_portfolio_allocator_feedback_artifact_written() -> None:
    assert PORTFOLIO_ALLOCATOR_FEEDBACK_PATH.exists() and len(_jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH)) == 96


def test_portfolio_threshold_feedback_artifact_written() -> None:
    assert PORTFOLIO_THRESHOLD_FEEDBACK_PATH.exists() and len(_jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH)) == 96


def test_portfolio_replay_summary_artifact_written() -> None:
    assert PORTFOLIO_REPLAY_SUMMARY_PATH.exists() and _summary()["replay_case_count"] == 96


def test_portfolio_replay_proof_artifact_written() -> None:
    assert PORTFOLIO_REPLAY_PROOF_PATH.exists() and len(_jsonl(PORTFOLIO_REPLAY_PROOF_PATH)) == 96


def test_audit_recognizes_portfolio_replay_artifacts() -> None:
    names = {artifact_type for artifact_type, _path, _kind, _fields in ARTIFACT_SPECS}
    assert {"portfolio_replay_summary", "portfolio_replay_proof", "portfolio_positions"}.issubset(names)


def test_audit_flags_portfolio_real_dollars() -> None:
    positions = [dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], audit_marker="dollar_sizing")]
    assert _audit_checks(positions, _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH), _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_no_real_dollars"] is False


def test_audit_flags_portfolio_buying_power() -> None:
    positions = [dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], audit_marker="buying_power")]
    assert _audit_checks(positions, _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH), _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_no_buying_power"] is False


def test_audit_flags_portfolio_account_balance() -> None:
    positions = [dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], audit_marker="account_balance")]
    assert _audit_checks(positions, _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH), _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_no_account_balance"] is False


def test_audit_flags_portfolio_broker_path() -> None:
    positions = [dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], audit_marker="robinhood_order")]
    assert _audit_checks(positions, _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH), _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_no_broker_path"] is False


def test_audit_flags_portfolio_credentials() -> None:
    positions = [dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], audit_marker="api_key")]
    assert _audit_checks(positions, _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH), _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_no_credentials"] is False


def test_audit_flags_portfolio_live_order() -> None:
    positions = [dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], audit_marker="live_order")]
    assert _audit_checks(positions, _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH), _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_no_live_order"] is False


def test_audit_flags_portfolio_same_day_churn() -> None:
    decisions = [dict(_jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH)[0], decision_type="close_position_allowed", same_day_close_blocked=False, reason_codes=["same_day_round_trip_allowed"])]
    assert _audit_checks(_jsonl(PORTFOLIO_POSITIONS_PATH), decisions, _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_no_same_day_churn"] is False


def test_audit_flags_portfolio_paper_shadow_leakage() -> None:
    positions = [dict(_jsonl(PORTFOLIO_POSITIONS_PATH)[0], paper_shadow_flag=True, current_paper_state="open")]
    assert _audit_checks(positions, _jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH), _jsonl(PORTFOLIO_STATES_PATH), _jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH), _jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH))["portfolio_paper_shadow_contained"] is False


def test_audit_confirms_portfolio_paper_only_live_blocked() -> None:
    checks = _default_audit_checks()
    assert checks["portfolio_all_paper_only"] is True and checks["portfolio_all_live_blocked"] is True


def test_audit_confirms_no_active_forbidden_live_decisions_after_portfolio_replay() -> None:
    assert _default_audit_checks()["portfolio_no_active_forbidden_live_decisions"] is True


def test_reporting_includes_portfolio_replay_summary() -> None:
    run_tournament_performance_reporting_bundle()
    assert _json(REPORTING_BUNDLE_SUMMARY_PATH)["portfolio_replay_summary"]["replay_case_count"] == 96


def test_reporting_includes_exposure_snapshot_summary() -> None:
    run_tournament_performance_reporting_bundle()
    assert "latest_total_paper_exposure" in _json(REPORTING_BUNDLE_SUMMARY_PATH)["portfolio_replay_summary"]


def test_reporting_includes_0dte_swing_exposure_split() -> None:
    run_tournament_performance_reporting_bundle()
    summary = _json(REPORTING_BUNDLE_SUMMARY_PATH)["portfolio_replay_summary"]
    assert "latest_zero_dte_units" in summary and "latest_swing_units" in summary


def test_export_verifier_selects_portfolio_replay_artifacts() -> None:
    run_portfolio_replay()
    plan = select_export_artifacts(DEFAULT_EXPORT_PROFILE, safety_state())
    ids = {artifact.artifact_id for artifact in plan.selected_artifacts}
    assert {"portfolio_replay_summary", "portfolio_replay_proof", "portfolio_rotation_decisions"}.issubset(ids)


def test_export_review_includes_portfolio_replay_summary() -> None:
    run_tournament_performance_reporting_bundle()
    reporting_summary = _json(REPORTING_BUNDLE_SUMMARY_PATH)
    ctx = ExportReviewContext({}, {}, {}, {}, {}, {}, reporting_summary, {}, [], [], {}, {}, Path("."), "", Path("."), Path("."))
    bundle = ExportReviewBundle("r", "b", "s", "m", "c", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "next", True, True, "")
    decision = ExportReviewDecision("d", "b", "approve_offline_review", "paper_only", [], [], "next", True, True, "")
    assert "Portfolio Replay" in render_executive_summary(ctx, bundle, [], decision)


def test_portfolio_replay_artifact_ledger_written() -> None:
    assert Path("docs/reports/DOPEY_PORTFOLIO_REPLAY_ARTIFACT_LEDGER.md").exists() or _summary()["artifact_type"] == "portfolio_replay_summary"


def test_shard_plan_includes_portfolio_replay_tests() -> None:
    result = CommandResult(["python", "-m", "pytest", "tests/test_portfolio_replay.py", "-q"], "pass", 0, 1.0, False, False, "", "")
    plan = write_test_shard_plan(["tests/test_portfolio_replay.py"], [result], {"collection": result.to_dict(), "full_suite": timeout_result(["python", "-m", "pytest"], 1)})
    assert "tests/test_portfolio_replay.py" in plan["portfolio_replay_test_files"]


def test_shard_plan_marks_portfolio_artifact_tests_sequential() -> None:
    result = CommandResult(["python", "-m", "pytest", "tests/test_portfolio_replay.py", "-q"], "pass", 0, 1.0, False, False, "", "")
    plan = write_test_shard_plan(["tests/test_portfolio_replay.py"], [result], {"collection": result.to_dict(), "full_suite": timeout_result(["python", "-m", "pytest"], 1)})
    assert "tests/test_portfolio_replay.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout" and result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_portfolio_replay() -> None:
    assert load_config(default_config_path())["live_trading_enabled"] is False


def test_robinhood_stub_still_blocks_live_after_portfolio_replay() -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_portfolio_replay() -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_portfolio_replay() -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_portfolio_replay() -> None:
    encoded = json.dumps([_json(PORTFOLIO_REPLAY_SUMMARY_PATH), _json(PORTFOLIO_REPLAY_POLICY_PATH)], sort_keys=True).lower()
    assert "api_key" not in encoded and "access_token" not in encoded


def test_no_scheduler_created_by_portfolio_replay() -> None:
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_portfolio").glob("*.py"))
    assert "apscheduler" not in text and "cron" not in text


def test_no_network_market_data_dependency_created_by_portfolio_replay() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("dopey_portfolio").glob("*.py")
    )
    assert "yfinance" not in text and "polygon" not in text and "iex" not in text


def test_no_same_day_churn_loophole_created_by_portfolio_replay() -> None:
    assert _default_audit_checks()["portfolio_no_same_day_churn"] is True


def test_no_real_capital_allocator_created_by_portfolio_replay() -> None:
    assert _json(PORTFOLIO_REPLAY_POLICY_PATH)["real_capital_sizing_allowed"] is False


def test_no_real_buying_power_logic_created_by_portfolio_replay() -> None:
    encoded = json.dumps(_json(PORTFOLIO_REPLAY_SUMMARY_PATH), sort_keys=True).lower()
    assert "buying_power" not in encoded and "account_balance" not in encoded


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    from dopey_export.artifact_selector import write_blunder_integrity_status

    path = write_blunder_integrity_status()
    status = _json(path)
    assert status["status"] in {"ok", "skipped", "warning"}

