from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_broker_readiness.approval_forbidden_scope_scanner import scan_forbidden_scope_terms
from dopey_broker_readiness.approval_intake_models import (
    ApprovalIntakeRequest,
    ApprovalIntakeResult,
    ApprovalScopeValidation,
    approval_intake_request_hash,
    approval_intake_result_hash,
    approval_scope_validation_hash,
    make_absent_approval_intake_request,
)
from dopey_broker_readiness.approval_intake_validator import (
    APPROVAL_BOUNDARY_BLOCKS_PATH,
    APPROVAL_FORBIDDEN_TERMS_PATH,
    APPROVAL_INCIDENT_ESCALATIONS_PATH,
    APPROVAL_INTAKE_EXPECTED_RESULTS_FIXTURE_PATH,
    APPROVAL_INTAKE_EXPECTED_VALIDATIONS_FIXTURE_PATH,
    APPROVAL_INTAKE_FORBIDDEN_TERMS_FIXTURE_PATH,
    APPROVAL_INTAKE_LEDGER_PATH,
    APPROVAL_INTAKE_PROOF_PATH,
    APPROVAL_INTAKE_REPORT_PATH,
    APPROVAL_INTAKE_REQUESTS_FIXTURE_PATH,
    APPROVAL_INTAKE_REQUESTS_PATH,
    APPROVAL_INTAKE_RESULTS_PATH,
    APPROVAL_INTAKE_SCOPE_CLAIMS_FIXTURE_PATH,
    APPROVAL_INTAKE_SUMMARY_PATH,
    APPROVAL_SCOPE_VALIDATIONS_PATH,
    validate_read_only_detector_approval_intake,
)
from dopey_broker_readiness.audit import audit_approval_intake_summary
from dopey_broker_readiness.manual_approval_models import REQUIRED_OPERATOR_ACKNOWLEDGEMENT
from dopey_broker_readiness.manual_approval_packet_builder import build_manual_approval_packet_outputs
from dopey_broker_readiness.read_only_detector_dry_run_validator import validate_read_only_detector_dry_run
from dopey_broker_readiness.run_broker_readiness_preflight import run_broker_readiness_preflight
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import ExportReviewBundle, ExportReviewDecision
from dopey_export_review.review_packet import render_executive_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _approval_intake_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


@pytest.fixture(scope="session")
def approval_bundle() -> dict[str, Any]:
    run_broker_readiness_preflight()
    build_manual_approval_packet_outputs()
    validate_read_only_detector_dry_run()
    result = validate_read_only_detector_approval_intake()
    return {
        "result": result,
        "requests": _jsonl(APPROVAL_INTAKE_REQUESTS_PATH),
        "validations": _jsonl(APPROVAL_SCOPE_VALIDATIONS_PATH),
        "results": _jsonl(APPROVAL_INTAKE_RESULTS_PATH),
        "terms": _json(APPROVAL_FORBIDDEN_TERMS_PATH),
        "blocks": _jsonl(APPROVAL_BOUNDARY_BLOCKS_PATH),
        "escalations": _jsonl(APPROVAL_INCIDENT_ESCALATIONS_PATH),
        "summary": _json(APPROVAL_INTAKE_SUMMARY_PATH),
        "proof": _jsonl(APPROVAL_INTAKE_PROOF_PATH),
        "request_fixture": _json(APPROVAL_INTAKE_REQUESTS_FIXTURE_PATH),
        "expected_validations": _json(APPROVAL_INTAKE_EXPECTED_VALIDATIONS_FIXTURE_PATH),
        "expected_results": _json(APPROVAL_INTAKE_EXPECTED_RESULTS_FIXTURE_PATH),
        "forbidden_terms_fixture": _json(APPROVAL_INTAKE_FORBIDDEN_TERMS_FIXTURE_PATH),
        "scope_claims_fixture": _json(APPROVAL_INTAKE_SCOPE_CLAIMS_FIXTURE_PATH),
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _raw_request(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["request_fixture"]["records"] if record["case_name"] == case_name)


def _validation(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["validations"] if record["case_name"] == case_name)


def _result(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["results"] if record["case_name"] == case_name)


def _block(bundle: dict[str, Any], incident_type: str) -> dict[str, Any]:
    return next(record for record in bundle["blocks"] if record["incident_type"] == incident_type)


def _term_ids(text: str) -> set[str]:
    return {record["term_id"] for record in scan_forbidden_scope_terms(text)}


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(intent_id="approval-intake-live", symbol="DLP1", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-17", "dte": 5}], max_loss=1.0, live_allowed=True, active_policy_required=True)


def _model_request_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"case_name", "case_group", "operator_text_hash"}}


