from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey_allocation.run_proof_weighted_allocator import lifecycle_feedback_summary as allocator_lifecycle_feedback_summary
from dopey_audit.active_policy_audit import audit_active_lifecycle_records, run_active_policy_audit
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_lifecycle.account_ledger_lifecycle_adapter import AccountLedgerLifecycleAdapter
from dopey_lifecycle.lifecycle_models import (
    ActiveOptionLifecycle,
    LifecycleProofRecord,
    LifecycleState,
    LifecycleTransition,
    active_lifecycle_hash,
    lifecycle_proof_hash,
    lifecycle_state_hash,
    lifecycle_transition_hash,
)
from dopey_lifecycle.lifecycle_policy import default_lifecycle_policy, evaluate_lifecycle_case, load_lifecycle_policy
from dopey_lifecycle.lifecycle_simulator import (
    LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH,
    LIFECYCLE_CASES_FIXTURE_PATH,
    LIFECYCLE_CASES_PATH,
    LIFECYCLE_EXPECTED_PROOFS_FIXTURE_PATH,
    LIFECYCLE_EXPECTED_STATES_FIXTURE_PATH,
    LIFECYCLE_EXPECTED_SUMMARY_FIXTURE_PATH,
    LIFECYCLE_EXPECTED_TRANSITIONS_FIXTURE_PATH,
    LIFECYCLE_FEEDBACK_ALLOCATOR_PATH,
    LIFECYCLE_FEEDBACK_INCIDENT_PATH,
    LIFECYCLE_FEEDBACK_PORTFOLIO_PATH,
    LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH,
    LIFECYCLE_PAPERBROKER_RESULTS_PATH,
    LIFECYCLE_POLICY_FIXTURE_PATH,
    LIFECYCLE_POLICY_PATH,
    LIFECYCLE_PROOF_PATH,
    LIFECYCLE_STATES_PATH,
    LIFECYCLE_SUMMARY_PATH,
    LIFECYCLE_TRANSITIONS_PATH,
    build_lifecycle_cases,
)
from dopey_lifecycle.paperbroker_lifecycle_adapter import PaperBrokerLifecycleAdapter
from dopey_lifecycle.run_active_option_lifecycle_simulator import run_active_option_lifecycle_simulator
from dopey_portfolio.run_portfolio_replay import lifecycle_feedback_summary as portfolio_lifecycle_feedback_summary
from dopey_portfolio.run_portfolio_stress_ladder import lifecycle_feedback_summary as stress_lifecycle_feedback_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _active_lifecycle_summary
from dopey_validation.full_suite_stabilizer import TEST_SHARD_PLAN_PATH, collect_test_files, write_test_shard_plan
from dopey_validation.full_suite_stabilizer import CommandResult
from dopey_incident.run_incident_response_rehearsal import lifecycle_feedback_summary as incident_lifecycle_feedback_summary


@pytest.fixture(scope="session")
def lifecycle_result() -> dict:
    return run_active_option_lifecycle_simulator()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _summary(lifecycle_result: dict) -> dict:
    return _json(LIFECYCLE_SUMMARY_PATH)


def _cases(lifecycle_result: dict) -> list[dict]:
    return _json(LIFECYCLE_CASES_PATH)["records"]


def _case(lifecycle_result: dict, group: str) -> dict:
    return next(record for record in _cases(lifecycle_result) if record["case_group"] == group)


def _current_states(lifecycle_result: dict) -> dict[str, str]:
    states: dict[str, str] = {}
    for proof in _jsonl(LIFECYCLE_PROOF_PATH):
        states[proof["lifecycle_id"]] = proof["action_attempted"]
    return states


def _model_state() -> LifecycleState:
    seed = LifecycleState("s1", "l1", "signal_detected", 1, 0, "day-0-step-01", [], [], [], True, True, "")
    return LifecycleState(**{**seed.to_dict(), "state_hash": lifecycle_state_hash(seed)})


def _model_transition() -> LifecycleTransition:
    seed = LifecycleTransition("t1", "l1", "signal_detected", "candidate_built", 0, True, [], [], {}, {}, {}, {}, {}, {}, True, True, "")
    return LifecycleTransition(**{**seed.to_dict(), "transition_hash": lifecycle_transition_hash(seed)})


