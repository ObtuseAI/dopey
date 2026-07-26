from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_broker_readiness.audit import audit_future_detector_command_template, audit_manual_approval_packet_summary
from dopey_broker_readiness.boundary_incidents import broker_boundary_incident_records
from dopey_broker_readiness.future_detector_command_templates import build_future_detector_command_templates
from dopey_broker_readiness.manual_approval_models import (
    EXPLICIT_MANUAL_APPROVAL_GATE,
    REQUIRED_OPERATOR_ACKNOWLEDGEMENT,
    ManualApprovalGate,
    ReadOnlyDetectorApprovalPacket,
    ReadOnlyDetectorScope,
    gate_hash,
    make_manual_approval_gate,
    make_read_only_detector_approval_packet,
    make_read_only_detector_scope,
    packet_hash,
    scope_hash,
)
from dopey_broker_readiness.manual_approval_packet_builder import (
    EXPECTED_APPROVAL_PACKET_SUMMARY_PATH,
    EXPECTED_MANUAL_GATE_RESULTS_PATH,
    FUTURE_DETECTOR_COMMAND_TEMPLATES_FIXTURE_PATH,
    FUTURE_DETECTOR_COMMAND_TEMPLATES_PATH,
    MANUAL_APPROVAL_BOUNDARY_BLOCKS_PATH,
    MANUAL_APPROVAL_GATE_PATH,
    MANUAL_APPROVAL_GATES_FIXTURE_PATH,
    MANUAL_APPROVAL_LEDGER_PATH,
    MANUAL_APPROVAL_PACKET_CASES_FIXTURE_PATH,
    MANUAL_APPROVAL_PACKET_PROOF_PATH,
    MANUAL_APPROVAL_PACKET_SUMMARY_PATH,
    MANUAL_APPROVAL_REPORT_PATH,
    MANUAL_APPROVAL_SCOPE_FIXTURE_PATH,
    MANUAL_GATE_VALIDATION_RESULTS_PATH,
    OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH,
    READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH,
    READ_ONLY_DETECTOR_SCOPE_PATH,
    build_manual_approval_packet_outputs,
)
from dopey_broker_readiness.manual_gate_validator import validate_manual_approval_text
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
from dopey_reporting.reporting_bundle import _manual_approval_packet_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


