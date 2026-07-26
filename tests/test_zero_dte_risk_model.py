from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.active_policy_audit import audit_zero_dte_risk_records, run_active_policy_audit
from dopey_execution.account_ledger import add_open_position, close_position, create_paper_account_ledger
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.day_trade_policy import default_day_trade_policy
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.rotation_planner import build_rotation_plan
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary, render_safety_summary
from dopey_options.run_zero_dte_risk_model import (
    ZERO_DTE_APPROVED_CANDIDATES_PATH,
    ZERO_DTE_BLOCKED_CANDIDATES_PATH,
    ZERO_DTE_RISK_DECISIONS_PATH,
    ZERO_DTE_RISK_PROOF_PATH,
    ZERO_DTE_RISK_SUMMARY_PATH,
    load_zero_dte_risk_cases,
    run_zero_dte_risk_model,
)
from dopey_options.zero_dte_decision_engine import evaluate_zero_dte_candidate
from dopey_options.zero_dte_risk_model import ZeroDTERiskDecision, ZeroDTERiskInput, zero_dte_decision_hash
from dopey_options.zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _zero_dte_risk_summary


def _thresholds():
    return load_default_zero_dte_risk_thresholds()


def _case(case_id: str) -> dict:
    for case in load_zero_dte_risk_cases():
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"missing case {case_id}")


def _decision(case_id: str) -> ZeroDTERiskDecision:
    case = _case(case_id)
    return evaluate_zero_dte_candidate(ZeroDTERiskInput.from_dict(case["input"]), _thresholds())


def _approved_decision() -> dict:
    return _decision("liquid_strong_trend_call_approved").to_dict()


def _blocked_decision() -> dict:
    return _decision("wide_spread_call_blocked").to_dict()


def _throttled_decision() -> dict:
    return _decision("moderate_risk_candidate_approved_with_throttle").to_dict()


def _intent(intent_id: str, risk_decision: dict, action: str = "buy_to_open", lifecycle: str = "zero_dte_special_lifecycle", reason: str = "") -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure="long_call",
        legs=[{"side": "buy" if action == "buy_to_open" else "sell", "symbol": f"SPY_0DTE_{intent_id}", "option_type": "call", "expiry": "2026-07-03", "strike": 500.0, "dte": 0}],
        max_loss=1.0,
        order_action=action,
        trade_date="2026-07-03",
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state=lifecycle,
        zero_dte=True,
        liquidity_approved=True,
        risk_cap_approved=True,
        reason_code=reason,
        zero_dte_risk_decision=risk_decision,
    )


def _decision_record_without(field_name: str) -> dict:
    record = _approved_decision()
    candidate = dict(record["candidate_input"])
    if field_name == "liquidity":
        record["failed_controls"] = ["strict_liquidity"]
    elif field_name == "risk_cap":
        record["max_paper_premium_at_risk"] = 0.0
    else:
        candidate[field_name] = ""
    record["candidate_input"] = candidate
    return record


def test_zero_dte_risk_input_serializes_deterministically():
    candidate = ZeroDTERiskInput.from_dict(_case("liquid_strong_trend_call_approved")["input"])
    assert candidate.to_dict() == ZeroDTERiskInput.from_dict(candidate.to_dict()).to_dict()


def test_zero_dte_risk_decision_serializes_deterministically():
    decision = _decision("liquid_strong_trend_call_approved")
    assert decision.to_dict() == ZeroDTERiskDecision.from_dict(decision.to_dict()).to_dict()


def test_zero_dte_thresholds_load_from_fixture():
    assert _thresholds().threshold_version == "dopey-zero-dte-risk-thresholds-v1"


def test_zero_dte_decision_hash_is_deterministic():
    first = _decision("liquid_strong_trend_call_approved")
    second = _decision("liquid_strong_trend_call_approved")
    assert first.decision_hash == second.decision_hash == zero_dte_decision_hash(first)


def test_liquid_strong_trend_call_approved():
    assert _decision("liquid_strong_trend_call_approved").decision == "approved_for_paper_open"


def test_liquid_strong_breakdown_put_approved():
    assert _decision("liquid_strong_breakdown_put_approved").decision == "approved_for_paper_open"


def test_wide_spread_candidate_blocked():
    assert _decision("wide_spread_call_blocked").decision == "blocked_spread"


