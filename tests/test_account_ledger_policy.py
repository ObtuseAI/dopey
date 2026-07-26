from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.active_policy_audit import audit_account_ledger_record, run_active_policy_audit
from dopey_execution.account_ledger import (
    add_open_position,
    close_position,
    close_eligible_positions,
    create_paper_account_ledger,
    same_day_blocked_positions,
)
from dopey_execution.account_models import ledger_hash
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.day_trade_policy import default_day_trade_policy
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.run_account_ledger_rotation_planner import run_account_ledger_rotation_planner
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _account_ledger_summary
from dopey_validation.full_suite_stabilizer import TEST_SHARD_PLAN_PATH, run_full_suite_stabilizer


def _policy():
    return default_day_trade_policy()


def _ledger():
    return create_paper_account_ledger("test-account", _policy())


def _intent(intent_id: str, structure: str, side: str, action: str, trade_date: str, option_type: str, expiry: str = "2026-07-17", live: bool = False) -> ExecutionIntent:
    strike = 500.0 if option_type == "call" else 495.0
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure=structure,
        legs=[{"side": side, "symbol": f"SPY_{option_type}_{strike}_{expiry}", "option_type": option_type, "expiry": expiry, "strike": strike, "dte": 14}],
        max_loss=1.0,
        target_profit=2.0,
        order_action=action,
        trade_date=trade_date,
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state="normal_hold",
        live_allowed=live,
    )


def test_paper_account_ledger_serializes_deterministically():
    ledger = _ledger()
    assert ledger.to_dict()["ledger_hash"] == ledger_hash(ledger)


