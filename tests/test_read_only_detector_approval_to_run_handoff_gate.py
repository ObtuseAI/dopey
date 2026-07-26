from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_broker_readiness import approval_to_run_handoff_gate as handoff_module
from dopey_broker_readiness.approval_intake_validator import validate_read_only_detector_approval_intake
from dopey_broker_readiness.approval_to_run_handoff_gate import (
    APPROVAL_TO_RUN_GATE_DECISIONS_FIXTURE_PATH,
    APPROVAL_TO_RUN_GATE_DECISIONS_PATH,
    APPROVAL_TO_RUN_HANDOFF_LEDGER_PATH,
    APPROVAL_TO_RUN_HANDOFF_PROOF_PATH,
    APPROVAL_TO_RUN_HANDOFF_REPORT_PATH,
    APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH,
    DISABLED_HANDOFF_COMMAND_TEMPLATES_FIXTURE_PATH,
    DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH,
    EXPECTED_HANDOFF_SUMMARY_FIXTURE_PATH,
    FUTURE_DETECTOR_RUN_ENVELOPES_FIXTURE_PATH,
    FUTURE_DETECTOR_RUN_ENVELOPES_PATH,
    HANDOFF_BOUNDARY_BLOCKS_PATH,
    HANDOFF_INCIDENT_ESCALATIONS_PATH,
    HANDOFF_INPUTS_FIXTURE_PATH,
    HANDOFF_INPUTS_PATH,
    build_approval_to_run_gate_decisions,
    build_approval_to_run_handoff_inputs,
    build_future_detector_run_envelopes,
    load_handoff_source_snapshot,
    validate_read_only_detector_approval_to_run_handoff_gate,
)
from dopey_broker_readiness.approval_to_run_handoff_models import (
    APPROVAL_TO_RUN_NEXT_GATE,
    ApprovalToRunGateDecision,
    ApprovalToRunHandoffInput,
    FutureDetectorRunEnvelope,
    approval_to_run_gate_decision_hash,
    approval_to_run_handoff_input_hash,
    future_detector_run_envelope_hash,
)
from dopey_broker_readiness.audit import audit_approval_to_run_handoff_summary
from dopey_broker_readiness.disabled_handoff_command_registry import build_disabled_handoff_command_templates
from dopey_broker_readiness.manual_approval_packet_builder import build_manual_approval_packet_outputs
from dopey_broker_readiness.read_only_detector_dry_run_validator import validate_read_only_detector_dry_run
from dopey_broker_readiness.run_broker_readiness_preflight import run_broker_readiness_preflight
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import ExportReviewBundle, ExportReviewDecision
from dopey_export_review.review_packet import render_executive_summary, render_safety_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _approval_to_run_handoff_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


@pytest.fixture(scope="session")
def handoff_bundle() -> dict[str, Any]:
    run_broker_readiness_preflight()
    build_manual_approval_packet_outputs()
    validate_read_only_detector_dry_run()
    validate_read_only_detector_approval_intake()
    result = validate_read_only_detector_approval_to_run_handoff_gate()
    return {
        "result": result,
        "inputs": _jsonl(HANDOFF_INPUTS_PATH),
        "envelopes": _jsonl(FUTURE_DETECTOR_RUN_ENVELOPES_PATH),
        "decisions": _jsonl(APPROVAL_TO_RUN_GATE_DECISIONS_PATH),
        "templates": _jsonl(DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH),
        "blocks": _jsonl(HANDOFF_BOUNDARY_BLOCKS_PATH),
        "escalations": _jsonl(HANDOFF_INCIDENT_ESCALATIONS_PATH),
        "summary": _json(APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH),
        "proof": _jsonl(APPROVAL_TO_RUN_HANDOFF_PROOF_PATH),
        "input_fixture": _json(HANDOFF_INPUTS_FIXTURE_PATH),
        "envelope_fixture": _json(FUTURE_DETECTOR_RUN_ENVELOPES_FIXTURE_PATH),
        "decision_fixture": _json(APPROVAL_TO_RUN_GATE_DECISIONS_FIXTURE_PATH),
        "template_fixture": _json(DISABLED_HANDOFF_COMMAND_TEMPLATES_FIXTURE_PATH),
        "expected_summary": _json(EXPECTED_HANDOFF_SUMMARY_FIXTURE_PATH),
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _decision(bundle: dict[str, Any], case_group: str) -> dict[str, Any]:
    return next(record for record in bundle["decisions"] if record["case_group"] == case_group)


def _input(bundle: dict[str, Any], case_group: str) -> dict[str, Any]:
    return next(record for record in bundle["inputs"] if record["case_group"] == case_group)


def _decision_model_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"case_group", "case_name"}}