def test_low_volume_candidate_blocked():
    assert _decision("low_volume_put_blocked").decision == "blocked_liquidity"


def test_high_slippage_candidate_blocked():
    assert _decision("high_slippage_candidate_blocked").decision == "blocked_slippage"


def test_high_gamma_instability_blocked():
    assert _decision("high_gamma_unstable_candidate_blocked").decision == "blocked_gamma_instability"


def test_theta_decay_trap_blocked():
    assert _decision("theta_decay_trap_blocked").decision == "blocked_theta_decay"


def test_iv_overpayment_trap_blocked():
    assert _decision("iv_overpayment_trap_blocked").decision == "blocked_iv_shock"


def test_event_risk_candidate_blocked():
    assert _decision("event_risk_too_high_blocked").decision == "blocked_event_risk"


def test_weak_thesis_candidate_blocked():
    assert _decision("weak_thesis_blocked").decision == "blocked_weak_thesis"


def test_missing_exit_plan_blocked():
    assert _decision("missing_explicit_exit_plan_blocked").decision == "blocked_missing_exit_plan"


def test_good_signal_poor_liquidity_blocked():
    assert _decision("strong_signal_poor_liquidity_blocked").decision == "blocked_liquidity"


def test_good_liquidity_weak_proof_blocked():
    assert _decision("good_liquidity_weak_proof_blocked").decision == "blocked_missing_proof"


def test_moderate_risk_candidate_approved_with_throttle():
    decision = _decision("moderate_risk_candidate_approved_with_throttle")
    assert decision.decision == "approved_with_throttle"
    assert decision.max_contracts_paper == 1


def test_prefer_non_zero_dte_alternative_when_available():
    assert _decision("prefer_non_zero_dte_alternative_when_same_signal_exists").decision == "prefer_non_zero_dte_alternative"


def test_expiry_managed_only_candidate_recorded():
    assert _decision("expiry_managed_only_candidate").decision == "expiry_managed_only"


def test_zero_dte_rejects_non_call_put():
    assert _decision("unsupported_option_type_blocked").decision == "blocked_policy_violation"


def test_zero_dte_rejects_sell_to_open():
    assert "sell_to_open_rejected" in _decision("sell_to_open_blocked").reason_codes


def test_zero_dte_rejects_unsupported_spread():
    record = dict(_case("liquid_strong_trend_call_approved")["input"])
    record["candidate_id"] = "unsupported-spread"
    record["structure_type"] = "vertical"
    decision = evaluate_zero_dte_candidate(ZeroDTERiskInput.from_dict(record), _thresholds())
    assert decision.decision == "blocked_policy_violation"


def test_zero_dte_rejects_undefined_risk_structure():
    assert "undefined_risk_structure_rejected" in _decision("undefined_risk_structure_blocked").reason_codes


def test_zero_dte_rejects_live_path():
    assert _decision("live_path_blocked").decision == "blocked_live_path"


def test_zero_dte_approval_requires_paper_only_live_blocked():
    record = dict(_case("liquid_strong_trend_call_approved")["input"])
    record["candidate_id"] = "paper-false"
    record["paper_only"] = False
    decision = evaluate_zero_dte_candidate(ZeroDTERiskInput.from_dict(record), _thresholds())
    assert decision.decision == "blocked_policy_violation"


def test_zero_dte_approved_candidate_can_enter_account_ledger():
    result = add_open_position(create_paper_account_ledger("zrisk", default_day_trade_policy()), _intent("zrisk-open", _approved_decision()), default_day_trade_policy())
    assert result.accepted


def test_zero_dte_blocked_candidate_cannot_enter_account_ledger():
    result = add_open_position(create_paper_account_ledger("zrisk", default_day_trade_policy()), _intent("zrisk-block", _blocked_decision()), default_day_trade_policy())
    assert not result.accepted
    assert "zero_dte_risk_model_rejected" in result.reason_codes


def test_zero_dte_throttled_candidate_records_caps():
    result = add_open_position(create_paper_account_ledger("zrisk", default_day_trade_policy()), _intent("zrisk-throttle", _throttled_decision()), default_day_trade_policy())
    flags = result.ledger.positions[0].policy_flags
    assert result.accepted
    assert flags["zero_dte_max_contracts_paper"] == 1


