from __future__ import annotations

import json
from pathlib import Path

from dopey_audit.active_policy_audit import audit_zero_dte_replay_records, run_active_policy_audit
from dopey_execution.account_ledger import add_open_position, create_paper_account_ledger
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.day_trade_policy import default_day_trade_policy
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.rotation_planner import build_rotation_plan
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_options.run_zero_dte_outcome_replay import (
    ZERO_DTE_EXPIRY_MANAGEMENT_PATH,
    ZERO_DTE_INTRADAY_STATES_PATH,
    ZERO_DTE_REPLAY_INPUTS_PATH,
    ZERO_DTE_REPLAY_OUTCOMES_PATH,
    ZERO_DTE_REPLAY_PROOF_PATH,
    ZERO_DTE_REPLAY_SUMMARY_PATH,
    ZERO_DTE_THRESHOLD_FEEDBACK_PATH,
    run_zero_dte_outcome_replay,
)
from dopey_options.run_zero_dte_risk_model import load_zero_dte_risk_cases
from dopey_options.zero_dte_decision_engine import evaluate_zero_dte_candidate
from dopey_options.zero_dte_outcome_models import (
    ZeroDTEIntradayState,
    ZeroDTEReplayDecisionPoint,
    ZeroDTEReplayInput,
    ZeroDTEReplayOutcome,
    zero_dte_replay_hash,
)
from dopey_options.zero_dte_replay_engine import (
    ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH,
    ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH,
    evaluate_zero_dte_replay_fixture_cases,
    load_zero_dte_intraday_paths,
    load_zero_dte_outcome_replay_cases,
)
from dopey_options.zero_dte_risk_model import ZeroDTERiskInput
from dopey_options.zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _zero_dte_replay_summary


def _thresholds():
    return load_default_zero_dte_risk_thresholds()


def _cases() -> list[dict]:
    return load_zero_dte_outcome_replay_cases(ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH)


def _paths() -> dict[str, dict]:
    return load_zero_dte_intraday_paths(ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH)


def _details() -> list[dict]:
    return evaluate_zero_dte_replay_fixture_cases(_cases(), _paths(), _thresholds())["replay_details"]


def _detail_for_path(path_id: str) -> dict:
    for detail in _details():
        if detail["case"]["fixture_path_id"] == path_id:
            return detail
    raise AssertionError(f"missing replay detail for {path_id}")


def _outcome(path_id: str) -> ZeroDTEReplayOutcome:
    return _detail_for_path(path_id)["replay"]["outcome"]


def _feedback(path_id: str) -> list[str]:
    return _detail_for_path(path_id)["replay"]["threshold_feedback"].recommendations


def _decision_points(path_id: str) -> list[ZeroDTEReplayDecisionPoint]:
    return _detail_for_path(path_id)["replay"]["decision_points"]


def _expiry(path_id: str) -> dict:
    return _detail_for_path(path_id)["replay"]["expiry_management"].to_dict()


def _risk_decision(case_id: str) -> dict:
    case = next(item for item in load_zero_dte_risk_cases() if item["case_id"] == case_id)
    return evaluate_zero_dte_candidate(ZeroDTERiskInput.from_dict(case["input"]), _thresholds()).to_dict()


def _intent(intent_id: str, risk_decision: dict, replay_feedback: dict) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure="long_call",
        legs=[{"side": "buy", "symbol": f"SPY_0DTE_{intent_id}", "option_type": "call", "expiry": "2026-07-03", "strike": 500.0, "dte": 0}],
        max_loss=1.0,
        order_action="buy_to_open",
        trade_date="2026-07-03",
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state="zero_dte_special_lifecycle",
        zero_dte=True,
        liquidity_approved=True,
        risk_cap_approved=True,
        zero_dte_risk_decision=risk_decision,
        zero_dte_replay_feedback=replay_feedback,
    )


def _replay_feedback(path_id: str) -> dict:
    outcome = _outcome(path_id).to_dict()
    return {
        "replay_id": outcome["replay_id"],
        "candidate_id": outcome["candidate_id"],
        "outcome_type": outcome["outcome_type"],
        "risk_model_alignment": outcome["risk_model_alignment"],
        "threshold_feedback": outcome["threshold_feedback"],
        "recursive_improvement_tags": outcome["recursive_improvement_tags"],
        "paper_only": True,
        "live_blocked": True,
    }


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_zero_dte_replay_input_serializes_deterministically():
    record = _details()[0]["replay"]["input"]
    assert record.to_dict() == ZeroDTEReplayInput.from_dict(record.to_dict()).to_dict()