def test_approval_intake_request_serializes_deterministically(approval_bundle: dict[str, Any]) -> None:
    record = _raw_request(approval_bundle, "exact_required_acknowledgement_fixture_validates")
    model = ApprovalIntakeRequest.from_dict(_model_request_payload(record))
    assert model.to_dict() == _model_request_payload(record)


def test_approval_scope_validation_serializes_deterministically(approval_bundle: dict[str, Any]) -> None:
    record = _validation(approval_bundle, "exact_required_acknowledgement_fixture_validates")
    model = ApprovalScopeValidation.from_dict({key: value for key, value in record.items() if key not in {"case_name", "case_group"}})
    assert model.to_dict() == {key: value for key, value in record.items() if key not in {"case_name", "case_group"}}


def test_approval_intake_result_serializes_deterministically(approval_bundle: dict[str, Any]) -> None:
    record = _result(approval_bundle, "exact_required_acknowledgement_fixture_validates")
    model = ApprovalIntakeResult.from_dict({key: value for key, value in record.items() if key not in {"case_name", "case_group"}})
    assert model.to_dict() == {key: value for key, value in record.items() if key not in {"case_name", "case_group"}}


def test_approval_intake_hashes_are_deterministic(approval_bundle: dict[str, Any]) -> None:
    req = _raw_request(approval_bundle, "exact_required_acknowledgement_fixture_validates")
    val = _validation(approval_bundle, "exact_required_acknowledgement_fixture_validates")
    res = _result(approval_bundle, "exact_required_acknowledgement_fixture_validates")
    assert approval_intake_request_hash(ApprovalIntakeRequest.from_dict({**_model_request_payload(req), "request_hash": ""})) == req["request_hash"]
    assert approval_scope_validation_hash(ApprovalScopeValidation.from_dict({**{k: v for k, v in val.items() if k not in {"case_name", "case_group"}}, "validation_hash": ""})) == val["validation_hash"]
    assert approval_intake_result_hash(ApprovalIntakeResult.from_dict({**{k: v for k, v in res.items() if k not in {"case_name", "case_group"}}, "result_hash": ""})) == res["result_hash"]


def test_approval_intake_default_does_not_use_real_operator_input() -> None:
    request = make_absent_approval_intake_request("packet", "ack-hash")
    assert request.approval_channel == "absent"
    assert request.operator_text_present is False


def test_approval_intake_requires_paper_only_live_blocked(approval_bundle: dict[str, Any]) -> None:
    payload = {**_model_request_payload(_raw_request(approval_bundle, "exact_required_acknowledgement_fixture_validates")), "paper_only": False}
    with pytest.raises(ValueError):
        ApprovalIntakeRequest.from_dict(payload)


def test_approval_intake_result_defaults_all_runtime_permissions_false(approval_bundle: dict[str, Any]) -> None:
    result = _result(approval_bundle, "exact_required_acknowledgement_fixture_validates")
    assert not any(result[name] for name in ["approval_effective_now", "detector_run_allowed_now", "broker_connection_allowed_now", "credential_allowed_now", "live_order_allowed_now", "scheduler_allowed_now", "real_sizing_allowed_now"])


def test_approval_intake_validator_loads_required_acknowledgement(approval_bundle: dict[str, Any]) -> None:
    assert _raw_request(approval_bundle, "exact_required_acknowledgement_fixture_validates")["operator_text"] == REQUIRED_OPERATOR_ACKNOWLEDGEMENT