def test_open_long_call_creates_position():
    result = add_open_position(_ledger(), _intent("call-open", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy())
    assert result.accepted
    assert result.ledger.positions[0].option_type == "call"


def test_open_long_put_creates_position():
    result = add_open_position(_ledger(), _intent("put-open", "long_put", "buy", "buy_to_open", "2026-07-03", "put"), _policy())
    assert result.accepted
    assert result.ledger.positions[0].option_type == "put"


def test_position_close_eligible_date_set_to_next_trading_day():
    result = add_open_position(_ledger(), _intent("friday-open", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy())
    assert result.ledger.positions[0].close_eligible_date == "2026-07-06"


def test_ledger_rejects_non_call_put_option_type():
    intent = _intent("bad-type", "single", "buy", "buy_to_open", "2026-07-03", "call")
    intent.legs[0]["option_type"] = "future"
    result = add_open_position(_ledger(), intent, _policy())
    assert "ledger_rejects_non_call_put_option_type" in result.reason_codes


def test_ledger_rejects_sell_to_open():
    result = add_open_position(_ledger(), _intent("sell-open", "long_call", "sell", "sell_to_open", "2026-07-03", "call"), _policy())
    assert not result.accepted
    assert "sell_to_open_rejected" in result.reason_codes


def test_ledger_hash_is_deterministic():
    ledger_one = add_open_position(_ledger(), _intent("hash-call", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy()).ledger
    ledger_two = add_open_position(_ledger(), _intent("hash-call", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy()).ledger
    assert ledger_one.ledger_hash == ledger_two.ledger_hash


def test_same_day_close_rejected_for_call():
    ledger = add_open_position(_ledger(), _intent("call", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy()).ledger
    close = _intent("call-close", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "call"
    assert close_position(ledger, close, _policy()).decision == "blocked_same_day_round_trip"


def test_same_day_close_rejected_for_put():
    ledger = add_open_position(_ledger(), _intent("put", "long_put", "buy", "buy_to_open", "2026-07-03", "put"), _policy()).ledger
    close = _intent("put-close", "long_put", "sell", "sell_to_close", "2026-07-03", "put")
    close.related_open_position_id = "put"
    assert "same_day_round_trip_rejected" in close_position(ledger, close, _policy()).reason_codes


def test_next_day_close_allowed_for_call():
    ledger = add_open_position(_ledger(), _intent("call-y", "long_call", "buy", "buy_to_open", "2026-07-02", "call"), _policy()).ledger
    close = _intent("call-y-close", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "call-y"
    assert close_position(ledger, close, _policy()).accepted


def test_next_day_close_allowed_for_put():
    ledger = add_open_position(_ledger(), _intent("put-y", "long_put", "buy", "buy_to_open", "2026-07-02", "put"), _policy()).ledger
    close = _intent("put-y-close", "long_put", "sell", "sell_to_close", "2026-07-03", "put")
    close.related_open_position_id = "put-y"
    assert close_position(ledger, close, _policy()).accepted


def test_close_without_open_position_rejected():
    close = _intent("missing-close", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "missing"
    assert close_position(_ledger(), close, _policy()).reason_codes == ["close_without_open_position_rejected"]


def test_day_trade_event_logged_when_same_day_close_attempted():
    ledger = add_open_position(_ledger(), _intent("event-call", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy()).ledger
    close = _intent("event-close", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "event-call"
    result = close_position(ledger, close, _policy())
    assert result.ledger.day_trade_events[-1].rejection_reason == "same_day_round_trip_rejected"


def test_same_day_block_does_not_block_new_compliant_entry():
    ledger = add_open_position(_ledger(), _intent("blocked-call", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy()).ledger
    assert same_day_blocked_positions(ledger, "2026-07-03")
    assert add_open_position(ledger, _intent("new-put", "long_put", "buy", "buy_to_open", "2026-07-03", "put"), _policy()).accepted


def test_audit_recognizes_account_ledger_artifacts():
    run_account_ledger_rotation_planner()
    audit = run_active_policy_audit()
    assert audit["artifact_paths"]["paper_account_ledger"].endswith("paper_account_ledger.json")


def test_audit_recognizes_rotation_planner_artifacts():
    audit = run_active_policy_audit()
    assert audit["artifact_paths"]["rotation_planner_proof"].endswith("rotation_planner_proof.jsonl")


def test_audit_flags_same_day_normal_close_allowed():
    bad = {
        "positions": [{"option_type": "call"}],
        "orders": [],
        "day_trade_events": [{"same_trading_day": True, "allowed": True, "zero_dte_special_lifecycle": False}],
    }
    checks = audit_account_ledger_record(bad)
    assert any(check["check_id"] == "account_ledger_no_same_day_normal_close_allowed" and not check["passed"] for check in checks)


def test_audit_confirms_zero_dte_special_lifecycle_tracking():
    audit = run_active_policy_audit()
    assert any(check["check_id"] == "account_ledger_zero_dte_special_lifecycle_tracked" and check["passed"] for check in audit["checks"])


def test_audit_confirms_active_forbidden_live_decisions_zero():
    assert run_active_policy_audit()["safety_errors"] == 0


def test_reporting_includes_account_ledger_summary():
    run_account_ledger_rotation_planner()
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert "open_positions_count" in _account_ledger_summary(evidence)


def test_reporting_includes_rotation_planner_summary():
    run_account_ledger_rotation_planner()
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _account_ledger_summary(evidence)["rotation_decisions_count"] >= 1


def test_export_verifier_selects_account_ledger_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"paper_account_ledger", "rotation_plan", "rotation_planner_proof"}.issubset(ids)


def test_export_review_includes_no_day_trade_summary():
    from dopey_export_review.review_packet import render_safety_summary

    class Ctx:
        safety_state = {"mode": "RESEARCH", "live_trading_enabled": False, "funded_broker_connections_enabled": False, "allow_unofficial_robinhood_api": False}
        export_safety_scan = {"active_forbidden_live_decisions": 0, "credential_findings": 0}

    assert "account_ledger_no_day_trade_enforcement" in render_safety_summary(Ctx())


def test_account_ledger_artifact_ledger_written():
    assert Path("docs/reports/DOPEY_ACCOUNT_LEDGER_ARTIFACT_LEDGER.md").exists() or run_account_ledger_rotation_planner()["account_ledger_rotation_planner_status"] == "ok"


def test_test_shard_plan_written():
    run_full_suite_stabilizer(per_file_timeout_seconds=1, max_files=1, full_timeout_seconds=1)
    assert TEST_SHARD_PLAN_PATH.exists()


def test_test_shard_plan_includes_slow_export_verifier_file():
    run_full_suite_stabilizer(per_file_timeout_seconds=1, max_files=1, full_timeout_seconds=1)
    plan = json.loads(TEST_SHARD_PLAN_PATH.read_text(encoding="utf-8"))
    assert "tests/test_artifact_compaction_export_verifier.py" in plan["slow_test_allowlist"]


def test_stabilizer_does_not_mark_timeout_as_pass():
    summary = run_full_suite_stabilizer(per_file_timeout_seconds=1, max_files=1, full_timeout_seconds=1)
    assert summary["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_account_ledger_bundle():
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_intent("live", "long_call", "buy", "buy_to_open", "2026-07-03", "call", live=True))


def test_robinhood_stub_still_blocks_live_after_account_ledger_bundle():
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_intent("rh-live", "long_call", "buy", "buy_to_open", "2026-07-03", "call", live=True))


def test_alpaca_stub_still_blocks_live_after_account_ledger_bundle():
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_intent("alpaca-live", "long_call", "buy", "buy_to_open", "2026-07-03", "call", live=True))


def test_tradier_stub_still_blocks_live_after_account_ledger_bundle():
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_intent("tradier-live", "long_call", "buy", "buy_to_open", "2026-07-03", "call", live=True))


def test_no_credentials_created_by_account_ledger_bundle():
    new_modules = ["dopey_execution/account_ledger.py", "dopey_execution/rotation_planner.py"]
    assert all("credential" not in Path(path).read_text(encoding="utf-8").lower() for path in new_modules)


def test_no_scheduler_created_by_account_ledger_bundle():
    assert "scheduler" not in Path("dopey_execution/run_account_ledger_rotation_planner.py").read_text(encoding="utf-8").lower()


def test_no_network_market_data_dependency_created_by_account_ledger_bundle():
    text = Path("dopey_execution/rotation_planner.py").read_text(encoding="utf-8").lower()
    assert "requests" not in text and "http" not in text


def test_blunder_integrity_unchanged_if_manifest_available():
    touched = [
        Path("dopey_execution/account_ledger.py"),
        Path("dopey_execution/rotation_planner.py"),
        Path("dopey_execution/run_account_ledger_rotation_planner.py"),
    ]
    assert all("_forked_blunder" not in path.read_text(encoding="utf-8") for path in touched)