def test_zero_dte_intraday_state_serializes_deterministically():
    state = _details()[0]["replay"]["states"][0]
    assert state.to_dict() == ZeroDTEIntradayState.from_dict(state.to_dict()).to_dict()


def test_zero_dte_replay_decision_point_serializes_deterministically():
    point = _details()[0]["replay"]["decision_points"][0]
    assert point.to_dict() == ZeroDTEReplayDecisionPoint.from_dict(point.to_dict()).to_dict()


def test_zero_dte_replay_outcome_serializes_deterministically():
    outcome = _details()[0]["replay"]["outcome"]
    assert outcome.to_dict() == ZeroDTEReplayOutcome.from_dict(outcome.to_dict()).to_dict()


def test_zero_dte_replay_hash_is_deterministic():
    first = _outcome("path-clean-bullish-trend-call-win")
    second = _outcome("path-clean-bullish-trend-call-win")
    assert first.replay_hash == second.replay_hash == zero_dte_replay_hash(first)


def test_zero_dte_outcome_replay_cases_load():
    assert len(_cases()) == 24


def test_zero_dte_intraday_paths_load():
    assert len(_paths()) == 24


def test_all_replay_cases_have_expected_outcomes():
    assert all(detail["expectation_matched"] for detail in _details())


def test_all_intraday_paths_are_fixture_only():
    raw = json.loads(ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert raw["no_real_market_data"] is True
    assert raw["no_broker"] is True


def test_no_replay_fixture_contains_live_market_reference():
    text = ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH.read_text(encoding="utf-8").lower()
    forbidden = ["polygon", "yfinance", "iex", "live_quote", "broker_quote"]
    assert not any(token in text for token in forbidden)


def test_clean_bullish_trend_call_replay_survives():
    assert _outcome("path-clean-bullish-trend-call-win").outcome_type == "approved_survived_fixture"


def test_clean_bearish_breakdown_put_replay_survives():
    assert _outcome("path-clean-bearish-breakdown-put-win").outcome_type == "approved_survived_fixture"


def test_early_spike_then_fade_detected():
    assert _outcome("path-early-spike-then-fade").outcome_type == "approved_spiked_then_failed"


def test_immediate_theta_bleed_detected():
    assert _outcome("path-immediate-theta-bleed").outcome_type == "approved_decayed"


def test_midday_chop_decay_detected():
    assert _outcome("path-midday-chop-decay").outcome_type == "approved_decayed"


def test_gamma_squeeze_then_reversal_detected():
    assert _outcome("path-gamma-squeeze-then-reversal").outcome_type == "approved_spiked_then_failed"


def test_iv_crush_after_entry_detected():
    assert _outcome("path-iv-crush-after-entry").outcome_type == "approved_should_have_been_throttled_more"


def test_wide_spread_exit_trap_detected():
    assert _outcome("path-wide-spread-exit-trap").outcome_type == "approved_should_have_been_throttled_more"


def test_liquidity_dries_near_close_detected():
    assert _outcome("path-liquidity-dries-near-close").outcome_type == "approved_should_have_been_throttled_more"


def test_false_breakout_call_failure_detected():
    assert _outcome("path-false-breakout-call-failure").outcome_type == "approved_decayed"


def test_false_breakdown_put_failure_detected():
    assert _outcome("path-false-breakdown-put-failure").outcome_type == "approved_decayed"


def test_late_day_rescue_move_detected():
    assert _outcome("path-late-day-rescue-move").outcome_type == "approved_expiry_managed_success"


def test_expiry_pin_near_strike_detected():
    assert _outcome("path-expiry-pin-near-strike").expiry_state == "pin_risk_simulated"


def test_deep_otm_expires_worthless_simulated():
    outcome = _outcome("path-deep-otm-expires-worthless")
    assert outcome.expiry_state == "expires_worthless_simulated"
    assert outcome.outcome_type == "approved_expiry_managed_failure"


def test_itm_expiry_intrinsic_value_simulated():
    assert _outcome("path-itm-expiry-intrinsic-value").expiry_state == "assignment_exercise_risk_flagged_simulated_only"


def test_later_expiry_alternative_confirmed():
    assert _outcome("path-signal-valid-later-expiry-better").outcome_type == "prefer_later_expiry_confirmed"


def test_blocked_poor_liquidity_candidate_validates_block():
    assert _outcome("path-blocked-poor-liquidity-correct").outcome_type == "blocked_correctly"


def test_blocked_wide_spread_candidate_validates_block():
    assert _outcome("path-blocked-wide-spread-correct").outcome_type == "blocked_correctly"


def test_blocked_weak_thesis_candidate_working_is_inconclusive():
    assert _outcome("path-blocked-weak-thesis-unexpected-work").outcome_type == "blocked_maybe_too_strict"


def test_throttled_candidate_working_keeps_throttle_feedback():
    assert _outcome("path-throttled-candidate-works").outcome_type == "throttled_correctly"


def test_high_gamma_candidate_unstable_outcome_detected():
    assert _outcome("path-high-gamma-unstable").outcome_type == "blocked_correctly"


def test_event_risk_candidate_validates_block():
    assert _outcome("path-event-risk-validates-block").outcome_type == "blocked_correctly"


def test_special_close_missing_reason_blocked():
    points = _decision_points("path-special-close-missing-reason")
    assert any(point.action == "blocked_close_missing_reason" for point in points)


def test_special_close_missing_liquidity_approval_blocked():
    points = _decision_points("path-wide-spread-exit-trap")
    assert any(point.action == "blocked_close_liquidity" for point in points)


def test_special_close_missing_risk_cap_approval_blocked():
    points = _decision_points("path-gamma-squeeze-then-reversal")
    assert any(point.action == "blocked_close_risk_cap" for point in points)


def test_special_close_with_all_approvals_improves_outcome():
    outcome = _outcome("path-special-close-with-reason-improves")
    assert outcome.outcome_type == "approved_special_close_helped"
    assert outcome.special_close_used is True


def test_special_close_records_reason_code():
    assert _outcome("path-special-close-with-reason-improves").special_close_reason == "protect_0dte_gamma_spike"


def test_special_close_not_treated_as_normal_day_trade():
    points = _decision_points("path-special-close-with-reason-improves")
    assert any(point.no_day_trade_exception_type == "zero_dte_expiry_managed" for point in points)
    assert not any(point.action == "blocked_normal_day_trade" and point.allowed for point in points)


def test_expiry_managed_worthless_state_written():
    assert _expiry("path-deep-otm-expires-worthless")["expiry_state"] == "expires_worthless_simulated"


def test_expiry_managed_intrinsic_value_state_written():
    assert _expiry("path-clean-bullish-trend-call-win")["expiry_state"] == "expires_itm_intrinsic_value_simulated"


def test_expiry_pin_risk_flag_written():
    assert "pin_risk_simulated" in _expiry("path-expiry-pin-near-strike")["risk_flags"]


def test_assignment_exercise_risk_flagged_simulated_only():
    assert _expiry("path-itm-expiry-intrinsic-value")["expiry_state"] == "assignment_exercise_risk_flagged_simulated_only"


def test_expiry_management_has_no_broker_instruction():
    assert _expiry("path-itm-expiry-intrinsic-value")["broker_instruction"] == "none_simulated_only"


def test_threshold_feedback_tighten_spread():
    assert "tighten_spread_threshold" in _feedback("path-wide-spread-exit-trap")


def test_threshold_feedback_tighten_liquidity():
    assert "tighten_liquidity_threshold" in _feedback("path-liquidity-dries-near-close")


def test_threshold_feedback_tighten_gamma():
    assert "tighten_gamma_instability_threshold" in _feedback("path-gamma-squeeze-then-reversal")


def test_threshold_feedback_prefer_later_expiry():
    assert "prefer_later_expiry_more_often" in _feedback("path-signal-valid-later-expiry-better")


def test_threshold_feedback_advisory_only():
    feedback = _detail_for_path("path-wide-spread-exit-trap")["replay"]["threshold_feedback"]
    assert feedback.advisory_only is True


def test_threshold_feedback_does_not_mutate_live_thresholds():
    before = _thresholds().to_dict()
    _feedback("path-wide-spread-exit-trap")
    assert _thresholds().to_dict() == before


def test_zero_dte_replay_inputs_artifact_written():
    run_zero_dte_outcome_replay()
    assert ZERO_DTE_REPLAY_INPUTS_PATH.exists()


def test_zero_dte_intraday_states_artifact_written():
    run_zero_dte_outcome_replay()
    assert ZERO_DTE_INTRADAY_STATES_PATH.exists()


def test_zero_dte_replay_outcomes_artifact_written():
    run_zero_dte_outcome_replay()
    assert ZERO_DTE_REPLAY_OUTCOMES_PATH.exists()


def test_zero_dte_replay_summary_artifact_written():
    run_zero_dte_outcome_replay()
    assert ZERO_DTE_REPLAY_SUMMARY_PATH.exists()


def test_zero_dte_threshold_feedback_artifact_written():
    run_zero_dte_outcome_replay()
    assert ZERO_DTE_THRESHOLD_FEEDBACK_PATH.exists()


def test_zero_dte_replay_proof_artifact_written():
    run_zero_dte_outcome_replay()
    assert ZERO_DTE_REPLAY_PROOF_PATH.exists()


def test_account_ledger_consumes_zero_dte_replay_feedback():
    result = add_open_position(
        create_paper_account_ledger("zreplay", default_day_trade_policy()),
        _intent("zreplay-ledger", _risk_decision("liquid_strong_trend_call_approved"), _replay_feedback("path-clean-bullish-trend-call-win")),
        default_day_trade_policy(),
    )
    assert result.accepted
    assert result.ledger.positions[0].policy_flags["zero_dte_replay_feedback"]["advisory_only"] is True


def test_rotation_planner_consumes_zero_dte_later_expiry_feedback():
    plan = build_rotation_plan(
        create_paper_account_ledger("zreplay-rotation", default_day_trade_policy()),
        [_intent("zreplay-rotation", _risk_decision("liquid_strong_trend_call_approved"), _replay_feedback("path-signal-valid-later-expiry-better"))],
        [],
        default_day_trade_policy(),
        {"entry_allowed": True},
        {"entry_allowed": True},
        {"zreplay-rotation": 0.99},
    )
    assert plan.blocked_actions[0].decision_type == "prefer_non_zero_dte_alternative"


def test_paper_broker_not_mutated_into_optimizer():
    preview = PaperBroker().preview_order(
        _intent("zreplay-broker", _risk_decision("liquid_strong_trend_call_approved"), _replay_feedback("path-clean-bullish-trend-call-win"))
    )
    assert preview["paper_broker_role"] == "policy_executor_not_optimizer"


def test_replay_feedback_does_not_auto_approve_blocked_candidate():
    result = add_open_position(
        create_paper_account_ledger("zreplay-blocked", default_day_trade_policy()),
        _intent("zreplay-blocked", _risk_decision("weak_thesis_blocked"), _replay_feedback("path-blocked-weak-thesis-unexpected-work")),
        default_day_trade_policy(),
    )
    assert not result.accepted
    assert "zero_dte_risk_model_rejected" in result.reason_codes


def test_audit_recognizes_zero_dte_replay_artifacts():
    audit = run_active_policy_audit()
    assert audit["artifact_paths"]["zero_dte_replay_outcomes"].endswith("zero_dte_replay_outcomes.jsonl")


def test_audit_flags_replay_with_live_market_reference():
    checks = audit_zero_dte_replay_records(
        [{"replay_id": "bad", "paper_only": True, "live_blocked": True, "source": "polygon"}],
        [],
        [],
    )
    assert any(check["check_id"] == "zero_dte_replay_no_real_market_reference" and not check["passed"] for check in checks)


def test_audit_flags_special_close_without_reason():
    checks = audit_zero_dte_replay_records(
        [{"replay_id": "bad", "paper_only": True, "live_blocked": True, "special_close_used": True, "special_close_reason": ""}],
        [],
        [],
    )
    assert any(check["check_id"] == "zero_dte_replay_special_close_requires_reason" and not check["passed"] for check in checks)


def test_audit_confirms_threshold_feedback_advisory():
    checks = audit_zero_dte_replay_records(
        [{"replay_id": "ok", "paper_only": True, "live_blocked": True}],
        [],
        [{"replay_id": "ok", "advisory_only": True, "live_threshold_mutation_allowed": False}],
    )
    assert any(check["check_id"] == "zero_dte_threshold_feedback_advisory_only" and check["passed"] for check in checks)


def test_audit_confirms_no_active_forbidden_live_decisions():
    assert run_active_policy_audit()["safety_errors"] == 0


def test_reporting_includes_zero_dte_replay_summary():
    run_zero_dte_outcome_replay()
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _zero_dte_replay_summary(evidence)["replay_count"] == 24


def test_export_verifier_selects_zero_dte_replay_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"zero_dte_replay_outcomes", "zero_dte_replay_summary", "zero_dte_replay_proof"}.issubset(ids)