def test_approval_intake_validator_loads_future_detector_contract(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["next_required_gate"] == "separate_explicitly_approved_read_only_detector_run_bundle"


def test_missing_approval_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "missing_approval_rejected")["validation_status"] == "missing"


def test_empty_approval_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "empty_approval_rejected")["validation_status"] == "missing"


def test_whitespace_approval_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "whitespace_only_approval_rejected")["validation_status"] == "missing"


def test_exact_required_acknowledgement_fixture_validates(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "exact_required_acknowledgement_fixture_validates")["validation_status"] == "valid_exact_read_only_detector_only_fixture"


def test_exact_valid_fixture_does_not_run_detector(approval_bundle: dict[str, Any]) -> None:
    assert _result(approval_bundle, "valid_fixture_approval_still_does_not_run_detector")["detector_run_allowed_now"] is False


def test_exact_valid_fixture_does_not_create_broker_connection(approval_bundle: dict[str, Any]) -> None:
    assert _result(approval_bundle, "valid_fixture_approval_still_does_not_create_broker_connection")["broker_connection_allowed_now"] is False


def test_exact_valid_fixture_does_not_create_credentials(approval_bundle: dict[str, Any]) -> None:
    assert _result(approval_bundle, "valid_fixture_approval_still_does_not_create_credentials")["credential_allowed_now"] is False


def test_exact_valid_fixture_marks_future_detector_eligible_only(approval_bundle: dict[str, Any]) -> None:
    result = _result(approval_bundle, "valid_fixture_approval_only_marks_future_detector_eligible")
    assert result["future_detector_eligible_for_next_bundle"] is True
    assert result["approval_effective_now"] is False


def test_lowercase_difference_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "lowercase_difference_rejected")["validation_status"] == "invalid"


def test_punctuation_difference_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "punctuation_difference_rejected")["validation_status"] == "invalid"


def test_partial_approval_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "partial_read_only_approval_rejected")["partial_approval"] is True


def test_forbidden_scope_scanner_detects_live_trading() -> None:
    assert "live_trading" in _term_ids("allow live trading")


def test_forbidden_scope_scanner_detects_live_orders() -> None:
    assert "live_orders" in _term_ids("allow live orders")


def test_forbidden_scope_scanner_detects_order_placement() -> None:
    assert "order_placement" in _term_ids("allow order placement")


def test_forbidden_scope_scanner_detects_order_cancellation() -> None:
    assert "order_cancellation" in _term_ids("allow order cancellation")


def test_forbidden_scope_scanner_detects_broker_execution() -> None:
    assert "broker_execution" in _term_ids("allow broker execution")


def test_forbidden_scope_scanner_detects_credentials() -> None:
    assert "credentials" in _term_ids("store credentials")


def test_forbidden_scope_scanner_detects_token() -> None:
    assert "token" in _term_ids("use token")


def test_forbidden_scope_scanner_detects_env() -> None:
    assert "env_file" in _term_ids("use .env")


def test_forbidden_scope_scanner_detects_account_balance() -> None:
    assert "account_balance" in _term_ids("use account balance")


def test_forbidden_scope_scanner_detects_buying_power() -> None:
    assert "buying_power" in _term_ids("use buying power")


def test_forbidden_scope_scanner_detects_real_sizing() -> None:
    assert "real_sizing" in _term_ids("allow real sizing")


def test_forbidden_scope_scanner_detects_scheduler() -> None:
    assert "scheduler" in _term_ids("start scheduler")


def test_forbidden_scope_scanner_detects_autonomous_live() -> None:
    assert "autonomous_live" in _term_ids("autonomous live")


def test_forbidden_scope_scanner_detects_network_market_data() -> None:
    assert "network_market_data" in _term_ids("network market data")


def test_forbidden_scope_scanner_detects_sell_to_open() -> None:
    assert "sell_to_open" in _term_ids("sell-to-open")


def test_forbidden_scope_scanner_detects_naked_option() -> None:
    assert "naked_option" in _term_ids("naked option")


def test_approval_omitting_no_live_orders_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_omitting_no_live_orders_rejected")["validation_status"] == "invalid"


def test_approval_omitting_no_credential_storage_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_omitting_no_credential_storage_rejected")["validation_status"] == "invalid"