@pytest.fixture(scope="session")
def manual_bundle() -> dict[str, Any]:
    run_broker_readiness_preflight()
    result = build_manual_approval_packet_outputs()
    return {
        "result": result,
        "scope": _json(READ_ONLY_DETECTOR_SCOPE_PATH),
        "gate": _json(MANUAL_APPROVAL_GATE_PATH),
        "packet": _json(READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH),
        "templates": _jsonl(FUTURE_DETECTOR_COMMAND_TEMPLATES_PATH),
        "validations": _jsonl(MANUAL_GATE_VALIDATION_RESULTS_PATH),
        "blocks": _jsonl(MANUAL_APPROVAL_BOUNDARY_BLOCKS_PATH),
        "summary": _json(MANUAL_APPROVAL_PACKET_SUMMARY_PATH),
        "proof": _jsonl(MANUAL_APPROVAL_PACKET_PROOF_PATH),
        "cases": _json(MANUAL_APPROVAL_PACKET_CASES_FIXTURE_PATH)["records"],
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _case(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["cases"] if record["case_name"] == case_name)


def _block(bundle: dict[str, Any], incident_type: str) -> dict[str, Any]:
    return next(record for record in bundle["blocks"] if record["incident_type"] == incident_type)


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(intent_id="manual-live", symbol="DLP1", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-17", "dte": 5}], max_loss=1.0, live_allowed=True, active_policy_required=True)


def test_read_only_detector_scope_serializes_deterministically() -> None:
    scope = make_read_only_detector_scope()
    assert ReadOnlyDetectorScope.from_dict(scope.to_dict()).to_dict() == scope.to_dict()


def test_manual_approval_gate_serializes_deterministically() -> None:
    gate = make_manual_approval_gate()
    assert ManualApprovalGate.from_dict(gate.to_dict()).to_dict() == gate.to_dict()


def test_read_only_detector_approval_packet_serializes_deterministically() -> None:
    scope = make_read_only_detector_scope()
    gate = make_manual_approval_gate()
    packet = make_read_only_detector_approval_packet("source-run", scope, gate)
    assert ReadOnlyDetectorApprovalPacket.from_dict(packet.to_dict()).to_dict() == packet.to_dict()


def test_manual_approval_hashes_are_deterministic() -> None:
    scope = make_read_only_detector_scope()
    gate = make_manual_approval_gate()
    packet = make_read_only_detector_approval_packet("source-run", scope, gate)
    assert scope_hash(ReadOnlyDetectorScope.from_dict({**scope.to_dict(), "scope_hash": ""})) == scope.scope_hash
    assert gate_hash(ManualApprovalGate.from_dict({**gate.to_dict(), "gate_hash": ""})) == gate.gate_hash
    assert packet_hash(ReadOnlyDetectorApprovalPacket.from_dict({**packet.to_dict(), "packet_hash": ""})) == packet.packet_hash


def test_scope_requires_paper_only_live_blocked() -> None:
    payload = {**make_read_only_detector_scope().to_dict(), "paper_only": False}
    with pytest.raises(ValueError):
        ReadOnlyDetectorScope.from_dict(payload)


def test_scope_forbids_write_execute_operations() -> None:
    scope = make_read_only_detector_scope()
    assert {"broker_write", "broker_execute", "live_order_placement"}.issubset(set(scope.forbidden_operations))


def test_approval_gate_default_not_approved() -> None:
    gate = make_manual_approval_gate()
    assert gate.gate_status == "packet_ready"
    assert gate.approval_present is False
    assert gate.approval_valid is False


def test_manual_approval_packet_builder_loads_preflight(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["packet"]["source_preflight_run_id"] == "dopey-broker-readiness-preflight-v1"


def test_manual_approval_packet_builder_loads_boundary_simulation(manual_bundle: dict[str, Any]) -> None:
    assert "broker_readiness_preflight_summary_exists" in manual_bundle["packet"]["preconditions"]


def test_manual_approval_packet_builder_loads_incident_proof(manual_bundle: dict[str, Any]) -> None:
    assert "incident_response_terminal_blocks_exist" in manual_bundle["packet"]["preconditions"]


def test_manual_approval_packet_builder_loads_lifecycle_proof(manual_bundle: dict[str, Any]) -> None:
    assert "active_lifecycle_proof_exists" in manual_bundle["packet"]["preconditions"]


def test_manual_approval_packet_ready_but_not_approved(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["readiness_status"] == "approval_packet_ready"
    assert manual_bundle["summary"]["detector_approved_now"] is False


def test_manual_approval_packet_next_gate_is_explicit_approval(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["next_required_gate"] == EXPLICIT_MANUAL_APPROVAL_GATE


def test_manual_approval_packet_does_not_run_detector(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["read_only_detector_run"] is False


def test_operator_acknowledgement_text_written(manual_bundle: dict[str, Any]) -> None:
    assert OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH.exists()


def test_exact_acknowledgement_text_matches_required(manual_bundle: dict[str, Any]) -> None:
    assert REQUIRED_OPERATOR_ACKNOWLEDGEMENT in OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH.read_text(encoding="utf-8")


def test_acknowledgement_is_not_treated_as_approved_in_this_bundle(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["approval_present"] is False


def test_manual_gate_rejects_missing_approval() -> None:
    assert validate_manual_approval_text(None, True)["gate_status"] == "approval_missing"


def test_manual_gate_accepts_exact_text_only_as_future_fixture() -> None:
    result = validate_manual_approval_text(REQUIRED_OPERATOR_ACKNOWLEDGEMENT, True)
    assert result["approval_valid"] is True
    assert result["detector_approved_now"] is False


def test_manual_gate_rejects_partial_approval() -> None:
    assert validate_manual_approval_text("I APPROVE DOPEY READ-ONLY BROKER CAPABILITY DETECTOR ONLY.", True)["approval_valid"] is False


def test_manual_gate_rejects_live_trading_scope() -> None:
    assert "approval_mentions_live_trading" in validate_manual_approval_text("allow live trading", True)["reason_codes"]


def test_manual_gate_rejects_credential_storage_scope() -> None:
    assert "approval_mentions_credential_storage" in validate_manual_approval_text("allow credential storage", True)["reason_codes"]


def test_manual_gate_rejects_order_placement_scope() -> None:
    assert "approval_mentions_order_placement" in validate_manual_approval_text("allow order placement", True)["reason_codes"]


def test_manual_gate_rejects_order_cancellation_scope() -> None:
    assert "approval_mentions_order_cancellation" in validate_manual_approval_text("allow order cancellation", True)["reason_codes"]


def test_manual_gate_rejects_scheduler_scope() -> None:
    assert "approval_mentions_scheduler" in validate_manual_approval_text("allow scheduler", True)["reason_codes"]


def test_manual_gate_rejects_autonomous_live_scope() -> None:
    assert "approval_mentions_autonomous_live_trading" in validate_manual_approval_text("allow autonomous live trading", True)["reason_codes"]


def test_manual_gate_rejects_real_sizing_scope() -> None:
    assert "approval_mentions_real_sizing" in validate_manual_approval_text("allow real sizing", True)["reason_codes"]


def test_manual_gate_rejects_write_access_scope() -> None:
    assert "approval_expands_to_write_access" in validate_manual_approval_text("write access", True)["reason_codes"]


def test_manual_gate_rejects_broker_execution_scope() -> None:
    assert "approval_expands_to_broker_execution" in validate_manual_approval_text("broker execution", True)["reason_codes"]


def test_future_detector_command_templates_written(manual_bundle: dict[str, Any]) -> None:
    assert len(manual_bundle["templates"]) >= 4


def test_command_templates_disabled_by_default(manual_bundle: dict[str, Any]) -> None:
    assert all(record["enabled"] is False for record in manual_bundle["templates"])


def test_command_templates_require_manual_approval(manual_bundle: dict[str, Any]) -> None:
    assert all(record["requires_manual_approval"] is True for record in manual_bundle["templates"])


def test_command_templates_allowed_now_false(manual_bundle: dict[str, Any]) -> None:
    assert all(record["allowed_now"] is False for record in manual_bundle["templates"])


def test_command_templates_contain_no_credentials(manual_bundle: dict[str, Any]) -> None:
    assert all("credential" not in record["command_template"].lower() for record in manual_bundle["templates"])


def test_command_templates_contain_no_token_paths(manual_bundle: dict[str, Any]) -> None:
    assert all("token_path" not in record["command_template"].lower() for record in manual_bundle["templates"])


def test_command_templates_contain_no_env_file(manual_bundle: dict[str, Any]) -> None:
    assert all(".env" not in record["command_template"].lower() for record in manual_bundle["templates"])


def test_command_templates_contain_no_order_placement(manual_bundle: dict[str, Any]) -> None:
    assert all("place" not in record["command_template"].lower() for record in manual_bundle["templates"])


def test_command_templates_contain_no_order_cancellation(manual_bundle: dict[str, Any]) -> None:
    assert all("cancel" not in record["command_template"].lower() for record in manual_bundle["templates"])


def test_command_templates_contain_no_scheduler(manual_bundle: dict[str, Any]) -> None:
    assert all("scheduler" not in record["command_template"].lower() for record in manual_bundle["templates"])


def test_command_templates_contain_no_live_execution(manual_bundle: dict[str, Any]) -> None:
    assert all("live-execution" not in record["command_template"].lower() for record in manual_bundle["templates"])


def test_manual_approval_scope_fixture_loads(manual_bundle: dict[str, Any]) -> None:
    assert _json(MANUAL_APPROVAL_SCOPE_FIXTURE_PATH)["case_count"] == 1


def test_manual_approval_gates_fixture_loads(manual_bundle: dict[str, Any]) -> None:
    assert _json(MANUAL_APPROVAL_GATES_FIXTURE_PATH)["case_count"] == 1


def test_manual_approval_packet_cases_load(manual_bundle: dict[str, Any]) -> None:
    assert _json(MANUAL_APPROVAL_PACKET_CASES_FIXTURE_PATH)["case_count"] == len(manual_bundle["cases"])


def test_future_detector_command_templates_fixture_loads(manual_bundle: dict[str, Any]) -> None:
    assert _json(FUTURE_DETECTOR_COMMAND_TEMPLATES_FIXTURE_PATH)["case_count"] == len(manual_bundle["templates"])


def test_expected_manual_gate_results_load(manual_bundle: dict[str, Any]) -> None:
    assert _json(EXPECTED_MANUAL_GATE_RESULTS_PATH)["case_count"] >= 12


def test_expected_approval_packet_summary_load(manual_bundle: dict[str, Any]) -> None:
    assert _json(EXPECTED_APPROVAL_PACKET_SUMMARY_PATH)["readiness_status"] == "approval_packet_ready"


def test_manual_approval_packet_has_at_least_72_cases(manual_bundle: dict[str, Any]) -> None:
    assert len(manual_bundle["cases"]) >= 72


def test_manual_approval_packet_covers_valid_read_only_scope_cases(manual_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in manual_bundle["cases"] if record["case_group"] == "valid_read_only_scope_definition") >= 12


def test_manual_approval_packet_covers_invalid_approval_cases(manual_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in manual_bundle["cases"] if record["case_group"] == "missing_or_invalid_approval") >= 12


def test_manual_approval_packet_covers_scope_expansion_rejections(manual_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in manual_bundle["cases"] if record["case_group"] == "scope_expansion_rejection") >= 12


def test_manual_approval_packet_covers_forbidden_command_templates(manual_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in manual_bundle["cases"] if record["case_group"] == "forbidden_command_template") >= 12


def test_manual_approval_packet_covers_terminal_block_cases(manual_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in manual_bundle["cases"] if record["case_group"] == "terminal_block_escalation") >= 8


def test_manual_approval_packet_covers_manual_review_cases(manual_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in manual_bundle["cases"] if record["case_group"] == "manual_review") >= 8


def test_manual_approval_packet_covers_packet_ready_cases(manual_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in manual_bundle["cases"] if record["case_group"] == "benign_packet_ready") >= 8


def test_detector_run_without_approval_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "read_only_detector_run_attempt_without_approval")["kill_switch_state"] == "terminal_block"


def test_detector_scope_expansion_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "detector_scope_expansion_attempt")["response_decision"] == "terminal_block"


def test_template_enabled_without_approval_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "command_template_enabled_without_approval")["approval_bypass"] is True


def test_network_call_attempt_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "detector_network_call_attempt_in_packet_bundle")["kill_switch_state"] == "terminal_block"


def test_broker_connection_attempt_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "detector_broker_connection_attempt_in_packet_bundle")["response_decision"] == "terminal_block"


def test_credential_request_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "credential_request")["kill_switch_state"] == "terminal_block"


def test_live_order_review_attempt_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "broker_order_review_attempt")["kill_switch_state"] == "terminal_block"