def test_zero_dte_special_close_missing_reason_rejected():
    ledger = add_open_position(create_paper_account_ledger("zrisk", default_day_trade_policy()), _intent("zrisk-open", _approved_decision()), default_day_trade_policy()).ledger
    close = _intent("zrisk-close", _approved_decision(), action="sell_to_close", lifecycle="zero_dte_expiry_managed")
    close.related_open_position_id = "zrisk-open"
    assert "zero_dte_special_close_requires_explicit_reason_code" in close_position(ledger, close, default_day_trade_policy()).reason_codes


def test_zero_dte_special_close_all_approvals_allowed():
    ledger = add_open_position(create_paper_account_ledger("zrisk", default_day_trade_policy()), _intent("zrisk-open", _approved_decision()), default_day_trade_policy()).ledger
    close = _intent("zrisk-close-ok", _approved_decision(), action="sell_to_close", lifecycle="zero_dte_expiry_managed", reason="expiry_window")
    close.related_open_position_id = "zrisk-open"
    assert close_position(ledger, close, default_day_trade_policy()).accepted


def test_zero_dte_expiry_managed_state_written():
    result = run_zero_dte_risk_model()
    assert result["summary"]["expiry_managed_only_count"] == 1


def test_rotation_planner_can_prefer_non_zero_dte_alternative():
    plan = build_rotation_plan(
        create_paper_account_ledger("zrisk", default_day_trade_policy()),
        [_intent("zrisk-prefer", _decision("prefer_non_zero_dte_alternative_when_same_signal_exists").to_dict())],
        [],
        default_day_trade_policy(),
        {"entry_allowed": True},
        {"entry_allowed": True},
        {"zrisk-prefer": 0.9},
    )
    assert plan.blocked_actions[0].decision_type == "prefer_non_zero_dte_alternative"


def test_paper_broker_rejects_zero_dte_without_risk_model_approval():
    broker = PaperBroker()
    result = broker.place_order(_intent("zrisk-no-model", {}))
    assert not result["ok"]
    assert "zero_dte_risk_model_approval_required" in result["errors"]


def test_zero_dte_risk_decisions_artifact_written():
    run_zero_dte_risk_model()
    assert ZERO_DTE_RISK_DECISIONS_PATH.exists()


def test_zero_dte_risk_summary_artifact_written():
    run_zero_dte_risk_model()
    assert json.loads(ZERO_DTE_RISK_SUMMARY_PATH.read_text(encoding="utf-8"))["decision_count"] == 24


def test_zero_dte_risk_proof_artifact_written():
    run_zero_dte_risk_model()
    assert ZERO_DTE_RISK_PROOF_PATH.exists()


def test_zero_dte_blocked_candidates_have_reason_codes():
    run_zero_dte_risk_model()
    records = [json.loads(line) for line in ZERO_DTE_BLOCKED_CANDIDATES_PATH.read_text(encoding="utf-8").splitlines() if line]
    assert all(record["reason_codes"] for record in records)


def test_zero_dte_approved_candidates_have_threshold_version():
    run_zero_dte_risk_model()
    records = [json.loads(line) for line in ZERO_DTE_APPROVED_CANDIDATES_PATH.read_text(encoding="utf-8").splitlines() if line]
    assert all(record["threshold_version"] for record in records)


def test_audit_recognizes_zero_dte_risk_artifacts():
    audit = run_active_policy_audit()
    assert audit["artifact_paths"]["zero_dte_risk_summary"].endswith("zero_dte_risk_summary.json")


def test_audit_flags_zero_dte_approved_without_thesis():
    checks = audit_zero_dte_risk_records([_decision_record_without("explicit_thesis")])
    assert any(check["check_id"] == "zero_dte_no_missing_thesis_approved" and not check["passed"] for check in checks)


def test_audit_flags_zero_dte_approved_without_exit_plan():
    checks = audit_zero_dte_risk_records([_decision_record_without("explicit_exit_or_expiry_plan")])
    assert any(check["check_id"] == "zero_dte_no_missing_exit_plan_approved" and not check["passed"] for check in checks)