def test_approval_omitting_no_order_placement_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_omitting_no_order_placement_rejected")["validation_status"] == "invalid"


def test_approval_omitting_no_order_cancellation_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_omitting_no_order_cancellation_rejected")["validation_status"] == "invalid"


def test_approval_omitting_no_scheduler_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_omitting_no_scheduler_rejected")["validation_status"] == "invalid"


def test_approval_adding_place_trades_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_place_trades_terminal_blocked")["validation_status"] == "terminal_block"


def test_approval_adding_live_trading_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_live_trading_terminal_blocked")["live_trading_scope_detected"] is True


def test_approval_adding_store_credentials_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_store_credentials_terminal_blocked")["credential_scope_detected"] is True


def test_approval_adding_account_balance_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_account_balance_terminal_blocked")["real_sizing_scope_detected"] is True


def test_approval_adding_buying_power_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_buying_power_terminal_blocked")["real_sizing_scope_detected"] is True


def test_approval_adding_real_sizing_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_real_sizing_terminal_blocked")["real_sizing_scope_detected"] is True


def test_approval_adding_cancel_orders_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_cancel_orders_terminal_blocked")["order_cancellation_scope_detected"] is True


def test_approval_adding_autonomous_live_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_autonomous_live_trading_terminal_blocked")["autonomous_loop_scope_detected"] is True


def test_approval_adding_robinhood_mcp_execution_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_robinhood_mcp_execution_terminal_blocked")["broker_execute_scope_detected"] is True


def test_approval_adding_broker_write_access_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_broker_write_access_terminal_blocked")["broker_execute_scope_detected"] is True


def test_approval_adding_scheduler_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_adding_scheduler_terminal_blocked")["scheduler_scope_detected"] is True


def test_approval_adding_network_market_data_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert "network_market_data" in _validation(approval_bundle, "approval_adding_network_market_data_terminal_blocked")["forbidden_terms_detected"]


def test_stale_approval_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "stale_approval_rejected")["validation_status"] == "invalid"


def test_revoked_approval_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "revoked_approval_rejected")["validation_status"] == "invalid"


def test_expired_approval_rejected(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "expired_approval_rejected")["validation_status"] == "invalid"


def test_invalid_channel_rejected(approval_bundle: dict[str, Any]) -> None:
    assert "approval_from_invalid_channel" in _validation(approval_bundle, "invalid_channel_rejected")["reason_codes"]


def test_hidden_newline_command_rejected(approval_bundle: dict[str, Any]) -> None:
    assert "hidden_newline_command" in _validation(approval_bundle, "hidden_newline_command_rejected")["forbidden_terms_detected"]


def test_command_injection_like_text_rejected(approval_bundle: dict[str, Any]) -> None:
    assert "command_injection_like_text" in _validation(approval_bundle, "command_injection_like_text_rejected")["forbidden_terms_detected"]


def test_path_token_reference_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert "path_token_reference" in _validation(approval_bundle, "path_token_reference_terminal_blocked")["forbidden_terms_detected"]


def test_ambiguous_scope_expansion_manual_review(approval_bundle: dict[str, Any]) -> None:
    assert _validation(approval_bundle, "approval_ambiguous_scope_manual_review")["validation_status"] == "manual_review_required"