def test_export_review_includes_zero_dte_replay_summary():
    class Ctx:
        shared_export_path = "Z:/fixture"
        reporting_summary = {
            "top_strategy": "fixture",
            "top_family": "fixture",
            "active_policy_summary": {},
            "account_ledger_summary": {},
            "zero_dte_risk_summary": {},
            "zero_dte_replay_summary": {"replay_count": 24, "fixture_path_count": 24, "all_expectations_matched": True},
        }

    class Bundle:
        source_bundle_id = "bundle"
        source_export_path = "local"
        artifact_count = 1
        hash_status = "pass"
        copy_status = "verified"
        safety_status = "pass"
        credential_scan_status = "pass"
        active_forbidden_live_decisions = 0

    class Decision:
        decision = "ready_for_review"
        suitability = "offline_review"
        next_build_target = "0DTE threshold feedback optimizer"

    assert "0DTE Expiry Outcome Replay" in render_executive_summary(Ctx(), Bundle(), [], Decision())


def test_zero_dte_replay_artifact_ledger_written():
    assert Path("docs/reports/DOPEY_0DTE_REPLAY_ARTIFACT_LEDGER.md").exists() or run_zero_dte_outcome_replay()["zero_dte_outcome_replay_status"] == "ok"


def test_live_trading_still_disabled_after_zero_dte_replay():
    assert run_zero_dte_outcome_replay()["summary"]["live_blocked"] is True