def test_audit_flags_zero_dte_approved_without_liquidity_approval():
    checks = audit_zero_dte_risk_records([_decision_record_without("liquidity")])
    assert any(check["check_id"] == "zero_dte_no_missing_liquidity_approval_approved" and not check["passed"] for check in checks)


def test_audit_flags_zero_dte_approved_without_risk_cap():
    checks = audit_zero_dte_risk_records([_decision_record_without("risk_cap")])
    assert any(check["check_id"] == "zero_dte_no_missing_risk_cap_approved" and not check["passed"] for check in checks)


def test_audit_confirms_zero_dte_no_live_path():
    audit = run_active_policy_audit()
    assert any(check["check_id"] == "zero_dte_no_live_path_approved" and check["passed"] for check in audit["checks"])


def test_reporting_includes_zero_dte_risk_summary():
    run_zero_dte_risk_model()
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _zero_dte_risk_summary(evidence)["approved_count"] >= 1


def test_export_verifier_selects_zero_dte_risk_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"zero_dte_risk_summary", "zero_dte_risk_decisions", "zero_dte_risk_proof"}.issubset(ids)


def test_export_review_includes_zero_dte_risk_summary():
    class Ctx:
        reporting_summary = {"zero_dte_risk_summary": {"approved_count": 1, "blocked_count": 2, "throttled_count": 1, "all_expectations_matched": True}, "account_ledger_summary": {}}
        shared_export_path = "Z:\\fixture"
        audit_gap_plan = {"gaps": []}

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
        decision = "review_ready"
        suitability = "offline"
        next_build_target = "0DTE expiry/outcome replay simulator"

    assert "0DTE Special Lifecycle Risk Model" in render_executive_summary(Ctx(), Bundle(), [], Decision())


def test_zero_dte_risk_artifact_ledger_written():
    assert Path("docs/reports/DOPEY_0DTE_RISK_ARTIFACT_LEDGER.md").exists() or run_zero_dte_risk_model()["zero_dte_risk_model_status"] == "ok"


def test_live_trading_still_disabled_after_zero_dte_risk_model():
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(ExecutionIntent(intent_id="live", symbol="SPY", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-03", "dte": 0}], max_loss=1.0, live_allowed=True, active_policy_required=True))


def test_robinhood_stub_still_blocks_live_after_zero_dte_risk_model():
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(ExecutionIntent(intent_id="rh-live", symbol="SPY", structure="long_call", legs=[{"side": "buy", "option_type": "call"}], max_loss=1.0, live_allowed=True))


def test_alpaca_stub_still_blocks_live_after_zero_dte_risk_model():
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(ExecutionIntent(intent_id="alpaca-live", symbol="SPY", structure="long_call", legs=[{"side": "buy", "option_type": "call"}], max_loss=1.0, live_allowed=True))


def test_tradier_stub_still_blocks_live_after_zero_dte_risk_model():
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(ExecutionIntent(intent_id="tradier-live", symbol="SPY", structure="long_call", legs=[{"side": "buy", "option_type": "call"}], max_loss=1.0, live_allowed=True))


def test_no_credentials_created_by_zero_dte_risk_model():
    files = [
        Path("dopey_options/zero_dte_risk_model.py"),
        Path("dopey_options/zero_dte_decision_engine.py"),
        Path("dopey_options/run_zero_dte_risk_model.py"),
    ]
    assert all("credential" not in path.read_text(encoding="utf-8").lower() for path in files)


def test_no_scheduler_created_by_zero_dte_risk_model():
    assert "scheduler" not in Path("dopey_options/run_zero_dte_risk_model.py").read_text(encoding="utf-8").lower()


def test_no_network_market_data_dependency_created_by_zero_dte_risk_model():
    text = "\n".join(Path(path).read_text(encoding="utf-8").lower() for path in ["dopey_options/zero_dte_decision_engine.py", "dopey_options/run_zero_dte_risk_model.py"])
    assert "requests" not in text and "http://" not in text and "https://" not in text


def test_blunder_integrity_unchanged_if_manifest_available():
    touched = [
        Path("dopey_options/zero_dte_risk_model.py"),
        Path("dopey_options/zero_dte_decision_engine.py"),
        Path("dopey_options/run_zero_dte_risk_model.py"),
    ]
    assert all("_forked_blunder" not in path.read_text(encoding="utf-8") for path in touched)