def test_approval_intake_requests_fixture_loads(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["request_fixture"]["case_count"] == 96


def test_approval_intake_expected_validations_load(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["expected_validations"]["case_count"] == 96


def test_approval_intake_expected_results_load(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["expected_results"]["case_count"] == 96


def test_approval_intake_forbidden_terms_load(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["forbidden_terms_fixture"]["case_count"] >= 24


def test_approval_intake_scope_claims_load(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["scope_claims_fixture"]["case_count"] >= 8


def test_approval_intake_has_at_least_96_cases(approval_bundle: dict[str, Any]) -> None:
    assert len(approval_bundle["request_fixture"]["records"]) >= 96


def test_approval_intake_covers_missing_approval_cases(approval_bundle: dict[str, Any]) -> None:
    assert _group_count(approval_bundle, "missing_approval") >= 12


def test_approval_intake_covers_exact_valid_fixture_cases(approval_bundle: dict[str, Any]) -> None:
    assert _group_count(approval_bundle, "exact_valid_fixture") >= 12


def test_approval_intake_covers_partial_approval_cases(approval_bundle: dict[str, Any]) -> None:
    assert _group_count(approval_bundle, "partial_approval") >= 16


def test_approval_intake_covers_extra_scope_cases(approval_bundle: dict[str, Any]) -> None:
    assert _group_count(approval_bundle, "extra_scope_approval") >= 16


def test_approval_intake_covers_forbidden_term_cases(approval_bundle: dict[str, Any]) -> None:
    assert _group_count(approval_bundle, "forbidden_term_approval") >= 16


def test_approval_intake_covers_terminal_block_cases(approval_bundle: dict[str, Any]) -> None:
    assert _group_count(approval_bundle, "terminal_block_escalation") >= 8


def test_approval_intake_covers_manual_review_cases(approval_bundle: dict[str, Any]) -> None:
    assert _group_count(approval_bundle, "manual_review") >= 8


def test_invalid_approval_live_scope_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_invalid_live_scope")["response_decision"] == "terminal_block"


def test_invalid_approval_credential_scope_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_invalid_credential_scope")["kill_switch_state"] == "terminal_block"


def test_invalid_approval_order_placement_scope_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_invalid_order_placement_scope")["response_decision"] == "terminal_block"


def test_invalid_approval_cancellation_scope_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_invalid_cancellation_scope")["kill_switch_state"] == "terminal_block"


def test_invalid_approval_scheduler_scope_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_invalid_scheduler_scope")["response_decision"] == "terminal_block"


def test_invalid_approval_real_sizing_scope_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_invalid_real_sizing_scope")["kill_switch_state"] == "terminal_block"


def test_invalid_approval_broker_execute_scope_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_invalid_broker_path_scope")["response_decision"] == "terminal_block"


def test_valid_fixture_approval_followed_by_detector_run_attempt_terminal_blocks(approval_bundle: dict[str, Any]) -> None:
    assert _block(approval_bundle, "approval_intake_valid_fixture_followed_by_detector_run_attempt")["kill_switch_state"] == "terminal_block"


def test_approval_intake_requests_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_INTAKE_REQUESTS_PATH.exists()


def test_approval_scope_validations_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_SCOPE_VALIDATIONS_PATH.exists()


def test_approval_intake_results_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_INTAKE_RESULTS_PATH.exists()


def test_approval_forbidden_terms_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_FORBIDDEN_TERMS_PATH.exists()


def test_approval_boundary_blocks_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_BOUNDARY_BLOCKS_PATH.exists()


def test_approval_incident_escalations_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_INCIDENT_ESCALATIONS_PATH.exists()


def test_approval_intake_summary_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_INTAKE_SUMMARY_PATH.exists()


def test_approval_intake_proof_artifact_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_INTAKE_PROOF_PATH.exists()


def test_audit_recognizes_approval_intake_artifacts(approval_bundle: dict[str, Any]) -> None:
    types = {record[0] for record in ARTIFACT_SPECS}
    assert {"approval_intake_requests", "approval_scope_validations", "approval_intake_results", "approval_intake_summary", "approval_intake_proof"}.issubset(types)


def test_audit_confirms_exact_valid_fixture_does_not_run_detector(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["read_only_detector_run"] is False


def test_audit_confirms_approval_effective_now_false(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["approval_effective_now_count"] == 0


def test_audit_confirms_detector_run_allowed_now_false(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["detector_run_allowed_now_count"] == 0


def test_audit_confirms_broker_connection_allowed_now_false(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["broker_connection_allowed_now_count"] == 0


def test_audit_confirms_credential_allowed_now_false(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["credential_allowed_now_count"] == 0


def test_audit_confirms_live_order_allowed_now_false(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["live_order_allowed_now_count"] == 0


def test_audit_confirms_scheduler_allowed_now_false(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["scheduler_allowed_now_count"] == 0


def test_audit_confirms_real_sizing_allowed_now_false(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["real_sizing_allowed_now_count"] == 0


def test_audit_flags_scope_expansion_terminal_block(approval_bundle: dict[str, Any]) -> None:
    assert audit_approval_intake_summary({**approval_bundle["summary"], "terminal_block_count": 0})


def test_audit_confirms_no_active_forbidden_live_decisions_after_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert audit_approval_intake_summary(approval_bundle["summary"]) == []


def test_reporting_includes_approval_intake_summary(approval_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _approval_intake_summary(evidence)["approval_intake_status"] == "approval_intake_fixture_validated"


def test_reporting_includes_approval_status_distribution(approval_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _approval_intake_summary(evidence)["approval_status_distribution"]["terminal_block"] >= 1


def test_reporting_includes_forbidden_term_distribution(approval_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _approval_intake_summary(evidence)["forbidden_term_distribution"]


def test_reporting_includes_future_detector_eligible_count(approval_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _approval_intake_summary(evidence)["future_detector_eligible_count"] == 12


def test_reporting_detector_run_allowed_now_zero(approval_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _approval_intake_summary(evidence)["detector_run_allowed_now_count"] == 0


def test_export_verifier_selects_approval_intake_artifacts(approval_bundle: dict[str, Any]) -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"approval_intake_summary", "approval_intake_proof"}.issubset(ids)


def test_export_review_includes_approval_intake_summary(approval_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(reporting_summary={"approval_intake_summary": approval_bundle["summary"]}, shared_export_path="shared", safety_state={}, export_safety_scan={})
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "read-only detector approval intake validator", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "approve_for_offline_review", "offline_review_only", [], [], "read-only detector approval intake validator", True, True, "hash")
    assert "Read-Only Detector Approval Intake Validator" in render_executive_summary(ctx, bundle, [], decision)


def test_approval_intake_artifact_ledger_written(approval_bundle: dict[str, Any]) -> None:
    assert APPROVAL_INTAKE_LEDGER_PATH.exists()


def test_shard_plan_includes_approval_intake_tests() -> None:
    plan = _approval_shard_plan()
    assert plan["split_suite_lanes"]["approval_intake_validator_tests"] == ["tests/test_read_only_detector_approval_intake_validator.py"]


def test_shard_plan_marks_approval_intake_artifact_tests_sequential() -> None:
    plan = _approval_shard_plan()
    assert "tests/test_read_only_detector_approval_intake_validator.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    plan = _approval_shard_plan()
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["live_blocked"] is True


def test_robinhood_stub_still_blocks_live_after_approval_intake(approval_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_approval_intake(approval_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_approval_intake(approval_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["credentials_created"] is False
    assert not Path(".env").exists()


def test_no_scheduler_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["scheduler_created"] is False


def test_no_network_market_data_dependency_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["no_real_market_data"] is True


def test_no_same_day_churn_loophole_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert "normal_same_day_round_trip" not in json.dumps(approval_bundle["summary"])


def test_no_real_capital_allocator_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["real_sizing_created"] is False


def test_no_real_buying_power_logic_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["real_buying_power_logic_created"] is False


def test_no_robinhood_mcp_integration_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["robinhood_mcp_integration_created"] is False


def test_no_broker_connection_created_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["broker_connection_created"] is False


def test_no_read_only_detector_run_by_approval_intake(approval_bundle: dict[str, Any]) -> None:
    assert approval_bundle["summary"]["read_only_detector_run"] is False


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    findings = audit_blunder_integrity()
    assert not [finding for finding in findings if finding.severity == "safety_error"]


def _group_count(bundle: dict[str, Any], group_name: str) -> int:
    return sum(1 for record in bundle["request_fixture"]["records"] if record["case_group"] == group_name)


def _approval_shard_plan() -> dict[str, Any]:
    summary = {"collection": {"status": "pass", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    result = CommandResult(["python", "-m", "pytest", "tests/test_read_only_detector_approval_intake_validator.py", "-q"], "pass", 0, 1.0, False, False, "ok", "")
    return write_test_shard_plan(["tests/test_read_only_detector_approval_intake_validator.py"], [result], summary)