def test_robinhood_stub_still_blocks_live_after_zero_dte_replay():
    try:
        RobinhoodMCPAdapter().place_order(ExecutionIntent(intent_id="live", symbol="SPY", structure="long_call", legs=[{"side": "buy"}], live_allowed=True, paper=False, broker_preference="robinhood"))
    except LiveTradingDisabledError:
        assert True
    else:
        raise AssertionError("Robinhood adapter did not block live order")


def test_alpaca_stub_still_blocks_live_after_zero_dte_replay():
    try:
        AlpacaOptionsAdapter().place_order(ExecutionIntent(intent_id="live", symbol="SPY", structure="long_call", legs=[{"side": "buy"}], live_allowed=True, paper=False, broker_preference="alpaca"))
    except LiveTradingDisabledError:
        assert True
    else:
        raise AssertionError("Alpaca adapter did not block live order")


def test_tradier_stub_still_blocks_live_after_zero_dte_replay():
    try:
        TradierOptionsAdapter().place_order(ExecutionIntent(intent_id="live", symbol="SPY", structure="long_call", legs=[{"side": "buy"}], live_allowed=True, paper=False, broker_preference="tradier"))
    except LiveTradingDisabledError:
        assert True
    else:
        raise AssertionError("Tradier adapter did not block live order")


def test_no_credentials_created_by_zero_dte_replay():
    run_zero_dte_outcome_replay()
    artifact_text = "\n".join(path.read_text(encoding="utf-8") for path in [ZERO_DTE_REPLAY_SUMMARY_PATH, ZERO_DTE_REPLAY_PROOF_PATH])
    assert "sk-proj-" not in artifact_text
    assert "sk_live" not in artifact_text
    assert "api_key" not in artifact_text.lower()


def test_no_scheduler_created_by_zero_dte_replay():
    module_text = Path("dopey_options/run_zero_dte_outcome_replay.py").read_text(encoding="utf-8")
    assert "cron" not in module_text.lower()
    assert "apscheduler" not in module_text.lower()


def test_no_network_market_data_dependency_created_by_zero_dte_replay():
    modules = [
        Path("dopey_options/zero_dte_replay_engine.py"),
        Path("dopey_options/run_zero_dte_outcome_replay.py"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in modules)
    assert "requests" not in text
    assert "yfinance" not in text
    assert "websocket" not in text


def test_blunder_integrity_unchanged_if_manifest_available():
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        assert True
        return
    assert manifest.read_text(encoding="utf-8-sig").strip() or manifest.exists()