def test_handoff_gate_runs_fixture_only(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["result"]["approval_to_run_handoff_status"] == "handoff_gate_validated"
    assert handoff_bundle["result"]["paper_only"] is True
    assert handoff_bundle["result"]["live_blocked"] is True


def test_handoff_summary_has_expected_distribution(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["summary"]["gate_status_distribution"] == {
        "blocked_audit_or_export_failure": 8,
        "blocked_missing_valid_approval": 12,
        "blocked_runtime_permission_leak": 8,
        "blocked_scope_expansion": 6,
        "blocked_terminal_incident": 12,
        "blocked_timeout_misclassified_as_pass": 6,
        "eligible_future_bundle_only": 12,
        "manual_review_required": 8,
    }


@pytest.mark.parametrize(
    ("field_name", "expected"),
    [
        ("input_count", 72),
        ("envelope_count", 72),
        ("gate_decision_count", 72),
        ("future_bundle_eligible_count", 12),
        ("boundary_block_count", 60),
        ("incident_escalation_count", 60),
        ("proof_record_count", 72),
        ("disabled_command_template_count", 3),
    ],
)
def test_handoff_summary_counts(handoff_bundle: dict[str, Any], field_name: str, expected: int) -> None:
    assert handoff_bundle["summary"][field_name] == expected


@pytest.mark.parametrize(
    "field_name",
    [
        "current_detector_run_allowed_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
    ],
)
def test_handoff_never_allows_current_runtime_permissions(handoff_bundle: dict[str, Any], field_name: str) -> None:
    assert handoff_bundle["summary"][field_name] == 0


@pytest.mark.parametrize(
    "field_name",
    [
        "separate_future_bundle_required_count",
        "explicit_reapproval_required_count",
        "pre_run_safety_scan_required_count",
        "post_run_evidence_required_count",
    ],
)
def test_handoff_requires_future_bundle_guards_for_every_decision(handoff_bundle: dict[str, Any], field_name: str) -> None:
    assert handoff_bundle["summary"][field_name] == handoff_bundle["summary"]["gate_decision_count"]


@pytest.mark.parametrize(
    ("case_group", "gate_status", "eligible"),
    [
        ("eligible_future_bundle_only", "eligible_future_bundle_only", True),
        ("blocked_missing_valid_approval", "blocked_missing_valid_approval", False),
        ("blocked_terminal_incident", "blocked_terminal_incident", False),
        ("manual_review_required", "manual_review_required", False),
        ("blocked_audit_or_export_failure", "blocked_audit_or_export_failure", False),
        ("blocked_runtime_permission_leak", "blocked_runtime_permission_leak", False),
        ("blocked_scope_expansion", "blocked_scope_expansion", False),
        ("blocked_timeout_misclassified_as_pass", "blocked_timeout_misclassified_as_pass", False),
    ],
)
def test_handoff_case_groups_map_to_gate_statuses(handoff_bundle: dict[str, Any], case_group: str, gate_status: str, eligible: bool) -> None:
    decision = _decision(handoff_bundle, case_group)
    assert decision["gate_status"] == gate_status
    assert decision["future_bundle_eligible"] is eligible
    assert decision["detector_run_allowed_now"] is False


def test_eligible_path_ignores_prior_invalid_terminal_blocks(handoff_bundle: dict[str, Any]) -> None:
    handoff_input = _input(handoff_bundle, "eligible_future_bundle_only")
    assert handoff_input["source_terminal_block_count"] >= 1
    assert _decision(handoff_bundle, "eligible_future_bundle_only")["gate_status"] == "eligible_future_bundle_only"


def test_handoff_input_hash_is_deterministic(handoff_bundle: dict[str, Any]) -> None:
    record = handoff_bundle["inputs"][0]
    assert approval_to_run_handoff_input_hash(ApprovalToRunHandoffInput.from_dict({**record, "input_hash": ""})) == record["input_hash"]


def test_handoff_envelope_hash_is_deterministic(handoff_bundle: dict[str, Any]) -> None:
    record = handoff_bundle["envelopes"][0]
    assert future_detector_run_envelope_hash(FutureDetectorRunEnvelope.from_dict({**record, "envelope_hash": ""})) == record["envelope_hash"]


def test_handoff_decision_hash_is_deterministic(handoff_bundle: dict[str, Any]) -> None:
    record = _decision_model_payload(handoff_bundle["decisions"][0])
    assert approval_to_run_gate_decision_hash(ApprovalToRunGateDecision.from_dict({**record, "decision_hash": ""})) == record["decision_hash"]


@pytest.mark.parametrize(
    "field_name",
    [
        "detector_run_allowed_now",
        "broker_connection_allowed_now",
        "credential_allowed_now",
        "live_order_allowed_now",
        "scheduler_allowed_now",
        "real_sizing_allowed_now",
    ],
)
def test_handoff_decision_model_rejects_runtime_permission_true(handoff_bundle: dict[str, Any], field_name: str) -> None:
    record = _decision_model_payload(handoff_bundle["decisions"][0])
    with pytest.raises(ValueError):
        ApprovalToRunGateDecision.from_dict({**record, field_name: True})


@pytest.mark.parametrize(
    "field_name",
    [
        "command_template_enabled",
        "command_template_allowed_now",
        "detector_run_allowed_now",
        "broker_connection_allowed_now",
        "credential_allowed_now",
        "live_order_allowed_now",
        "scheduler_allowed_now",
        "real_sizing_allowed_now",
    ],
)
def test_handoff_envelope_model_rejects_runtime_permission_true(handoff_bundle: dict[str, Any], field_name: str) -> None:
    record = handoff_bundle["envelopes"][0]
    with pytest.raises(ValueError):
        FutureDetectorRunEnvelope.from_dict({**record, field_name: True})


def test_handoff_input_model_requires_source_hashes(handoff_bundle: dict[str, Any]) -> None:
    record = handoff_bundle["inputs"][0]
    with pytest.raises(ValueError):
        ApprovalToRunHandoffInput.from_dict({**record, "source_audit_summary_hash": ""})


def test_disabled_command_templates_are_disabled(handoff_bundle: dict[str, Any]) -> None:
    assert all(template["enabled"] is False and template["allowed_now"] is False for template in handoff_bundle["templates"])


def test_disabled_command_templates_require_future_bundle_controls(handoff_bundle: dict[str, Any]) -> None:
    for template in handoff_bundle["templates"]:
        assert template["requires_separate_future_bundle"] is True
        assert template["requires_explicit_operator_reapproval"] is True
        assert template["requires_pre_run_safety_scan"] is True
        assert template["requires_post_run_evidence"] is True


def test_command_registry_builds_three_templates() -> None:
    assert len(build_disabled_handoff_command_templates()) == 3


def test_handoff_source_snapshot_loads_requested_prior_proof() -> None:
    snapshot = load_handoff_source_snapshot()
    assert {"manual_approval_packet_summary", "read_only_detector_dry_run_summary", "approval_intake_summary", "broker_readiness_summary", "incident_rehearsal_summary", "lifecycle_summary", "audit_proof", "export_safety_scan", "export_review_proof"}.issubset(snapshot)


def test_handoff_source_snapshot_has_no_export_safety_findings() -> None:
    snapshot = load_handoff_source_snapshot()
    assert snapshot["export_safety_scan"]["active_forbidden_live_decisions"] == 0
    assert snapshot["export_safety_scan"]["credential_findings"] == 0


def test_build_functions_are_deterministic() -> None:
    snapshot = load_handoff_source_snapshot()
    first_inputs = build_approval_to_run_handoff_inputs(snapshot)
    second_inputs = build_approval_to_run_handoff_inputs(snapshot)
    assert first_inputs == second_inputs
    templates = build_disabled_handoff_command_templates()
    assert build_approval_to_run_gate_decisions(first_inputs, build_future_detector_run_envelopes(first_inputs, templates))


@pytest.mark.parametrize(
    "path_attribute",
    [
        "HANDOFF_INPUTS_PATH",
        "FUTURE_DETECTOR_RUN_ENVELOPES_PATH",
        "APPROVAL_TO_RUN_GATE_DECISIONS_PATH",
        "DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH",
        "HANDOFF_BOUNDARY_BLOCKS_PATH",
        "HANDOFF_INCIDENT_ESCALATIONS_PATH",
        "APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH",
        "APPROVAL_TO_RUN_HANDOFF_PROOF_PATH",
        "APPROVAL_TO_RUN_HANDOFF_REPORT_PATH",
        "APPROVAL_TO_RUN_HANDOFF_LEDGER_PATH",
        "HANDOFF_INPUTS_FIXTURE_PATH",
        "FUTURE_DETECTOR_RUN_ENVELOPES_FIXTURE_PATH",
        "APPROVAL_TO_RUN_GATE_DECISIONS_FIXTURE_PATH",
        "DISABLED_HANDOFF_COMMAND_TEMPLATES_FIXTURE_PATH",
        "EXPECTED_HANDOFF_SUMMARY_FIXTURE_PATH",
    ],
)
def test_handoff_artifacts_written(
    handoff_bundle: dict[str, Any],
    path_attribute: str,
) -> None:
    path = getattr(handoff_module, path_attribute)
    if not isinstance(path, Path):
        raise TypeError(
            "approval-to-run handoff artifact binding must be a Path: "
            f"attribute={path_attribute}, actual={type(path).__name__}"
        )
    assert path.exists()


def test_handoff_expected_summary_fixture_matches_summary(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["expected_summary"] == handoff_bundle["summary"]


def test_handoff_report_states_detector_not_run(handoff_bundle: dict[str, Any]) -> None:
    text = APPROVAL_TO_RUN_HANDOFF_REPORT_PATH.read_text(encoding="utf-8")
    assert "detector_run_in_this_bundle: `false`" in text


def test_handoff_ledger_lists_summary_artifact(handoff_bundle: dict[str, Any]) -> None:
    text = APPROVAL_TO_RUN_HANDOFF_LEDGER_PATH.read_text(encoding="utf-8")
    assert "approval_to_run_handoff_summary" in text


def test_audit_recognizes_handoff_artifacts(handoff_bundle: dict[str, Any]) -> None:
    types = {artifact_type for artifact_type, _, _, _ in ARTIFACT_SPECS}
    assert {"handoff_inputs", "approval_to_run_gate_decisions", "approval_to_run_handoff_summary", "approval_to_run_handoff_proof"}.issubset(types)


def test_audit_confirms_handoff_summary_safe(handoff_bundle: dict[str, Any]) -> None:
    assert audit_approval_to_run_handoff_summary(handoff_bundle["summary"]) == []


@pytest.mark.parametrize(
    ("mutation", "check_id"),
    [
        ({"paper_only": False}, "approval_to_run_handoff_paper_live_boundary"),
        ({"approval_to_run_handoff_status": "missing"}, "approval_to_run_handoff_status_not_validated"),
        ({"detector_run_allowed_now": True}, "approval_to_run_handoff_detector_run_allowed_now_forbidden"),
        ({"broker_connection_created": True}, "approval_to_run_handoff_broker_connection_created_forbidden"),
        ({"current_detector_run_allowed_count": 1}, "approval_to_run_handoff_current_detector_run_allowed_count_must_be_zero"),
        ({"credential_allowed_now_count": 1}, "approval_to_run_handoff_credential_allowed_now_count_must_be_zero"),
        ({"future_bundle_eligible_count": 0}, "approval_to_run_handoff_future_bundle_eligible_count_missing"),
        ({"command_templates_disabled": False}, "approval_to_run_handoff_templates_not_disabled"),
        ({"source_full_suite_timeout_recorded_as_pass": True}, "approval_to_run_handoff_source_timeout_recorded_as_pass"),
        ({"next_required_gate": "wrong"}, "approval_to_run_handoff_next_gate"),
    ],
)
def test_audit_flags_handoff_mutations(handoff_bundle: dict[str, Any], mutation: dict[str, Any], check_id: str) -> None:
    findings = audit_approval_to_run_handoff_summary({**handoff_bundle["summary"], **mutation})
    assert any(finding["check_id"] == check_id for finding in findings)


def test_reporting_includes_handoff_summary(handoff_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _approval_to_run_handoff_summary(evidence)
    assert summary["approval_to_run_handoff_status"] == "handoff_gate_validated"
    assert summary["future_bundle_eligible_count"] == 12


def test_reporting_handoff_summary_runtime_counts_zero(handoff_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _approval_to_run_handoff_summary(evidence)
    assert summary["current_detector_run_allowed_count"] == 0
    assert summary["broker_connection_allowed_now_count"] == 0


def test_export_verifier_selects_handoff_artifacts(handoff_bundle: dict[str, Any]) -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"approval_to_run_handoff_summary", "approval_to_run_handoff_proof", "approval_to_run_gate_decisions"}.issubset(ids)


def test_export_verifier_selects_handoff_reports(handoff_bundle: dict[str, Any]) -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "report-dopey_read_only_detector_approval_to_run_handoff_gate_report" in ids
    assert "report-dopey_approval_to_run_handoff_gate_artifact_ledger" in ids


def test_export_review_includes_handoff_summary(handoff_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(reporting_summary={"approval_to_run_handoff_summary": handoff_bundle["summary"]}, shared_export_path="shared", safety_state={}, export_safety_scan={})
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "read-only detector approval-to-run handoff gate", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "approve_for_offline_review", "offline_review_only", [], [], "read-only detector approval-to-run handoff gate", True, True, "hash")
    assert "Read-Only Detector Approval-To-Run Handoff Gate" in render_executive_summary(ctx, bundle, [], decision)


def test_export_review_safety_summary_mentions_handoff_gate(handoff_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(reporting_summary={"approval_to_run_handoff_summary": handoff_bundle["summary"]}, shared_export_path="shared", safety_state={}, export_safety_scan={})
    assert "approval_to_run_handoff_gate" in render_safety_summary(ctx)


def test_shard_plan_includes_handoff_tests() -> None:
    plan = _handoff_shard_plan()
    assert plan["split_suite_lanes"]["approval_to_run_handoff_gate_tests"] == ["tests/test_read_only_detector_approval_to_run_handoff_gate.py"]


def test_shard_plan_marks_handoff_artifact_tests_sequential() -> None:
    plan = _handoff_shard_plan()
    assert "tests/test_read_only_detector_approval_to_run_handoff_gate.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    plan = _handoff_shard_plan()
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_handoff_does_not_create_credentials_file(handoff_bundle: dict[str, Any]) -> None:
    assert not Path(".env").exists()
    assert handoff_bundle["summary"]["credentials_created"] is False


def test_handoff_does_not_create_scheduler(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["summary"]["scheduler_created"] is False


def test_handoff_does_not_create_robinhood_mcp_integration(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["summary"]["robinhood_mcp_integration_created"] is False


def test_handoff_does_not_create_broker_connection(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["summary"]["broker_connection_created"] is False


def test_handoff_does_not_run_detector(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["summary"]["read_only_detector_run"] is False


def test_handoff_does_not_create_real_sizing_logic(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["summary"]["real_sizing_created"] is False
    assert handoff_bundle["summary"]["real_buying_power_logic_created"] is False


def test_handoff_next_gate_is_separate_future_bundle(handoff_bundle: dict[str, Any]) -> None:
    assert handoff_bundle["summary"]["next_required_gate"] == APPROVAL_TO_RUN_NEXT_GATE


def _handoff_shard_plan() -> dict[str, Any]:
    summary = {"collection": {"status": "pass", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    result = CommandResult(["python", "-m", "pytest", "tests/test_read_only_detector_approval_to_run_handoff_gate.py", "-q"], "pass", 0, 1.0, False, False, "ok", "")
    return write_test_shard_plan(["tests/test_read_only_detector_approval_to_run_handoff_gate.py"], [result], summary)
