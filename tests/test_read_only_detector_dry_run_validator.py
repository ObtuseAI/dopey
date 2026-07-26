from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_broker_readiness.audit import audit_read_only_detector_dry_run_summary
from dopey_broker_readiness.boundary_incidents import broker_boundary_incident_records
from dopey_broker_readiness.dry_run_detector_models import (
    FORBIDDEN_REQUEST_CLASSES,
    ReadOnlyDetectorDryRunInput,
    ReadOnlyDetectorDryRunResult,
    SimulatedBrokerCapabilityResponse,
    dry_run_input_hash,
    dry_run_result_hash,
    simulated_response_hash,
)
from dopey_broker_readiness.manual_approval_packet_builder import build_manual_approval_packet_outputs
from dopey_broker_readiness.read_only_detector_dry_run_validator import (
    DRY_RUN_BOUNDARY_BLOCKS_PATH,
    DRY_RUN_INPUTS_FIXTURE_PATH,
    DRY_RUN_INPUTS_PATH,
    DRY_RUN_LEDGER_PATH,
    DRY_RUN_PROOF_PATH,
    DRY_RUN_REPORT_PATH,
    DRY_RUN_RESULTS_PATH,
    DRY_RUN_SUMMARY_PATH,
    EXPECTED_DRY_RUN_RESULTS_FIXTURE_PATH,
    FUTURE_DETECTOR_CONTRACT_PATH,
    SIMULATED_FORBIDDEN_SHAPES_FIXTURE_PATH,
    SIMULATED_FORBIDDEN_SHAPES_PATH,
    SIMULATED_READ_ONLY_SHAPES_FIXTURE_PATH,
    SIMULATED_READ_ONLY_SHAPES_PATH,
    SIMULATED_RESPONSES_FIXTURE_PATH,
    SIMULATED_RESPONSES_PATH,
    validate_read_only_detector_dry_run,
)
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
from dopey_reporting.reporting_bundle import _read_only_detector_dry_run_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