def test_live_order_placement_attempt_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "broker_order_placement_attempt")["kill_switch_state"] == "terminal_block"


def test_real_buying_power_read_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "buying_power_read")["kill_switch_state"] == "terminal_block"


def test_real_account_balance_read_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "real_account_balance_read")["response_decision"] == "terminal_block"


def test_real_sizing_logic_terminal_blocks(manual_bundle: dict[str, Any]) -> None:
    assert _block(manual_bundle, "real_sizing_logic")["auto_recovery_allowed"] is False


def test_read_only_detector_scope_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert READ_ONLY_DETECTOR_SCOPE_PATH.exists()


def test_manual_approval_gate_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert MANUAL_APPROVAL_GATE_PATH.exists()


def test_read_only_detector_approval_packet_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH.exists()


def test_operator_acknowledgement_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH.exists()


def test_future_detector_command_templates_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert FUTURE_DETECTOR_COMMAND_TEMPLATES_PATH.exists()


def test_manual_gate_validation_results_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert MANUAL_GATE_VALIDATION_RESULTS_PATH.exists()


def test_manual_approval_boundary_blocks_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert MANUAL_APPROVAL_BOUNDARY_BLOCKS_PATH.exists()


def test_manual_approval_packet_summary_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert MANUAL_APPROVAL_PACKET_SUMMARY_PATH.exists()


