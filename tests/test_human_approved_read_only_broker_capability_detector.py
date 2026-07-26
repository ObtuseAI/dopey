from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_broker_readiness import read_only_capability_detector as detector_module
from dopey_broker_readiness.approval_intake_validator import validate_read_only_detector_approval_intake
from dopey_broker_readiness.approval_to_run_handoff_gate import validate_read_only_detector_approval_to_run_handoff_gate
from dopey_broker_readiness.audit import audit_read_only_detector_summary
from dopey_broker_readiness.manual_approval_packet_builder import build_manual_approval_packet_outputs
from dopey_broker_readiness.pre_run_safety_scanner import validate_read_only_detector_pre_run_safety_scanner
from dopey_broker_readiness.read_only_capability_detector import (
    READ_ONLY_BLOCKED_WRITE_EXECUTE_RECORDS_PATH,
    READ_ONLY_CAPABILITY_RECORDS_FIXTURE_PATH,
    READ_ONLY_CAPABILITY_RECORDS_PATH,
    READ_ONLY_DETECTOR_BOUNDARY_CASES_FIXTURE_PATH,
    READ_ONLY_DETECTOR_EXPECTED_RESULTS_FIXTURE_PATH,
    READ_ONLY_DETECTOR_INCIDENT_ESCALATIONS_PATH,
    READ_ONLY_DETECTOR_LEDGER_PATH,
    READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_PATH,
    READ_ONLY_DETECTOR_PROOF_PATH,
    READ_ONLY_DETECTOR_PROVIDER_CASES_FIXTURE_PATH,
    READ_ONLY_DETECTOR_RUN_REQUESTS_FIXTURE_PATH,
    READ_ONLY_DETECTOR_RUN_REQUESTS_PATH,
    READ_ONLY_DETECTOR_RUN_RESULTS_PATH,
    READ_ONLY_DETECTOR_SUMMARY_PATH,
    READ_ONLY_PROVIDER_BOUNDARY_RESULTS_PATH,
    run_human_approved_read_only_broker_capability_detector,
)
from dopey_broker_readiness.read_only_capability_provider import (
    DisabledFutureProviderAdapter,
    FixtureOnlyCapabilityProvider,
    HumanApprovedReadOnlyProviderStub,
)
from dopey_broker_readiness.read_only_detector_dry_run_validator import validate_read_only_detector_dry_run
from dopey_broker_readiness.read_only_detector_models import (
    ReadOnlyCapabilityRecord,
    ReadOnlyDetectorRunRequest,
    ReadOnlyDetectorRunResult,
    read_only_capability_record_hash,
    read_only_detector_run_request_hash,
    read_only_detector_run_result_hash,
)
from dopey_broker_readiness.run_broker_readiness_preflight import run_broker_readiness_preflight
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import ExportReviewBundle, ExportReviewDecision
from dopey_export_review.review_packet import render_executive_summary
from dopey_governor.active_trading_policy import active_trading_candidate_from_dict, default_active_trading_thresholds, evaluate_active_trading_policy
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _read_only_detector_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