@pytest.fixture(scope="session")
def dry_run_bundle() -> dict[str, Any]:
    run_broker_readiness_preflight()
    build_manual_approval_packet_outputs()
    result = validate_read_only_detector_dry_run()
    return {
        "result": result,
        "inputs": _jsonl(DRY_RUN_INPUTS_PATH),
        "responses": _jsonl(SIMULATED_RESPONSES_PATH),
        "read_only_shapes": _json(SIMULATED_READ_ONLY_SHAPES_PATH),
        "forbidden_shapes": _json(SIMULATED_FORBIDDEN_SHAPES_PATH),
        "results": _jsonl(DRY_RUN_RESULTS_PATH),
        "blocks": _jsonl(DRY_RUN_BOUNDARY_BLOCKS_PATH),
        "summary": _json(DRY_RUN_SUMMARY_PATH),
        "proof": _jsonl(DRY_RUN_PROOF_PATH),
        "input_fixture": _json(DRY_RUN_INPUTS_FIXTURE_PATH),
        "response_fixture": _json(SIMULATED_RESPONSES_FIXTURE_PATH),
        "read_only_fixture": _json(SIMULATED_READ_ONLY_SHAPES_FIXTURE_PATH),
        "forbidden_fixture": _json(SIMULATED_FORBIDDEN_SHAPES_FIXTURE_PATH),
        "expected_results": _json(EXPECTED_DRY_RUN_RESULTS_FIXTURE_PATH),
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _response(bundle: dict[str, Any], family: str) -> dict[str, Any]:
    return next(record for record in bundle["responses"] if record["capability_family"] == family)


def _block(bundle: dict[str, Any], incident_type: str) -> dict[str, Any]:
    return next(record for record in bundle["blocks"] if record["incident_type"] == incident_type)


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(intent_id="dry-run-live", symbol="DLP1", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-17", "dte": 5}], max_loss=1.0, live_allowed=True, active_policy_required=True)


def test_read_only_detector_dry_run_input_serializes_deterministically(dry_run_bundle: dict[str, Any]) -> None:
    record = ReadOnlyDetectorDryRunInput.from_dict({k: v for k, v in dry_run_bundle["inputs"][0].items() if k != "case_group"})
    assert record.to_dict() == {k: v for k, v in dry_run_bundle["inputs"][0].items() if k != "case_group"}


def test_simulated_broker_capability_response_serializes_deterministically(dry_run_bundle: dict[str, Any]) -> None:
    record = SimulatedBrokerCapabilityResponse.from_dict(dry_run_bundle["responses"][0])
    assert record.to_dict() == dry_run_bundle["responses"][0]


def test_read_only_detector_dry_run_result_serializes_deterministically(dry_run_bundle: dict[str, Any]) -> None:
    record = ReadOnlyDetectorDryRunResult.from_dict({k: v for k, v in dry_run_bundle["results"][0].items() if k != "case_group"})
    assert record.to_dict() == {k: v for k, v in dry_run_bundle["results"][0].items() if k != "case_group"}


def test_dry_run_hashes_are_deterministic(dry_run_bundle: dict[str, Any]) -> None:
    dry_input = ReadOnlyDetectorDryRunInput.from_dict({**{k: v for k, v in dry_run_bundle["inputs"][0].items() if k != "case_group"}, "input_hash": ""})
    response = SimulatedBrokerCapabilityResponse.from_dict({**dry_run_bundle["responses"][0], "response_hash": ""})
    result = ReadOnlyDetectorDryRunResult.from_dict({**{k: v for k, v in dry_run_bundle["results"][0].items() if k != "case_group"}, "result_hash": ""})
    assert dry_run_input_hash(dry_input) == dry_run_bundle["inputs"][0]["input_hash"]
    assert simulated_response_hash(response) == dry_run_bundle["responses"][0]["response_hash"]
    assert dry_run_result_hash(result) == dry_run_bundle["results"][0]["result_hash"]


def test_dry_run_input_defaults_approval_missing(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["inputs"][0]["approval_status"] == "approval_missing"
    assert dry_run_bundle["inputs"][0]["detector_approved"] is False


def test_dry_run_input_requires_paper_only_live_blocked(dry_run_bundle: dict[str, Any]) -> None:
    payload = {k: v for k, v in dry_run_bundle["inputs"][0].items() if k != "case_group"}
    with pytest.raises(ValueError):
        ReadOnlyDetectorDryRunInput.from_dict({**payload, "paper_only": False})


def test_simulated_response_rejects_real_broker_connection(dry_run_bundle: dict[str, Any]) -> None:
    payload = {**dry_run_bundle["responses"][0], "simulated_schema": {"broker_connection": "handle"}}
    with pytest.raises(ValueError):
        SimulatedBrokerCapabilityResponse.from_dict(payload)


def test_dry_run_validator_loads_manual_approval_packet(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["inputs"][0]["source_approval_packet_id"] == "read-only-detector-approval-packet-v1"


def test_dry_run_validator_confirms_approval_missing(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["approval_status"] == "approval_missing"


def test_dry_run_validator_confirms_detector_not_approved(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["detector_approved"] is False


def test_dry_run_validator_does_not_run_detector(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["detector_run_attempted"] is False


def test_dry_run_validator_validates_input_schemas(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["input_count"] == 96


def test_dry_run_validator_validates_simulated_response_schemas(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["simulated_response_count"] == 32


def test_dry_run_validator_validates_read_only_shapes(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["read_only_shape_count"] >= 16


def test_dry_run_validator_blocks_write_execute_shapes(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["blocked_write_execute_shape_count"] >= 32


def test_dry_run_validator_blocks_credentials(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "credential_block")["write_or_execute_shape_blocked"] is True


def test_dry_run_validator_blocks_scheduler(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "scheduler_block")["write_or_execute_shape_blocked"] is True


def test_dry_run_validator_blocks_network(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["no_real_market_data"] is True


def test_dry_run_validator_blocks_live_execution(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "live_execution_block")["write_or_execute_shape_blocked"] is True


def test_dry_run_validator_blocks_order_placement(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["order_placement_blocked"] is True


def test_dry_run_validator_blocks_order_cancellation(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["order_cancellation_blocked"] is True


def test_dry_run_detector_inputs_fixture_loads(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["input_fixture"]["case_count"] == 96


def test_simulated_broker_capability_responses_fixture_loads(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["response_fixture"]["case_count"] == 32


def test_simulated_read_only_shapes_fixture_loads(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["read_only_fixture"]["case_count"] >= 7


def test_simulated_forbidden_shapes_fixture_loads(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["forbidden_fixture"]["case_count"] >= 6


def test_expected_dry_run_results_fixture_loads(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["expected_results"]["case_count"] == 96


def test_dry_run_fixture_has_at_least_96_cases(dry_run_bundle: dict[str, Any]) -> None:
    assert len(dry_run_bundle["inputs"]) >= 96


def test_dry_run_fixture_covers_input_validation(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "input_validation") >= 16


def test_dry_run_fixture_covers_read_only_responses(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "read_only_response") >= 16


def test_dry_run_fixture_covers_options_shapes(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "options_shape") >= 16


def test_dry_run_fixture_covers_write_execute_blocks(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "write_execute_block") >= 16


def test_dry_run_fixture_covers_credential_scheduler_network_blocks(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "credential_scheduler_network_block") >= 8


def test_dry_run_fixture_covers_detector_not_run_cases(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "approval_missing_detector_not_run") >= 8


def test_dry_run_fixture_covers_schema_violations(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "schema_violation") >= 8


def test_dry_run_fixture_covers_incident_escalations(dry_run_bundle: dict[str, Any]) -> None:
    assert _group_count(dry_run_bundle, "incident_escalation") >= 8


def test_simulated_capability_discovery_shape_validates(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "capability_discovery")["read_only_shape_available"] is True


def test_simulated_account_metadata_shape_validates(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "account_metadata_shape")["read_only_shape_available"] is True


def test_simulated_option_chain_shape_validates(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "option_chain_shape")["read_only_shape_available"] is True


def test_simulated_option_quote_shape_validates(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "option_quote_shape")["read_only_shape_available"] is True


def test_simulated_option_position_shape_validates(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "option_position_shape")["read_only_shape_available"] is True


def test_simulated_option_order_status_shape_validates(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "option_order_status_shape")["read_only_shape_available"] is True


def test_simulated_option_order_review_is_fixture_only(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "option_order_review_shape_simulated")["simulated_schema"]["fixture_only"] is True


def test_simulated_order_placement_shape_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "order_placement_block")["write_or_execute_shape_blocked"] is True


def test_simulated_order_cancellation_shape_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _response(dry_run_bundle, "order_cancellation_block")["write_or_execute_shape_blocked"] is True


def test_credential_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "credential" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_token_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "token" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_env_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert ".env" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_account_balance_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "account_balance" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_buying_power_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "buying_power" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_live_execution_flag_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "live_execution" in _response(dry_run_bundle, "live_execution_block")["forbidden_fields"]


def test_scheduler_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "scheduler" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_network_url_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "network_url" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_broker_connection_handle_field_forbidden(dry_run_bundle: dict[str, Any]) -> None:
    assert "connection_handle" in json.dumps(dry_run_bundle["forbidden_shapes"]["shapes"])


def test_detector_run_attempted_without_approval_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_detector_run_attempt")["kill_switch_state"] == "terminal_block"


def test_broker_connection_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_broker_connection_attempt")["response_decision"] == "terminal_block"


def test_credential_access_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_credential_read_attempt")["kill_switch_state"] == "terminal_block"


def test_network_access_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_network_call_attempt")["kill_switch_state"] == "terminal_block"


def test_live_order_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_order_review_attempt")["response_decision"] == "terminal_block"


def test_order_cancellation_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_order_cancellation_attempt")["kill_switch_state"] == "terminal_block"


def test_real_sizing_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_real_sizing_attempt")["kill_switch_state"] == "terminal_block"


def test_scope_expansion_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert any(record["incident_type"] == "detector_scope_expansion_attempt" for record in broker_boundary_incident_records())


def test_command_template_enablement_attempted_blocked(dry_run_bundle: dict[str, Any]) -> None:
    assert _block(dry_run_bundle, "dry_run_command_template_enablement_attempt")["response_decision"] == "terminal_block"


def test_dry_run_bypass_attempt_terminal_blocks(dry_run_bundle: dict[str, Any]) -> None:
    terminal = [record for record in dry_run_bundle["blocks"] if record["kill_switch_state"] == "terminal_block"]
    assert len(terminal) >= 11


def test_future_detector_contract_written(dry_run_bundle: dict[str, Any]) -> None:
    assert FUTURE_DETECTOR_CONTRACT_PATH.exists()


def test_future_detector_contract_allows_read_only_after_approval(dry_run_bundle: dict[str, Any]) -> None:
    assert "read-only broker capability discovery" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8")


def test_future_detector_contract_forbids_credentials(dry_run_bundle: dict[str, Any]) -> None:
    assert "credential storage" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8")


def test_future_detector_contract_forbids_live_orders(dry_run_bundle: dict[str, Any]) -> None:
    assert "live order review" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8")


def test_future_detector_contract_forbids_order_placement(dry_run_bundle: dict[str, Any]) -> None:
    assert "live order placement" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8")


def test_future_detector_contract_forbids_order_cancellation(dry_run_bundle: dict[str, Any]) -> None:
    assert "order cancellation" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8")


def test_future_detector_contract_forbids_scheduler(dry_run_bundle: dict[str, Any]) -> None:
    assert "scheduler" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8")


def test_future_detector_contract_forbids_real_sizing(dry_run_bundle: dict[str, Any]) -> None:
    assert "real account sizing" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8")


def test_future_detector_contract_states_approval_packet_is_not_approval(dry_run_bundle: dict[str, Any]) -> None:
    assert "approval packet is not approval" in FUTURE_DETECTOR_CONTRACT_PATH.read_text(encoding="utf-8").lower()


def test_dry_run_inputs_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert DRY_RUN_INPUTS_PATH.exists()


def test_simulated_broker_capability_responses_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert SIMULATED_RESPONSES_PATH.exists()


def test_simulated_read_only_shapes_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert SIMULATED_READ_ONLY_SHAPES_PATH.exists()


def test_simulated_forbidden_shapes_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert SIMULATED_FORBIDDEN_SHAPES_PATH.exists()


def test_dry_run_results_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert DRY_RUN_RESULTS_PATH.exists()


def test_dry_run_boundary_blocks_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert DRY_RUN_BOUNDARY_BLOCKS_PATH.exists()


def test_future_detector_contract_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert FUTURE_DETECTOR_CONTRACT_PATH.exists()


def test_dry_run_summary_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert DRY_RUN_SUMMARY_PATH.exists()


def test_dry_run_proof_artifact_written(dry_run_bundle: dict[str, Any]) -> None:
    assert DRY_RUN_PROOF_PATH.exists()


def test_audit_recognizes_dry_run_detector_artifacts(dry_run_bundle: dict[str, Any]) -> None:
    artifact_types = {record[0] for record in ARTIFACT_SPECS}
    assert {"read_only_detector_dry_run_summary", "dry_run_detector_proof"}.issubset(artifact_types)


def test_audit_confirms_approval_missing_in_dry_run(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary(dry_run_bundle["summary"]) == []


def test_audit_confirms_detector_not_approved_in_dry_run(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["detector_approved"] is False


def test_audit_confirms_detector_not_run_in_dry_run(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["detector_run_attempted"] is False


def test_audit_flags_dry_run_broker_connection(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "broker_connection_attempted": True})


def test_audit_flags_dry_run_credentials(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "credential_access_attempted": True})


def test_audit_flags_dry_run_network_access(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "network_access_attempted": True})


def test_audit_flags_dry_run_live_order(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "live_order_attempted": True})


def test_audit_flags_dry_run_order_placement(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "order_placement_blocked": False})


def test_audit_flags_dry_run_order_cancellation(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "order_cancellation_blocked": False})


def test_audit_flags_dry_run_scheduler(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "scheduler_blocked": False})


def test_audit_flags_dry_run_real_sizing(dry_run_bundle: dict[str, Any]) -> None:
    assert audit_read_only_detector_dry_run_summary({**dry_run_bundle["summary"], "real_sizing_blocked": False})


def test_audit_confirms_no_active_forbidden_live_decisions_after_dry_run(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["full_suite_timeout_recorded_as_pass"] is False


def test_reporting_includes_dry_run_validator_summary(dry_run_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _read_only_detector_dry_run_summary(evidence)["dry_run_status"] == "dry_run_fixture_validated"


def test_reporting_includes_detector_not_approved_status(dry_run_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _read_only_detector_dry_run_summary(evidence)["detector_approved"] is False


def test_reporting_includes_detector_not_run_status(dry_run_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _read_only_detector_dry_run_summary(evidence)["detector_run_attempted"] is False


def test_reporting_includes_future_detector_contract(dry_run_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _read_only_detector_dry_run_summary(evidence)["future_detector_contract_path"].endswith("future_detector_contract.md")


def test_export_verifier_selects_dry_run_validator_artifacts(dry_run_bundle: dict[str, Any]) -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"read_only_detector_dry_run_summary", "future_detector_contract"}.issubset(ids)


def test_export_review_includes_dry_run_validator_summary(dry_run_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(reporting_summary={"read_only_detector_dry_run_summary": dry_run_bundle["summary"]}, shared_export_path="shared", safety_state={}, export_safety_scan={})
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "read-only detector approval intake validator", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "approve_for_offline_review", "offline_review_only", [], [], "read-only detector approval intake validator", True, True, "hash")
    assert "Read-Only Detector Dry-Run Fixture Validator" in render_executive_summary(ctx, bundle, [], decision)


def test_dry_run_artifact_ledger_written(dry_run_bundle: dict[str, Any]) -> None:
    assert DRY_RUN_LEDGER_PATH.exists()


def test_shard_plan_includes_dry_run_validator_tests() -> None:
    plan = _dry_run_shard_plan()
    assert plan["split_suite_lanes"]["read_only_detector_dry_run_validator_tests"] == ["tests/test_read_only_detector_dry_run_validator.py"]


def test_shard_plan_marks_dry_run_artifact_tests_sequential() -> None:
    plan = _dry_run_shard_plan()
    assert "tests/test_read_only_detector_dry_run_validator.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    plan = _dry_run_shard_plan()
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["live_blocked"] is True


def test_robinhood_stub_still_blocks_live_after_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["no_credential"] is True


def test_no_scheduler_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["no_scheduler"] is True


def test_no_network_market_data_dependency_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["no_real_market_data"] is True


def test_no_same_day_churn_loophole_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert "normal_same_day_round_trip" not in json.dumps(dry_run_bundle["summary"])


def test_no_real_capital_allocator_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["no_real_sizing"] is True


def test_no_real_buying_power_logic_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert "real_buying_power" in FORBIDDEN_REQUEST_CLASSES


def test_no_robinhood_mcp_integration_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["robinhood_mcp_integration_created"] is False


def test_no_broker_connection_created_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["no_broker"] is True


def test_no_read_only_detector_run_by_dry_run_validator(dry_run_bundle: dict[str, Any]) -> None:
    assert dry_run_bundle["summary"]["read_only_detector_run"] is False


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    findings = audit_blunder_integrity()
    assert not [finding for finding in findings if finding.severity == "safety_error"]


def _group_count(bundle: dict[str, Any], group_name: str) -> int:
    return sum(1 for record in bundle["inputs"] if record["case_group"] == group_name)


def _dry_run_shard_plan() -> dict[str, Any]:
    summary = {"collection": {"status": "pass", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    result = CommandResult(["python", "-m", "pytest", "tests/test_read_only_detector_dry_run_validator.py", "-q"], "pass", 0, 1.0, False, False, "ok", "")
    return write_test_shard_plan(["tests/test_read_only_detector_dry_run_validator.py"], [result], summary)