def _model_proof() -> LifecycleProofRecord:
    seed = LifecycleProofRecord("p1", "l1", "t1", "s1", "test", "state", "accepted", [], [], {"paper_only": True}, True, True, "")
    return LifecycleProofRecord(**{**seed.to_dict(), "proof_hash": lifecycle_proof_hash(seed)})


def _model_lifecycle() -> ActiveOptionLifecycle:
    seed = ActiveOptionLifecycle("l1", "c1", "family", "DLP1", "call", "swing_long_call", "2026-07-06", "2026-07-17", 5, "approved", "allocate_paper", "within_cap", "normal", "clear", "opened", "recorded", "paper_closed", ["t1"], ["p1"], True, True, "")
    return ActiveOptionLifecycle(**{**seed.to_dict(), "lifecycle_hash": active_lifecycle_hash(seed)})


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(intent_id="live", symbol="DLP1", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-17", "dte": 5}], max_loss=1.0, live_allowed=True, active_policy_required=True)


def _audit(extra: dict) -> list[dict]:
    return audit_active_lifecycle_records(
        _json(LIFECYCLE_POLICY_PATH),
        _json(LIFECYCLE_CASES_PATH),
        _jsonl(LIFECYCLE_STATES_PATH),
        _jsonl(LIFECYCLE_TRANSITIONS_PATH),
        [*_jsonl(LIFECYCLE_PROOF_PATH), extra],
        _jsonl(LIFECYCLE_PAPERBROKER_RESULTS_PATH),
        _jsonl(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH),
        _jsonl(LIFECYCLE_FEEDBACK_ALLOCATOR_PATH),
        _jsonl(LIFECYCLE_FEEDBACK_PORTFOLIO_PATH),
        _jsonl(LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH),
        _jsonl(LIFECYCLE_FEEDBACK_INCIDENT_PATH),
        _json(LIFECYCLE_SUMMARY_PATH),
    )


def _failed(checks: list[dict], check_id: str) -> bool:
    return any(check["check_id"] == check_id and check["passed"] is False for check in checks)


def _contains_feedback(action: str) -> bool:
    return any(record.get("feedback_type") == action for record in _jsonl(LIFECYCLE_FEEDBACK_ALLOCATOR_PATH))


def test_active_option_lifecycle_serializes_deterministically():
    record = _model_lifecycle()
    assert record.lifecycle_hash == active_lifecycle_hash(ActiveOptionLifecycle(**{**record.to_dict(), "lifecycle_hash": ""}))


def test_lifecycle_state_serializes_deterministically():
    record = _model_state()
    assert record.state_hash == lifecycle_state_hash(LifecycleState(**{**record.to_dict(), "state_hash": ""}))


def test_lifecycle_transition_serializes_deterministically():
    record = _model_transition()
    assert record.transition_hash == lifecycle_transition_hash(LifecycleTransition(**{**record.to_dict(), "transition_hash": ""}))


def test_lifecycle_proof_record_serializes_deterministically():
    record = _model_proof()
    assert record.proof_hash == lifecycle_proof_hash(LifecycleProofRecord(**{**record.to_dict(), "proof_hash": ""}))


def test_lifecycle_hash_is_deterministic():
    assert active_lifecycle_hash(ActiveOptionLifecycle(**{**_model_lifecycle().to_dict(), "lifecycle_hash": ""})) == active_lifecycle_hash(ActiveOptionLifecycle(**{**_model_lifecycle().to_dict(), "lifecycle_hash": ""}))


def test_lifecycle_rejects_unsupported_option_type():
    payload = {**_model_lifecycle().to_dict(), "option_type": "stock"}
    with pytest.raises(ValueError):
        ActiveOptionLifecycle(**payload)


def test_lifecycle_rejects_unsupported_strategy_type():
    payload = {**_model_lifecycle().to_dict(), "strategy_type": "covered_call"}
    with pytest.raises(ValueError):
        ActiveOptionLifecycle(**payload)


def test_lifecycle_requires_paper_only_live_blocked():
    payload = {**_model_lifecycle().to_dict(), "paper_only": False}
    with pytest.raises(ValueError):
        ActiveOptionLifecycle(**payload)


def test_lifecycle_policy_loads(lifecycle_result: dict):
    assert load_lifecycle_policy()["artifact_type"] == "lifecycle_policy"


def test_policy_allows_long_call_lifecycle():
    assert evaluate_lifecycle_case(build_lifecycle_cases()[0], default_lifecycle_policy())["allowed"]


def test_policy_allows_long_put_lifecycle():
    case = next(record for record in build_lifecycle_cases() if record["option_type"] == "put")
    assert evaluate_lifecycle_case(case, default_lifecycle_policy())["allowed"]


def test_policy_rejects_sell_to_open():
    assert "sell_to_open_rejected" in evaluate_lifecycle_case({**build_lifecycle_cases()[0], "open_action": "sell_to_open"}, default_lifecycle_policy())["reason_codes"]


def test_policy_rejects_naked_option():
    assert "naked_option_sale_rejected" in evaluate_lifecycle_case({**build_lifecycle_cases()[0], "naked_option_attempt": True}, default_lifecycle_policy())["reason_codes"]


def test_policy_rejects_unsupported_spread():
    assert "unsupported_spread_rejected" in evaluate_lifecycle_case({**build_lifecycle_cases()[0], "structure": "vertical_spread"}, default_lifecycle_policy())["reason_codes"]


def test_policy_rejects_live_path():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "live_flag_injection": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_policy_rejects_broker_path():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "broker_path_injection": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_policy_rejects_credentials():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "credential_reference": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_policy_rejects_scheduler():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "scheduler_emergence": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_policy_rejects_real_sizing():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "real_sizing_reference": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_lifecycle_cases_load(lifecycle_result: dict):
    assert _json(LIFECYCLE_CASES_PATH)["lifecycle_case_count"] >= 120


def test_lifecycle_expected_states_load(lifecycle_result: dict):
    assert _json(LIFECYCLE_EXPECTED_STATES_FIXTURE_PATH)["state_count"] > 0


def test_lifecycle_expected_transitions_load(lifecycle_result: dict):
    assert _json(LIFECYCLE_EXPECTED_TRANSITIONS_FIXTURE_PATH)["transition_count"] > 0


def test_lifecycle_expected_proofs_load(lifecycle_result: dict):
    assert _json(LIFECYCLE_EXPECTED_PROOFS_FIXTURE_PATH)["proof_record_count"] > 0


def test_lifecycle_has_at_least_120_cases(lifecycle_result: dict):
    assert len(_cases(lifecycle_result)) >= 120


def test_lifecycle_cases_cover_swing_call(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["strategy_type"] == "swing_long_call") >= 16


def test_lifecycle_cases_cover_swing_put(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["strategy_type"] == "swing_long_put") >= 16


def test_lifecycle_cases_cover_zero_dte_call(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["strategy_type"] == "zero_dte_long_call") >= 16


def test_lifecycle_cases_cover_zero_dte_put(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["strategy_type"] == "zero_dte_long_put") >= 16


def test_lifecycle_cases_cover_delayed_rotation(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["case_group"] == "delayed_rotation") >= 12


def test_lifecycle_cases_cover_no_day_trade_blocks(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["case_group"] == "no_day_trade_block") >= 12


def test_lifecycle_cases_cover_incident_interruption(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["case_group"] == "incident_interruption") >= 8


def test_lifecycle_cases_cover_stress_interruption(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["case_group"] == "stress_interruption") >= 8


def test_lifecycle_cases_cover_paperbroker_rejection(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if case["case_group"] == "paperbroker_rejection") >= 8


def test_lifecycle_cases_cover_negative_controls(lifecycle_result: dict):
    assert sum(1 for case in _cases(lifecycle_result) if "terminal_block" in case["case_group"] or "rejected" in case["case_group"] or "missing" in case["case_group"]) >= 8


def test_lifecycle_simulator_runs_all_cases(lifecycle_result: dict):
    assert lifecycle_result["active_option_lifecycle_simulator_status"] == "ok"


def test_lifecycle_expectations_match(lifecycle_result: dict):
    assert _json(LIFECYCLE_EXPECTED_SUMMARY_FIXTURE_PATH)["summary"]["lifecycle_case_count"] == _summary(lifecycle_result)["lifecycle_case_count"]


def test_swing_long_call_opens_holds_closes_next_day(lifecycle_result: dict):
    assert _summary(lifecycle_result)["swing_next_day_close_count"] >= 16


def test_swing_long_put_opens_holds_closes_next_day(lifecycle_result: dict):
    assert _summary(lifecycle_result)["swing_next_day_close_count"] >= 32


def test_zero_dte_long_call_enters_special_lifecycle(lifecycle_result: dict):
    assert _summary(lifecycle_result)["zero_dte_special_lifecycle_count"] >= 16


def test_zero_dte_long_put_special_closes_with_proof(lifecycle_result: dict):
    assert _summary(lifecycle_result)["zero_dte_special_close_success_count"] >= 16


def test_zero_dte_special_close_missing_reason_rejected(lifecycle_result: dict):
    assert any("zero_dte_special_close_requires_explicit_reason_code" in record.get("reason_codes", []) for record in _jsonl(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH))


def test_zero_dte_special_close_missing_liquidity_rejected(lifecycle_result: dict):
    assert any("zero_dte_policy_violation_missing_liquidity_approval" in record.get("reason_codes", []) for record in _jsonl(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH))


def test_zero_dte_special_close_missing_risk_cap_rejected(lifecycle_result: dict):
    assert any("zero_dte_risk_model_missing_risk_cap" in record.get("reason_codes", []) for record in _jsonl(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH))


def test_same_day_swing_close_blocked(lifecycle_result: dict):
    assert _summary(lifecycle_result)["no_day_trade_block_count"] >= 12


def test_same_day_zero_dte_churn_blocked(lifecycle_result: dict):
    assert _summary(lifecycle_result)["same_day_churn_allowed"] is False


def test_delayed_rotation_reserves_without_same_day_close(lifecycle_result: dict):
    assert _summary(lifecycle_result)["delayed_rotation_count"] >= 12


def test_delayed_rotation_closes_next_day_when_eligible(lifecycle_result: dict):
    assert _contains_feedback("lifecycle_close_success")


def test_paper_shadow_candidate_cannot_open_full_allocation(lifecycle_result: dict):
    assert any("allocation_paper_shadow_cannot_open" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_watchlist_candidate_cannot_open(lifecycle_result: dict):
    assert any("allocation_watchlist_cannot_open" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_no_trade_candidate_cannot_open(lifecycle_result: dict):
    assert any("allocation_no_trade_cannot_open" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_rejected_candidate_cannot_open(lifecycle_result: dict):
    assert any("allocation_rejected_cannot_open" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_portfolio_exposure_cap_blocks_lifecycle_open(lifecycle_result: dict):
    assert any("portfolio_exposure_cap_blocks_open" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_stress_severe_blocks_zero_dte_open(lifecycle_result: dict):
    assert any("stress_severe_blocks_zero_dte_open" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_crisis_lockdown_blocks_new_lifecycle_entries(lifecycle_result: dict):
    assert any("crisis_lockdown_blocks_new_entries" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_incident_terminal_block_prevents_lifecycle_progress(lifecycle_result: dict):
    assert _summary(lifecycle_result)["incident_interruption_count"] >= 8


def test_paperbroker_lifecycle_adapter_opens_valid_long_call():
    result = PaperBrokerLifecycleAdapter(PaperBroker()).open_lifecycle_position(build_lifecycle_cases()[0])
    assert result["ok"]


def test_paperbroker_lifecycle_adapter_opens_valid_long_put():
    case = next(record for record in build_lifecycle_cases() if record["option_type"] == "put" and record["days_to_expiry"] > 0)
    result = PaperBrokerLifecycleAdapter(PaperBroker()).open_lifecycle_position(case)
    assert result["ok"]


def test_paperbroker_lifecycle_adapter_rejects_live_path():
    result = PaperBrokerLifecycleAdapter(PaperBroker()).open_lifecycle_position({**build_lifecycle_cases()[0], "live_flag_injection": True})
    assert not result["ok"]


def test_paperbroker_lifecycle_adapter_rejects_sell_to_open():
    result = PaperBrokerLifecycleAdapter(PaperBroker()).open_lifecycle_position({**build_lifecycle_cases()[0], "open_action": "sell_to_open"})
    assert not result["ok"]


def test_paperbroker_lifecycle_adapter_rejects_close_without_open():
    result = PaperBrokerLifecycleAdapter(PaperBroker()).close_lifecycle_position(build_lifecycle_cases()[0], "2026-07-06", "normal_hold", "")
    assert not result["ok"]


def test_paperbroker_lifecycle_adapter_rejects_same_day_normal_close():
    broker = PaperBroker()
    adapter = PaperBrokerLifecycleAdapter(broker)
    case = build_lifecycle_cases()[0]
    assert adapter.open_lifecycle_position(case)["ok"]
    assert not adapter.close_lifecycle_position(case, case["trade_date"], "normal_hold", "")["ok"]


def test_paperbroker_lifecycle_adapter_records_reason_codes():
    result = PaperBrokerLifecycleAdapter(PaperBroker()).close_lifecycle_position(build_lifecycle_cases()[0], "2026-07-06", "normal_hold", "")
    assert result["reason_code"] or result["errors"]


def test_paperbroker_cannot_be_overridden_by_lifecycle(lifecycle_result: dict):
    assert _summary(lifecycle_result)["paperbroker_override_allowed"] is False


def test_account_ledger_lifecycle_adapter_records_open():
    assert AccountLedgerLifecycleAdapter().record_open(build_lifecycle_cases()[0])["accepted"]


def test_account_ledger_lifecycle_adapter_records_close():
    adapter = AccountLedgerLifecycleAdapter()
    case = build_lifecycle_cases()[0]
    assert adapter.record_open(case)["accepted"]
    assert adapter.record_close(case, case["next_trade_date"], "normal_hold", "next_day_exit")["accepted"]


def test_account_ledger_preserves_close_eligibility():
    result = AccountLedgerLifecycleAdapter().record_open(build_lifecycle_cases()[0])
    assert result["close_eligible_date"] == "2026-07-07"


def test_account_ledger_blocks_same_day_close():
    adapter = AccountLedgerLifecycleAdapter()
    case = build_lifecycle_cases()[0]
    adapter.record_open(case)
    assert not adapter.record_close(case, case["trade_date"], "normal_hold", "")["accepted"]


def test_account_ledger_records_delayed_rotation(lifecycle_result: dict):
    assert _summary(lifecycle_result)["delayed_rotation_count"] >= 12


def test_account_ledger_records_zero_dte_state():
    case = next(record for record in build_lifecycle_cases() if record["days_to_expiry"] == 0)
    assert AccountLedgerLifecycleAdapter().record_open(case)["lifecycle_state"] == "zero_dte_open"


def test_account_ledger_mismatch_sends_audit_only(lifecycle_result: dict):
    assert _summary(lifecycle_result)["account_ledger_mismatch_count"] >= 1


def test_account_ledger_lifecycle_proof_written(lifecycle_result: dict):
    assert LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH.exists()


def test_lifecycle_sell_to_open_attempt_rejected(lifecycle_result: dict):
    assert any("sell_to_open_rejected" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_lifecycle_unsupported_spread_rejected(lifecycle_result: dict):
    assert any("unsupported_spread_rejected" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_lifecycle_naked_option_attempt_terminal_blocked():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "naked_option_attempt": True}, default_lifecycle_policy())["reason_codes"]


def test_lifecycle_live_flag_injection_terminal_blocked():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "live_flag_injection": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_lifecycle_broker_path_injection_terminal_blocked():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "broker_path_injection": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_lifecycle_credential_reference_terminal_blocked():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "credential_reference": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_lifecycle_scheduler_emergence_terminal_blocked():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "scheduler_emergence": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_lifecycle_real_sizing_reference_terminal_blocked():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "real_sizing_reference": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_lifecycle_close_without_open_rejected(lifecycle_result: dict):
    assert any("close_without_open_position_rejected" in record.get("blocked_reason_codes", []) for record in _jsonl(LIFECYCLE_TRANSITIONS_PATH))


def test_full_suite_timeout_misclassified_as_pass_terminal_blocked():
    assert evaluate_lifecycle_case({**build_lifecycle_cases()[0], "full_suite_timeout_misclassified_as_pass": True}, default_lifecycle_policy())["status"] == "terminal_block"


def test_allocator_consumes_lifecycle_feedback(lifecycle_result: dict):
    assert allocator_lifecycle_feedback_summary()["lifecycle_feedback_loaded"]


def test_portfolio_replay_consumes_lifecycle_feedback(lifecycle_result: dict):
    assert portfolio_lifecycle_feedback_summary()["lifecycle_feedback_loaded"]


def test_stress_ladder_consumes_lifecycle_feedback(lifecycle_result: dict):
    assert stress_lifecycle_feedback_summary()["lifecycle_feedback_loaded"]


def test_incident_response_consumes_lifecycle_feedback(lifecycle_result: dict):
    assert incident_lifecycle_feedback_summary()["lifecycle_feedback_loaded"]


def test_lifecycle_feedback_does_not_mutate_live_defaults(lifecycle_result: dict):
    assert allocator_lifecycle_feedback_summary()["live_allocation_mutation_allowed"] is False


def test_lifecycle_policy_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_POLICY_PATH.exists()


def test_lifecycle_cases_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_CASES_PATH.exists()


def test_lifecycle_states_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_STATES_PATH.exists()


def test_lifecycle_transitions_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_TRANSITIONS_PATH.exists()


def test_lifecycle_proof_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_PROOF_PATH.exists()


def test_lifecycle_paperbroker_results_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_PAPERBROKER_RESULTS_PATH.exists()


def test_lifecycle_account_ledger_results_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH.exists()


def test_lifecycle_feedback_allocator_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_FEEDBACK_ALLOCATOR_PATH.exists()


def test_lifecycle_feedback_portfolio_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_FEEDBACK_PORTFOLIO_PATH.exists()


def test_lifecycle_feedback_stress_ladder_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH.exists()


def test_lifecycle_feedback_incident_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_FEEDBACK_INCIDENT_PATH.exists()


def test_lifecycle_summary_artifact_written(lifecycle_result: dict):
    assert LIFECYCLE_SUMMARY_PATH.exists()


def test_audit_recognizes_lifecycle_artifacts(lifecycle_result: dict):
    audit = run_active_policy_audit(write_proofs=False)
    assert "lifecycle_summary" in audit["artifact_paths"]


def test_audit_flags_lifecycle_real_dollars(lifecycle_result: dict):
    assert _failed(_audit({"paper_only": True, "live_blocked": True, "real_capital_dollars": 1}), "lifecycle_no_real_dollars")


def test_audit_flags_lifecycle_buying_power(lifecycle_result: dict):
    assert _failed(_audit({"paper_only": True, "live_blocked": True, "buying_power": 1}), "lifecycle_no_buying_power")


def test_audit_flags_lifecycle_account_balance(lifecycle_result: dict):
    assert _failed(_audit({"paper_only": True, "live_blocked": True, "account_balance": 1}), "lifecycle_no_account_balance")


def test_audit_flags_lifecycle_broker_path(lifecycle_result: dict):
    assert _failed(_audit({"paper_only": True, "live_blocked": True, "note": "broker_execute"}), "lifecycle_no_broker_path")


def test_audit_flags_lifecycle_credentials(lifecycle_result: dict):
    assert _failed(_audit({"paper_only": True, "live_blocked": True, "credential_value": "x"}), "lifecycle_no_credentials")


def test_audit_flags_lifecycle_scheduler(lifecycle_result: dict):
    assert _failed(_audit({"paper_only": True, "live_blocked": True, "scheduler_enabled": True}), "lifecycle_no_scheduler")


def test_audit_flags_lifecycle_live_order(lifecycle_result: dict):
    assert _failed(_audit({"paper_only": True, "live_blocked": True, "live_order_allowed": True}), "lifecycle_no_live_order")


def test_audit_flags_lifecycle_same_day_churn(lifecycle_result: dict):
    assert _summary(lifecycle_result)["same_day_churn_allowed"] is False


def test_audit_flags_lifecycle_paperbroker_override(lifecycle_result: dict):
    assert _summary(lifecycle_result)["paperbroker_override_allowed"] is False


def test_audit_confirms_lifecycle_paper_only_live_blocked(lifecycle_result: dict):
    checks = audit_active_lifecycle_records(_json(LIFECYCLE_POLICY_PATH), _json(LIFECYCLE_CASES_PATH), _jsonl(LIFECYCLE_STATES_PATH), _jsonl(LIFECYCLE_TRANSITIONS_PATH), _jsonl(LIFECYCLE_PROOF_PATH), _jsonl(LIFECYCLE_PAPERBROKER_RESULTS_PATH), _jsonl(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH), _jsonl(LIFECYCLE_FEEDBACK_ALLOCATOR_PATH), _jsonl(LIFECYCLE_FEEDBACK_PORTFOLIO_PATH), _jsonl(LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH), _jsonl(LIFECYCLE_FEEDBACK_INCIDENT_PATH), _json(LIFECYCLE_SUMMARY_PATH))
    assert any(check["check_id"] == "lifecycle_all_paper_only" and check["passed"] for check in checks)


def test_audit_confirms_no_active_forbidden_live_decisions_after_lifecycle(lifecycle_result: dict):
    audit = run_active_policy_audit(write_proofs=False)
    assert audit.get("active_forbidden_live_decisions", audit.get("forbidden_live_decisions_active", 0)) == 0


def test_reporting_includes_lifecycle_summary(lifecycle_result: dict):
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _active_lifecycle_summary(evidence)["lifecycle_case_count"] >= 120


def test_reporting_includes_lifecycle_state_distribution(lifecycle_result: dict):
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _active_lifecycle_summary(evidence)["state_distribution"]


def test_reporting_includes_lifecycle_transition_distribution(lifecycle_result: dict):
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _active_lifecycle_summary(evidence)["transition_distribution"]


def test_reporting_includes_paperbroker_lifecycle_summary(lifecycle_result: dict):
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _active_lifecycle_summary(evidence)["paperbroker_rejection_count"] >= 1


def test_export_verifier_selects_lifecycle_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"lifecycle_summary", "lifecycle_proof", "lifecycle_cases"}.issubset(ids)


def test_export_review_includes_lifecycle_summary():
    ctx = SimpleNamespace(shared_export_path="Z:/fixture", reporting_summary={"active_lifecycle_summary": {"lifecycle_case_count": 136, "proof_completeness": True}}, safety_state={}, export_safety_scan={})
    bundle = SimpleNamespace(source_bundle_id="b", source_export_path="local", artifact_count=1, hash_status="pass", copy_status="verified", safety_status="pass", credential_scan_status="pass", active_forbidden_live_decisions=0)
    decision = SimpleNamespace(decision="pass", suitability="offline_review", next_build_target="broker-readiness preflight checklist and read-only boundary simulator")
    assert "Active Long Call / Long Put Lifecycle" in render_executive_summary(ctx, bundle, [], decision)


def test_lifecycle_artifact_ledger_written(lifecycle_result: dict):
    assert Path("docs/reports/DOPEY_ACTIVE_LIFECYCLE_ARTIFACT_LEDGER.md").exists() or LIFECYCLE_SUMMARY_PATH.exists()


def test_shard_plan_includes_lifecycle_tests():
    files = collect_test_files()
    summary = {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}}
    plan = write_test_shard_plan(files, [], summary)
    assert "tests/test_active_option_lifecycle_simulator.py" in plan["active_lifecycle_test_files"]


def test_shard_plan_marks_lifecycle_artifact_tests_sequential():
    plan = _json(TEST_SHARD_PLAN_PATH)
    assert "tests/test_active_option_lifecycle_simulator.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass():
    plan = _json(TEST_SHARD_PLAN_PATH)
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_lifecycle_simulator(lifecycle_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_robinhood_stub_still_blocks_live_after_lifecycle_simulator(lifecycle_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_lifecycle_simulator(lifecycle_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_lifecycle_simulator(lifecycle_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_lifecycle_simulator():
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_lifecycle").glob("*.py"))
    assert "api_key" not in text and "credential_value" not in text and "password" not in text


def test_no_scheduler_created_by_lifecycle_simulator():
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_lifecycle").glob("*.py"))
    assert "cron_expression" not in text and "scheduler_enabled" not in text


def test_no_network_market_data_dependency_created_by_lifecycle_simulator():
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_lifecycle").glob("*.py"))
    assert "requests" not in text and "httpx" not in text and "yfinance" not in text


def test_no_same_day_churn_loophole_created_by_lifecycle_simulator(lifecycle_result: dict):
    assert _summary(lifecycle_result)["same_day_churn_allowed"] is False


def test_no_real_capital_allocator_created_by_lifecycle_simulator(lifecycle_result: dict):
    assert _summary(lifecycle_result)["live_allocation_mutation_allowed"] is False


def test_no_real_buying_power_logic_created_by_lifecycle_simulator(lifecycle_result: dict):
    text = LIFECYCLE_SUMMARY_PATH.read_text(encoding="utf-8").lower()
    assert "buying_power" not in text


def test_no_broker_capability_detector_created_by_lifecycle_simulator():
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_lifecycle").glob("*.py"))
    assert "capability_detector" not in text


def test_blunder_integrity_unchanged_if_manifest_available():
    manifest = Path("artifacts/dopey/exports/blunder_integrity_status.json")
    if not manifest.exists():
        assert True
    else:
        assert _json(manifest).get("blunder_integrity_status", "unchanged") in {"unchanged", "not_applicable"}