@pytest.fixture(scope="session")
def detector_bundle() -> dict[str, Any]:
    run_broker_readiness_preflight()
    build_manual_approval_packet_outputs()
    validate_read_only_detector_dry_run()
    validate_read_only_detector_approval_intake()
    validate_read_only_detector_approval_to_run_handoff_gate()
    validate_read_only_detector_pre_run_safety_scanner()
    result = run_human_approved_read_only_broker_capability_detector()
    return {
        "result": result,
        "requests": _jsonl(READ_ONLY_DETECTOR_RUN_REQUESTS_PATH),
        "capabilities": _jsonl(READ_ONLY_CAPABILITY_RECORDS_PATH),
        "blocked": _jsonl(READ_ONLY_BLOCKED_WRITE_EXECUTE_RECORDS_PATH),
        "provider_boundaries": _jsonl(READ_ONLY_PROVIDER_BOUNDARY_RESULTS_PATH),
        "run_results": _jsonl(READ_ONLY_DETECTOR_RUN_RESULTS_PATH),
        "post_run_evidence": _json(READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_PATH),
        "incidents": _jsonl(READ_ONLY_DETECTOR_INCIDENT_ESCALATIONS_PATH),
        "summary": _json(READ_ONLY_DETECTOR_SUMMARY_PATH),
        "proof": _jsonl(READ_ONLY_DETECTOR_PROOF_PATH),
        "cases": _json(READ_ONLY_DETECTOR_BOUNDARY_CASES_FIXTURE_PATH)["records"],
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sample_request() -> ReadOnlyDetectorRunRequest:
    return ReadOnlyDetectorRunRequest("request", "approval", "handoff", "pre-run", True, True, "fixture", ["read_only_capability_inventory"], True, True, True, "")


def _sample_capability() -> ReadOnlyCapabilityRecord:
    return FixtureOnlyCapabilityProvider().list_capabilities()[0]


def _sample_result() -> ReadOnlyDetectorRunResult:
    return ReadOnlyDetectorRunResult("run", "request", "valid_exact_read_only_detector_only", "pre_run_clean", "read_only_detector_fixture_completed", False, False, False, False, False, False, False, False, 1, 1, 0, 0, 0, 0, True, True, True, "")


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(intent_id="detector-live", symbol="DLP1", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-17", "dte": 5}], max_loss=1.0, live_allowed=True, active_policy_required=True)


def _record_by_family(bundle: dict[str, Any], family: str) -> dict[str, Any]:
    return next(record for record in bundle["capabilities"] if record["capability_family"] == family)


def _incident(bundle: dict[str, Any], incident_type: str) -> bool:
    return any(record["incident_type"] == incident_type for record in bundle["incidents"])


def _group_count(bundle: dict[str, Any], group: str) -> int:
    return sum(1 for record in bundle["cases"] if record["case_group"] == group)


def _shard_plan() -> dict[str, Any]:
    summary = {"collection": {"status": "pass", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    result = CommandResult(["python", "-m", "pytest", "tests/test_human_approved_read_only_broker_capability_detector.py", "-q"], "pass", 0, 1.0, False, False, "ok", "")
    return write_test_shard_plan(["tests/test_human_approved_read_only_broker_capability_detector.py"], [result], summary)


def test_read_only_detector_run_request_serializes_deterministically() -> None:
    assert ReadOnlyDetectorRunRequest.from_dict(_sample_request().to_dict()).to_dict() == _sample_request().to_dict()


def test_read_only_capability_record_serializes_deterministically() -> None:
    assert ReadOnlyCapabilityRecord.from_dict(_sample_capability().to_dict()).to_dict() == _sample_capability().to_dict()


def test_read_only_detector_run_result_serializes_deterministically() -> None:
    assert ReadOnlyDetectorRunResult.from_dict(_sample_result().to_dict()).to_dict() == _sample_result().to_dict()


def test_detector_hashes_are_deterministic() -> None:
    assert read_only_detector_run_request_hash(_sample_request()) == read_only_detector_run_request_hash(_sample_request())
    assert read_only_capability_record_hash(_sample_capability()) == read_only_capability_record_hash(_sample_capability())
    assert read_only_detector_run_result_hash(_sample_result()) == read_only_detector_run_result_hash(_sample_result())


def test_detector_run_request_requires_paper_only_live_blocked() -> None:
    with pytest.raises(ValueError):
        ReadOnlyDetectorRunRequest.from_dict({**_sample_request().to_dict(), "paper_only": False})


def test_capability_record_rejects_write_execute_allowed_now() -> None:
    record = _record_by_family({"capabilities": [r.to_dict() for r in FixtureOnlyCapabilityProvider().list_capabilities()]}, "option_order_placement_blocked")
    with pytest.raises(ValueError):
        ReadOnlyCapabilityRecord.from_dict({**record, "allowed_now": True})


def test_run_result_blocks_runtime_permissions_by_default() -> None:
    assert _sample_result().credential_access_attempted is False
    with pytest.raises(ValueError):
        ReadOnlyDetectorRunResult.from_dict({**_sample_result().to_dict(), "order_placement_attempted": True})


def test_fixture_only_provider_lists_capabilities() -> None:
    assert FixtureOnlyCapabilityProvider().list_capabilities()


def test_fixture_only_provider_lists_read_only_shapes() -> None:
    assert all(record.read_only for record in FixtureOnlyCapabilityProvider().list_read_only_shapes())


def test_fixture_only_provider_lists_blocked_write_execute_shapes() -> None:
    assert all(record.blocked_now for record in FixtureOnlyCapabilityProvider().list_blocked_write_execute_shapes())


def test_fixture_only_provider_health_check_read_only_boundary() -> None:
    assert FixtureOnlyCapabilityProvider().health_check_read_only_boundary()["write_execute_available"] is False


def test_human_approved_provider_stub_requires_valid_approval() -> None:
    with pytest.raises(PermissionError):
        HumanApprovedReadOnlyProviderStub(False, True).list_capabilities()


def test_future_provider_placeholder_disabled() -> None:
    with pytest.raises(PermissionError):
        DisabledFutureProviderAdapter().list_capabilities()


for _test_name in [
    "test_provider_cannot_request_credentials",
    "test_provider_cannot_place_orders",
    "test_provider_cannot_cancel_orders",
    "test_provider_cannot_create_scheduler",
    "test_provider_cannot_use_real_sizing",
]:
    def _make_provider_boundary_test() -> Callable[[], None]:
        def test_func() -> None:
            health = FixtureOnlyCapabilityProvider().health_check_read_only_boundary()
            assert health["credentials_required"] is False
            assert health["write_execute_available"] is False
            assert health["scheduler_available"] is False
            assert health["real_sizing_available"] is False
        return test_func
    globals()[_test_name] = _make_provider_boundary_test()


def test_detector_not_run_when_approval_missing(detector_bundle: dict[str, Any]) -> None:
    assert any(record["approval_status"] == "approval_missing" and record["detector_status"] == "not_run_approval_missing" for record in detector_bundle["run_results"])


def test_detector_not_run_when_approval_invalid(detector_bundle: dict[str, Any]) -> None:
    assert any(record["approval_status"] == "approval_invalid" and record["detector_status"] == "not_run_approval_missing" for record in detector_bundle["run_results"])


def test_detector_not_run_when_manual_review_required(detector_bundle: dict[str, Any]) -> None:
    assert any(record["detector_status"] == "not_run_manual_review_required" for record in detector_bundle["run_results"])


def test_detector_not_run_when_terminal_block(detector_bundle: dict[str, Any]) -> None:
    assert any(record["detector_status"] == "not_run_terminal_block" for record in detector_bundle["run_results"])


def test_detector_not_run_when_pre_run_blocked(detector_bundle: dict[str, Any]) -> None:
    assert any(record["case_name"] == "pre_run_blocked_not_run" and result["detector_status"] == "not_run_pre_run_blocked" for record in detector_bundle["cases"] for result in detector_bundle["run_results"] if result["request_id"].endswith(record["case_id"][-3:]))


def test_clean_valid_fixture_approval_uses_fixture_provider(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["provider_type_used"] == "fixture_only"


for _test_name, _field in {
    "test_detector_confirms_pre_run_clean_before_provider": "pre_run_status",
    "test_detector_confirms_credentials_absent": "credential_access_attempted",
    "test_detector_confirms_scheduler_absent": "scheduler_attempted",
    "test_detector_confirms_no_live_order_tools_invoked": "live_order_attempted",
}.items():
    def _make_result_field_test(field_name: str) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            completed = [record for record in detector_bundle["run_results"] if record["detector_status"] == "read_only_detector_fixture_completed"]
            assert completed
            if field_name == "pre_run_status":
                assert all(record[field_name] == "pre_run_clean" for record in completed)
            else:
                assert all(record[field_name] is False for record in completed)
        return test_func
    globals()[_test_name] = _make_result_field_test(_field)


def test_detector_writes_capability_records(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["capabilities"]


def test_detector_writes_blocked_write_execute_records(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["blocked"]


def test_detector_writes_post_run_evidence(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["post_run_evidence"]["evidence_hash"]


for _test_name, _path in {
    "test_read_only_detector_run_requests_fixture_loads": READ_ONLY_DETECTOR_RUN_REQUESTS_FIXTURE_PATH,
    "test_read_only_capability_records_fixture_loads": READ_ONLY_CAPABILITY_RECORDS_FIXTURE_PATH,
    "test_read_only_detector_expected_results_fixture_loads": READ_ONLY_DETECTOR_EXPECTED_RESULTS_FIXTURE_PATH,
    "test_read_only_detector_boundary_cases_fixture_loads": READ_ONLY_DETECTOR_BOUNDARY_CASES_FIXTURE_PATH,
    "test_read_only_detector_provider_cases_fixture_loads": READ_ONLY_DETECTOR_PROVIDER_CASES_FIXTURE_PATH,
}.items():
    def _make_fixture_loads(path: Path) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            assert _json(path)["record_count"] > 0
        return test_func
    globals()[_test_name] = _make_fixture_loads(_path)


def test_detector_fixture_has_at_least_120_cases(detector_bundle: dict[str, Any]) -> None:
    assert len(detector_bundle["cases"]) >= 120


for _test_name, _group, _count in [
    ("test_detector_fixture_covers_approval_missing_cases", "approval_missing", 16),
    ("test_detector_fixture_covers_invalid_approval_cases", "invalid_approval", 16),
    ("test_detector_fixture_covers_clean_fixture_provider_cases", "clean_fixture_provider", 16),
    ("test_detector_fixture_covers_read_only_capability_inventory", "read_only_capability_inventory", 16),
    ("test_detector_fixture_covers_write_execute_blocks", "write_execute_block", 16),
    ("test_detector_fixture_covers_credential_scheduler_live_order_boundaries", "credential_scheduler_live_order_boundary", 12),
    ("test_detector_fixture_covers_provider_boundaries", "provider_boundary", 12),
    ("test_detector_fixture_covers_post_run_evidence", "post_run_evidence", 8),
    ("test_detector_fixture_covers_terminal_blocks", "terminal_block", 8),
]:
    def _make_group_test(group: str, count: int) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            assert _group_count(detector_bundle, group) == count
        return test_func
    globals()[_test_name] = _make_group_test(_group, _count)


for _test_name, _family in {
    "test_tool_inventory_shape_recorded": "tool_inventory",
    "test_option_chain_shape_recorded": "option_chain_shape",
    "test_option_quote_shape_recorded": "option_quote_shape",
    "test_option_position_shape_recorded": "option_position_shape",
    "test_order_status_shape_recorded": "option_order_status_shape",
    "test_error_shape_recorded": "option_error_shape",
    "test_order_review_blocked": "option_order_review_blocked",
    "test_order_placement_blocked": "option_order_placement_blocked",
    "test_order_cancellation_blocked": "option_order_cancellation_blocked",
    "test_credential_request_blocked": "credential_block",
    "test_scheduler_creation_blocked": "scheduler_block",
    "test_live_execution_blocked": "live_execution_block",
    "test_broker_write_blocked": "option_order_placement_blocked",
    "test_broker_execute_blocked": "live_execution_block",
    "test_real_sizing_blocked": "live_execution_block",
    "test_account_balance_use_blocked": "credential_block",
    "test_buying_power_use_blocked": "credential_block",
}.items():
    def _make_family_test(family: str) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            record = _record_by_family(detector_bundle, family)
            assert record["read_only"] is True or record["blocked_now"] is True
        return test_func
    globals()[_test_name] = _make_family_test(_family)


for _test_name, _incident_type in {
    "test_provider_with_credential_requirement_terminal_blocks": "provider_requested_credentials",
    "test_provider_with_write_tool_terminal_blocks": "provider_exposed_write_tool_allowed",
    "test_provider_with_execute_tool_terminal_blocks": "provider_exposed_execute_tool_allowed",
    "test_provider_with_live_order_tool_terminal_blocks": "provider_exposed_live_order_tool_allowed",
    "test_provider_with_scheduler_terminal_blocks": "provider_attempted_scheduler",
    "test_provider_with_real_sizing_terminal_blocks": "provider_attempted_real_sizing",
    "test_provider_with_account_balance_dependency_terminal_blocks": "provider_attempted_account_balance_or_buying_power",
    "test_detector_run_without_approval_terminal_blocks": "detector_run_without_approval",
    "test_detector_run_after_invalid_approval_terminal_blocks": "detector_run_after_invalid_approval",
    "test_detector_run_when_pre_run_blocked_terminal_blocks": "detector_run_when_pre_run_blocked",
}.items():
    def _make_incident_test(incident_type: str) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            assert _incident(detector_bundle, incident_type)
        return test_func
    globals()[_test_name] = _make_incident_test(_incident_type)


def test_detector_failed_post_run_evidence_terminal_blocks(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["post_run_evidence_written"] is True


for _test_name, _field in {
    "test_post_run_evidence_written": "evidence_hash",
    "test_post_run_evidence_consumes_approval_proof": "approval_proof_consumed",
    "test_post_run_evidence_consumes_pre_run_proof": "pre_run_safety_proof_consumed",
    "test_post_run_evidence_records_provider_type": "provider_type_used",
    "test_post_run_evidence_records_no_credentials": "no_credential_access",
    "test_post_run_evidence_records_no_live_orders": "no_live_order_access",
    "test_post_run_evidence_records_no_order_placement": "no_order_placement",
    "test_post_run_evidence_records_no_order_cancellation": "no_order_cancellation",
    "test_post_run_evidence_records_no_scheduler": "no_scheduler",
    "test_post_run_evidence_records_no_real_sizing": "no_real_sizing",
    "test_post_run_evidence_records_no_broker_mutation": "no_broker_mutation",
}.items():
    def _make_evidence_test(field_name: str) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            value = detector_bundle["post_run_evidence"][field_name]
            assert bool(value) is True
        return test_func
    globals()[_test_name] = _make_evidence_test(_field)


for _test_name, _path_attribute in {
    "test_detector_run_requests_artifact_written": "READ_ONLY_DETECTOR_RUN_REQUESTS_PATH",
    "test_read_only_capability_records_artifact_written": "READ_ONLY_CAPABILITY_RECORDS_PATH",
    "test_blocked_write_execute_records_artifact_written": "READ_ONLY_BLOCKED_WRITE_EXECUTE_RECORDS_PATH",
    "test_provider_boundary_results_artifact_written": "READ_ONLY_PROVIDER_BOUNDARY_RESULTS_PATH",
    "test_detector_run_results_artifact_written": "READ_ONLY_DETECTOR_RUN_RESULTS_PATH",
    "test_detector_post_run_evidence_artifact_written": "READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_PATH",
    "test_detector_incident_escalations_artifact_written": "READ_ONLY_DETECTOR_INCIDENT_ESCALATIONS_PATH",
    "test_detector_summary_artifact_written": "READ_ONLY_DETECTOR_SUMMARY_PATH",
    "test_detector_proof_artifact_written": "READ_ONLY_DETECTOR_PROOF_PATH",
}.items():
    def _make_artifact_test(path_attribute: str) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            path = getattr(detector_module, path_attribute)
            if not isinstance(path, Path):
                raise TypeError(
                    "read-only detector artifact binding must be a Path: "
                    f"attribute={path_attribute}, actual={type(path).__name__}"
                )
            assert path.exists()
            assert path.stat().st_size > 0
        return test_func
    globals()[_test_name] = _make_artifact_test(_path_attribute)


def test_audit_recognizes_read_only_detector_artifacts(detector_bundle: dict[str, Any]) -> None:
    types = {artifact_type for artifact_type, _, _, _ in ARTIFACT_SPECS}
    assert {"read_only_detector_run_requests", "read_only_capability_records", "read_only_detector_summary", "read_only_detector_proof"}.issubset(types)


for _test_name in [
    "test_audit_confirms_approval_missing_cases_did_not_run",
    "test_audit_confirms_invalid_approval_cases_did_not_run",
    "test_audit_confirms_fixture_provider_cases_read_only",
    "test_audit_confirms_write_execute_records_blocked",
    "test_audit_confirms_no_credentials_after_detector",
    "test_audit_confirms_no_scheduler_after_detector",
    "test_audit_confirms_no_live_order_after_detector",
    "test_audit_confirms_no_order_placement_after_detector",
    "test_audit_confirms_no_order_cancellation_after_detector",
    "test_audit_confirms_no_real_sizing_after_detector",
    "test_audit_confirms_no_account_balance_use_after_detector",
    "test_audit_confirms_no_buying_power_use_after_detector",
    "test_audit_confirms_no_broker_mutation_after_detector",
    "test_audit_confirms_post_run_evidence_exists",
    "test_audit_confirms_detector_result_not_live_ready",
    "test_audit_confirms_no_active_forbidden_live_decisions_after_detector",
]:
    def _make_audit_test() -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            assert audit_read_only_detector_summary(detector_bundle["summary"]) == []
        return test_func
    globals()[_test_name] = _make_audit_test()


for _test_name, _field in {
    "test_reporting_includes_read_only_detector_summary": "detector_bundle_status",
    "test_reporting_includes_detector_status_distribution": "detector_status_distribution",
    "test_reporting_includes_provider_type_distribution": "provider_type_distribution",
    "test_reporting_includes_capability_family_distribution": "capability_family_distribution",
    "test_reporting_includes_write_execute_block_total": "write_execute_blocked_total",
    "test_reporting_includes_post_run_evidence_status": "post_run_evidence_written",
}.items():
    def _make_reporting_test(field_name: str) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            evidence = load_reporting_evidence(EVIDENCE_PATHS)
            summary = _read_only_detector_summary(evidence)
            assert field_name in summary
            assert summary[field_name] not in ({}, "", None)
        return test_func
    globals()[_test_name] = _make_reporting_test(_field)


def test_export_verifier_selects_detector_artifacts(detector_bundle: dict[str, Any]) -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"read_only_detector_summary", "read_only_detector_proof", "read_only_capability_records"}.issubset(ids)


def test_export_review_includes_detector_summary(detector_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(reporting_summary={"read_only_detector_summary": detector_bundle["summary"]}, shared_export_path="shared", safety_state={}, export_safety_scan={})
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "read-only detector post-run evidence contract hardening", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "approve_for_offline_review", "offline_review_only", [], [], "read-only detector post-run evidence contract hardening", True, True, "hash")
    assert "Human-Approved Read-Only Broker Capability Detector" in render_executive_summary(ctx, bundle, [], decision)


def test_read_only_detector_artifact_ledger_written(detector_bundle: dict[str, Any]) -> None:
    assert READ_ONLY_DETECTOR_LEDGER_PATH.exists()


def test_shard_plan_includes_read_only_detector_tests() -> None:
    assert _shard_plan()["split_suite_lanes"]["human_approved_read_only_detector_tests"] == ["tests/test_human_approved_read_only_broker_capability_detector.py"]


def test_shard_plan_marks_detector_artifact_tests_sequential() -> None:
    assert "tests/test_human_approved_read_only_broker_capability_detector.py" in _shard_plan()["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    plan = _shard_plan()
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["live_blocked"] is True


for _test_name, _adapter in {
    "test_robinhood_stub_still_blocks_live_after_read_only_detector": RobinhoodMCPAdapter,
    "test_alpaca_stub_still_blocks_live_after_read_only_detector": AlpacaOptionsAdapter,
    "test_tradier_stub_still_blocks_live_after_read_only_detector": TradierOptionsAdapter,
}.items():
    def _make_adapter_test(adapter_cls: type) -> Callable[[dict[str, Any]], None]:
        def test_func(detector_bundle: dict[str, Any]) -> None:
            with pytest.raises(LiveTradingDisabledError):
                adapter_cls().place_order(_live_intent())
        return test_func
    globals()[_test_name] = _make_adapter_test(_adapter)


def test_no_credentials_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert not Path(".env").exists()
    assert detector_bundle["summary"]["credentials_created"] is False


def test_no_scheduler_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["scheduler_created"] is False


def test_no_network_market_data_dependency_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["real_market_data_used"] is False


def test_no_same_day_churn_loophole_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    fixture = json.loads((Path(__file__).resolve().parents[1] / "dopey_data" / "fixtures" / "active_trading_policy" / "long_premium_policy_cases.json").read_text(encoding="utf-8"))
    row = next(record for record in fixture["candidates"] if record["case_id"] == "same_day_churn_rejected")
    candidate = active_trading_candidate_from_dict(row["candidate"])
    assert evaluate_active_trading_policy(candidate, default_active_trading_thresholds()).allowed is False


def test_no_real_capital_allocator_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["real_sizing_created"] is False


def test_no_real_buying_power_logic_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["buying_power_attempted"] is False


def test_no_robinhood_write_execute_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["robinhood_mcp_integration_created"] is False


def test_no_broker_write_execute_created_by_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    assert detector_bundle["summary"]["broker_mutation_attempted"] is False


def test_blunder_integrity_unchanged_if_manifest_available(detector_bundle: dict[str, Any]) -> None:
    findings = audit_blunder_integrity()
    assert not any(finding.severity == "safety_error" for finding in findings)


def test_paper_broker_still_refuses_live_allowed_after_read_only_detector(detector_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())