def test_manual_approval_packet_proof_artifact_written(manual_bundle: dict[str, Any]) -> None:
    assert MANUAL_APPROVAL_PACKET_PROOF_PATH.exists()


def test_audit_recognizes_manual_approval_packet_artifacts() -> None:
    artifact_types = {record[0] for record in ARTIFACT_SPECS}
    assert "manual_approval_packet_summary" in artifact_types
    assert "manual_approval_packet_proof" in artifact_types


def test_audit_confirms_approval_not_present(manual_bundle: dict[str, Any]) -> None:
    assert audit_manual_approval_packet_summary(manual_bundle["summary"]) == []


def test_audit_confirms_detector_not_approved_now(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["detector_approved_now"] is False


def test_audit_confirms_command_templates_disabled(manual_bundle: dict[str, Any]) -> None:
    assert all(audit_future_detector_command_template(record) == [] for record in manual_bundle["templates"])


def test_audit_flags_template_with_credentials() -> None:
    assert audit_future_detector_command_template({"command_template": "python -m detector --credential", "enabled": False, "requires_manual_approval": True, "allowed_now": False})


def test_audit_flags_template_with_env() -> None:
    assert audit_future_detector_command_template({"command_template": "python -m detector --config .env", "enabled": False, "requires_manual_approval": True, "allowed_now": False})


def test_audit_flags_template_with_order_placement() -> None:
    assert audit_future_detector_command_template({"command_template": "python -m detector --place-order", "enabled": False, "requires_manual_approval": True, "allowed_now": False})


def test_audit_flags_template_with_order_cancellation() -> None:
    assert audit_future_detector_command_template({"command_template": "python -m detector --cancel-order", "enabled": False, "requires_manual_approval": True, "allowed_now": False})


def test_audit_flags_template_with_scheduler() -> None:
    assert audit_future_detector_command_template({"command_template": "python -m detector --scheduler", "enabled": False, "requires_manual_approval": True, "allowed_now": False})


def test_audit_flags_template_with_broker_connection() -> None:
    assert audit_future_detector_command_template({"command_template": "python -m detector --broker-connect", "enabled": False, "requires_manual_approval": True, "allowed_now": False})


def test_audit_flags_template_with_live_trading() -> None:
    assert audit_future_detector_command_template({"command_template": "python -m detector --enable-live", "enabled": False, "requires_manual_approval": True, "allowed_now": False})


def test_audit_confirms_next_gate_explicit_manual_approval(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["next_required_gate"] == EXPLICIT_MANUAL_APPROVAL_GATE


def test_audit_confirms_no_active_forbidden_live_decisions_after_manual_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["full_suite_timeout_recorded_as_pass"] is False


def test_reporting_includes_manual_approval_packet_summary(manual_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _manual_approval_packet_summary(evidence)["readiness_status"] == "approval_packet_ready"


def test_reporting_includes_detector_approval_status(manual_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _manual_approval_packet_summary(evidence)["detector_approved_now"] is False


def test_reporting_includes_exact_acknowledgement_requirement(manual_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert REQUIRED_OPERATOR_ACKNOWLEDGEMENT in _manual_approval_packet_summary(evidence)["operator_acknowledgement_required"]


def test_reporting_includes_disabled_command_template_status(manual_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _manual_approval_packet_summary(evidence)["command_templates_disabled"] is True


def test_export_verifier_selects_manual_approval_packet_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "manual_approval_packet_summary" in ids
    assert "read_only_detector_approval_packet" in ids


def test_export_review_includes_manual_approval_packet_summary(manual_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(
        reporting_summary={"manual_approval_packet_summary": manual_bundle["summary"]},
        shared_export_path="shared",
        safety_state={},
        export_safety_scan={},
    )
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "read-only detector dry-run fixture validator", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "approve_for_offline_review", "offline_review_only", [], [], "read-only detector dry-run fixture validator", True, True, "hash")
    text = render_executive_summary(ctx, bundle, [], decision)
    assert "Read-Only Detector Manual Approval Packet" in text


def test_manual_approval_packet_artifact_ledger_written(manual_bundle: dict[str, Any]) -> None:
    assert MANUAL_APPROVAL_LEDGER_PATH.exists()


def test_shard_plan_includes_manual_approval_packet_tests() -> None:
    plan = _manual_shard_plan()
    assert plan["split_suite_lanes"]["manual_approval_packet_tests"] == ["tests/test_read_only_detector_manual_approval_packet.py"]


def test_shard_plan_marks_manual_approval_artifact_tests_sequential() -> None:
    plan = _manual_shard_plan()
    assert "tests/test_read_only_detector_manual_approval_packet.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    plan = _manual_shard_plan()
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["live_trading_enabled"] is False


def test_robinhood_stub_still_blocks_live_after_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["credentials_created"] is False


def test_no_scheduler_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["scheduler_created"] is False


def test_no_network_market_data_dependency_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["no_real_market_data"] is True


def test_no_same_day_churn_loophole_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert "normal_same_day_round_trip" not in json.dumps(manual_bundle["summary"])


def test_no_real_capital_allocator_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["real_sizing_created"] is False


def test_no_real_buying_power_logic_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["real_buying_power_logic_created"] is False


def test_no_robinhood_mcp_integration_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["robinhood_mcp_integration_created"] is False


def test_no_broker_connection_created_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["broker_connection_created"] is False


def test_no_read_only_detector_run_by_manual_approval_packet(manual_bundle: dict[str, Any]) -> None:
    assert manual_bundle["summary"]["read_only_detector_run"] is False


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    findings = audit_blunder_integrity()
    assert not [finding for finding in findings if finding.severity == "safety_error"]


def _manual_shard_plan() -> dict[str, Any]:
    summary = {"collection": {"status": "ok", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    file_result = CommandResult(["python", "-m", "pytest", "tests/test_read_only_detector_manual_approval_packet.py", "-q"], "ok", 0, 1.0, False, False, "ok", "")
    return write_test_shard_plan(["tests/test_read_only_detector_manual_approval_packet.py"], [file_result], summary)


def test_required_case_names_present(manual_bundle: dict[str, Any]) -> None:
    assert _case(manual_bundle, "packet_ready_with_approval_missing")["expected_status"] == "packet_ready"
    assert _case(manual_bundle, "packet_does_not_approve_detector_by_itself")["detector_approved_now"] is False
    assert MANUAL_APPROVAL_REPORT_PATH.exists()
    assert broker_boundary_incident_records()
    assert build_future_detector_command_templates()
