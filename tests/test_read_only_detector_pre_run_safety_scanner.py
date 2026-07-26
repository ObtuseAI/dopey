from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_broker_readiness import pre_run_safety_scanner as pre_run_module
from dopey_broker_readiness.approval_intake_validator import validate_read_only_detector_approval_intake
from dopey_broker_readiness.approval_to_run_handoff_gate import validate_read_only_detector_approval_to_run_handoff_gate
from dopey_broker_readiness.audit import audit_pre_run_safety_summary
from dopey_broker_readiness.manual_approval_packet_builder import build_manual_approval_packet_outputs
from dopey_broker_readiness.pre_run_forbidden_boundary_scanner import (
    ACTIVE_RUNTIME_CLASSIFICATION,
    BLOCKED_TEMPLATE_CLASSIFICATION,
    DOCUMENTATION_CLASSIFICATION,
    NEGATIVE_CONTROL_CLASSIFICATION,
    BoundaryScanSource,
    classify_boundary_references,
)
from dopey_broker_readiness.pre_run_safety_scanner import (
    EXPECTED_PRE_RUN_SUMMARY_FIXTURE_PATH,
    PRE_RUN_BOUNDARY_CLASSIFICATIONS_PATH,
    PRE_RUN_BOUNDARY_SCAN_CASES_FIXTURE_PATH,
    PRE_RUN_BOUNDARY_SCAN_RESULTS_PATH,
    PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_FIXTURE_PATH,
    PRE_RUN_INCIDENT_ESCALATIONS_PATH,
    PRE_RUN_SAFETY_DECISIONS_FIXTURE_PATH,
    PRE_RUN_SAFETY_DECISIONS_PATH,
    PRE_RUN_SAFETY_LEDGER_PATH,
    PRE_RUN_SAFETY_PROOF_PATH,
    PRE_RUN_SAFETY_SCAN_INPUTS_FIXTURE_PATH,
    PRE_RUN_SAFETY_SCAN_INPUTS_PATH,
    PRE_RUN_SAFETY_SUMMARY_PATH,
    load_pre_run_source_snapshot,
    validate_read_only_detector_pre_run_safety_scanner,
)
from dopey_broker_readiness.pre_run_safety_scanner_models import (
    PreRunBoundaryScanResult,
    PreRunSafetyDecision,
    PreRunSafetyScanInput,
    pre_run_boundary_scan_result_hash,
    pre_run_safety_decision_hash,
    pre_run_safety_scan_input_hash,
)
from dopey_broker_readiness.read_only_detector_dry_run_validator import validate_read_only_detector_dry_run
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
from dopey_reporting.reporting_bundle import _pre_run_safety_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


@pytest.fixture(scope="session")
def pre_run_bundle() -> dict[str, Any]:
    run_broker_readiness_preflight()
    build_manual_approval_packet_outputs()
    validate_read_only_detector_dry_run()
    validate_read_only_detector_approval_intake()
    validate_read_only_detector_approval_to_run_handoff_gate()
    result = validate_read_only_detector_pre_run_safety_scanner()
    return {
        "result": result,
        "inputs": _jsonl(PRE_RUN_SAFETY_SCAN_INPUTS_PATH),
        "cases": _json(PRE_RUN_BOUNDARY_SCAN_CASES_FIXTURE_PATH)["records"],
        "boundary_results": _jsonl(PRE_RUN_BOUNDARY_SCAN_RESULTS_PATH),
        "decisions": _jsonl(PRE_RUN_SAFETY_DECISIONS_PATH),
        "classifications": _jsonl(PRE_RUN_BOUNDARY_CLASSIFICATIONS_PATH),
        "escalations": _jsonl(PRE_RUN_INCIDENT_ESCALATIONS_PATH),
        "summary": _json(PRE_RUN_SAFETY_SUMMARY_PATH),
        "proof": _jsonl(PRE_RUN_SAFETY_PROOF_PATH),
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _input(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["inputs"] if record["case_name"] == case_name)


def _case(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["cases"] if record["case_name"] == case_name)


def _boundary(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["boundary_results"] if record["case_name"] == case_name)


def _decision(bundle: dict[str, Any], case_name: str) -> dict[str, Any]:
    return next(record for record in bundle["decisions"] if record["case_name"] == case_name)


def _decision_by_group(bundle: dict[str, Any], case_group: str) -> dict[str, Any]:
    return next(record for record in bundle["decisions"] if record["case_group"] == case_group)


def _source(pattern: str, context_type: str) -> BoundaryScanSource:
    return BoundaryScanSource("source", "source", pattern, context_type, {})


def _classify(pattern: str, context_type: str) -> dict[str, Any]:
    return classify_boundary_references([_source(pattern, context_type)])[0]


def _sample_input() -> PreRunSafetyScanInput:
    return PreRunSafetyScanInput("input", "handoff", "intake", "dry", "manual", "preflight", "audit", "export", "review", 1, 0, 0, 0, 0, 0, 0, True, True, "")


def _sample_boundary() -> PreRunBoundaryScanResult:
    return PreRunBoundaryScanResult("boundary", "input", True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, 0, "clean", ["clean"], True, True, "")


def _sample_decision() -> PreRunSafetyDecision:
    return PreRunSafetyDecision("decision", "input", "boundary", "future_bundle_preparation_allowed", True, False, False, False, False, False, False, True, True, True, True, ["clean"], "none", True, True, "")


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(intent_id="live", symbol="DLP1", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-17", "dte": 5}], max_loss=1.0, live_allowed=True, active_policy_required=True)


def _pre_run_shard_plan() -> dict[str, Any]:
    summary = {"collection": {"status": "pass", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    result = CommandResult(["python", "-m", "pytest", "tests/test_read_only_detector_pre_run_safety_scanner.py", "-q"], "pass", 0, 1.0, False, False, "ok", "")
    return write_test_shard_plan(["tests/test_read_only_detector_pre_run_safety_scanner.py"], [result], summary)


def test_pre_run_safety_scan_input_serializes_deterministically() -> None:
    record = _sample_input()
    assert PreRunSafetyScanInput.from_dict(record.to_dict()).to_dict() == record.to_dict()


def test_pre_run_boundary_scan_result_serializes_deterministically() -> None:
    record = _sample_boundary()
    assert PreRunBoundaryScanResult.from_dict(record.to_dict()).to_dict() == record.to_dict()


def test_pre_run_safety_decision_serializes_deterministically() -> None:
    record = _sample_decision()
    assert PreRunSafetyDecision.from_dict(record.to_dict()).to_dict() == record.to_dict()


def test_pre_run_hashes_are_deterministic() -> None:
    assert pre_run_safety_scan_input_hash(_sample_input()) == pre_run_safety_scan_input_hash(_sample_input())
    assert pre_run_boundary_scan_result_hash(_sample_boundary()) == pre_run_boundary_scan_result_hash(_sample_boundary())
    assert pre_run_safety_decision_hash(_sample_decision()) == pre_run_safety_decision_hash(_sample_decision())


def test_pre_run_input_requires_paper_only_live_blocked() -> None:
    with pytest.raises(ValueError):
        PreRunSafetyScanInput.from_dict({**_sample_input().to_dict(), "paper_only": False})


def test_pre_run_decision_runtime_permissions_false_by_default() -> None:
    record = _sample_decision()
    assert record.detector_run_allowed_now is False
    with pytest.raises(ValueError):
        PreRunSafetyDecision.from_dict({**record.to_dict(), "detector_run_allowed_now": True})


def test_pre_run_future_preparation_does_not_equal_detector_run() -> None:
    decision = _sample_decision()
    assert decision.future_detector_bundle_preparation_allowed is True
    assert decision.detector_run_allowed_now is False


def test_pre_run_scanner_loads_handoff_summary(pre_run_bundle: dict[str, Any]) -> None:
    assert load_pre_run_source_snapshot()["handoff_summary"]["approval_to_run_handoff_status"] == "handoff_gate_validated"


def test_pre_run_scanner_loads_handoff_proof(pre_run_bundle: dict[str, Any]) -> None:
    assert "proof_hash" in load_pre_run_source_snapshot()["handoff_proof"]


def test_pre_run_scanner_loads_disabled_command_templates(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["command_templates_disabled"] is True


def test_pre_run_scanner_loads_approval_intake_summary(pre_run_bundle: dict[str, Any]) -> None:
    assert load_pre_run_source_snapshot()["approval_intake_summary"]["approval_intake_status"] == "approval_intake_fixture_validated"


def test_pre_run_scanner_loads_dry_run_summary(pre_run_bundle: dict[str, Any]) -> None:
    assert load_pre_run_source_snapshot()["dry_run_summary"]["read_only_detector_run"] is False


def test_pre_run_scanner_loads_manual_packet_summary(pre_run_bundle: dict[str, Any]) -> None:
    assert load_pre_run_source_snapshot()["manual_packet_summary"]["approval_present"] is False


def test_pre_run_scanner_loads_preflight_summary(pre_run_bundle: dict[str, Any]) -> None:
    assert load_pre_run_source_snapshot()["preflight_summary"]["not_broker_ready"] is True


def test_pre_run_scanner_loads_audit_summary(pre_run_bundle: dict[str, Any]) -> None:
    assert load_pre_run_source_snapshot()["audit_proof"]


def test_pre_run_scanner_confirms_future_bundle_eligibility(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["source_handoff_future_bundle_eligible_count"] == 12


def test_pre_run_scanner_confirms_detector_run_allowed_now_zero(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["detector_run_allowed_now_count"] == 0


def test_pre_run_scanner_confirms_broker_connection_allowed_now_zero(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["broker_connection_allowed_now_count"] == 0


def test_pre_run_scanner_confirms_credential_allowed_now_zero(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["credential_allowed_now_count"] == 0


def test_pre_run_scanner_confirms_live_order_allowed_now_zero(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["live_order_allowed_now_count"] == 0


def test_pre_run_scanner_confirms_scheduler_allowed_now_zero(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["scheduler_allowed_now_count"] == 0


def test_pre_run_scanner_confirms_real_sizing_allowed_now_zero(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["real_sizing_allowed_now_count"] == 0


def test_pre_run_scanner_confirms_command_templates_disabled(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["command_templates_disabled"] is True


def test_pre_run_scanner_confirms_reapproval_required(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["explicit_reapproval_required"] is True


def test_pre_run_scanner_confirms_post_run_evidence_required(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["post_run_evidence_required"] is True


def test_forbidden_boundary_scanner_detects_env() -> None:
    assert _classify(".env active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_token() -> None:
    assert _classify("access_token active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_broker_connection() -> None:
    assert _classify("broker_connection active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_robinhood_mcp_invocation() -> None:
    assert _classify("robinhood_mcp mcp.connect active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_order_placement() -> None:
    assert _classify("place_order active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_order_cancellation() -> None:
    assert _classify("cancel_order active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_review_option_order() -> None:
    assert _classify("review_option_order active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_account_balance() -> None:
    assert _classify("account_balance active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_buying_power() -> None:
    assert _classify("buying_power active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_real_sizing() -> None:
    assert _classify("real_sizing active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_scheduler() -> None:
    assert _classify("scheduler active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_detects_network_market_data() -> None:
    assert _classify("network_market_data requests.get active", "active_runtime")["active_forbidden"] is True


def test_forbidden_boundary_scanner_classifies_documentation_reference_nonfatal() -> None:
    record = _classify("blocked broker_connection documentation", "documentation")
    assert record["classification"] == DOCUMENTATION_CLASSIFICATION
    assert record["active_forbidden"] is False


def test_forbidden_boundary_scanner_classifies_negative_control_nonfatal() -> None:
    record = _classify("negative-control .env fixture", "negative_control_fixture")
    assert record["classification"] == NEGATIVE_CONTROL_CLASSIFICATION
    assert record["active_forbidden"] is False


def test_forbidden_boundary_scanner_classifies_blocked_template_nonfatal() -> None:
    record = _classify("disabled template place_order", "blocked_command_template")
    assert record["classification"] == BLOCKED_TEMPLATE_CLASSIFICATION
    assert record["active_forbidden"] is False


def test_pre_run_safety_scan_inputs_fixture_loads(pre_run_bundle: dict[str, Any]) -> None:
    assert _json(PRE_RUN_SAFETY_SCAN_INPUTS_FIXTURE_PATH)["record_count"] == 96


def test_pre_run_boundary_scan_cases_fixture_loads(pre_run_bundle: dict[str, Any]) -> None:
    assert _json(PRE_RUN_BOUNDARY_SCAN_CASES_FIXTURE_PATH)["record_count"] == 96


def test_pre_run_safety_decisions_fixture_loads(pre_run_bundle: dict[str, Any]) -> None:
    assert _json(PRE_RUN_SAFETY_DECISIONS_FIXTURE_PATH)["record_count"] == 96


def test_pre_run_forbidden_boundary_patterns_fixture_loads(pre_run_bundle: dict[str, Any]) -> None:
    assert _json(PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_FIXTURE_PATH)["pattern_count"] >= 28


def test_expected_pre_run_summary_fixture_loads(pre_run_bundle: dict[str, Any]) -> None:
    assert _json(EXPECTED_PRE_RUN_SUMMARY_FIXTURE_PATH) == pre_run_bundle["summary"]


def test_pre_run_fixture_has_at_least_96_cases(pre_run_bundle: dict[str, Any]) -> None:
    assert len(pre_run_bundle["cases"]) >= 96


def _assert_group_count(bundle: dict[str, Any], group: str, count: int) -> None:
    assert sum(1 for record in bundle["cases"] if record["case_group"] == group) == count


def test_pre_run_fixture_covers_clean_eligible_cases(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "clean_eligible", 16)


def test_pre_run_fixture_covers_runtime_permission_leaks(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "runtime_permission_leak", 16)


def test_pre_run_fixture_covers_forbidden_boundary_references(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "forbidden_boundary_reference", 16)


def test_pre_run_fixture_covers_command_template_violations(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "command_template_violation", 12)


def test_pre_run_fixture_covers_audit_export_failures(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "audit_export_failure", 12)


def test_pre_run_fixture_covers_missing_proof_cases(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "missing_proof", 8)


def test_pre_run_fixture_covers_timeout_misclassification_cases(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "timeout_misclassification", 8)


def test_pre_run_fixture_covers_terminal_block_cases(pre_run_bundle: dict[str, Any]) -> None:
    _assert_group_count(pre_run_bundle, "terminal_block", 8)


def test_clean_handoff_allows_future_bundle_preparation(pre_run_bundle: dict[str, Any]) -> None:
    assert _decision(pre_run_bundle, "clean_handoff_eligibility_allows_future_bundle_preparation")["future_detector_bundle_preparation_allowed"] is True


def test_future_bundle_preparation_does_not_allow_detector_run_now(pre_run_bundle: dict[str, Any]) -> None:
    decision = _decision(pre_run_bundle, "future_bundle_eligibility_does_not_allow_detector_run_now")
    assert decision["future_detector_bundle_preparation_allowed"] is True
    assert decision["detector_run_allowed_now"] is False


def _assert_case_decision(bundle: dict[str, Any], case_name: str, decision: str) -> None:
    assert _decision(bundle, case_name)["decision"] == decision


def _generated_case_test(case_name: str, decision: str) -> Callable[[dict[str, Any]], None]:
    def test_func(pre_run_bundle: dict[str, Any]) -> None:
        _assert_case_decision(pre_run_bundle, case_name, decision)
    return test_func


for _name in [
    "detector_run_allowed_now_true_blocks_scan",
    "broker_connection_allowed_now_true_blocks_scan",
    "credential_allowed_now_true_blocks_scan",
    "live_order_allowed_now_true_blocks_scan",
    "scheduler_allowed_now_true_blocks_scan",
    "real_sizing_allowed_now_true_blocks_scan",
]:
    globals()[f"test_{_name}"] = _generated_case_test(_name, "blocked_permission_leak")


for _name in [
    "enabled_command_template_blocks_scan",
    "command_template_missing_reapproval_blocks_scan",
    "command_template_missing_future_bundle_blocks_scan",
    "command_template_with_credentials_blocks_scan",
    "command_template_with_order_placement_blocks_scan",
    "command_template_with_cancellation_blocks_scan",
    "command_template_with_scheduler_blocks_scan",
    "command_template_with_live_trading_blocks_scan",
]:
    _case_name = _name.replace("command_template_with_credentials", "command_template_containing_credential")
    _case_name = _case_name.replace("command_template_with_order_placement", "command_template_containing_order_placement")
    _case_name = _case_name.replace("command_template_with_cancellation", "command_template_containing_cancellation")
    _case_name = _case_name.replace("command_template_with_scheduler", "command_template_containing_scheduler")
    _case_name = _case_name.replace("command_template_with_live_trading", "command_template_containing_live_trading")
    _case_name = _case_name.replace("enabled_command_template", "command_template_enabled")
    globals()[f"test_{_name}"] = _generated_case_test(_case_name, "terminal_block")


def test_missing_handoff_summary_blocks_scan(pre_run_bundle: dict[str, Any]) -> None:
    _assert_case_decision(pre_run_bundle, "missing_handoff_summary_blocks_scan", "blocked_missing_handoff")


def test_missing_approval_intake_summary_blocks_scan(pre_run_bundle: dict[str, Any]) -> None:
    _assert_case_decision(pre_run_bundle, "missing_approval_intake_summary_blocks_scan", "manual_review_required")


def test_missing_dry_run_summary_blocks_scan(pre_run_bundle: dict[str, Any]) -> None:
    _assert_case_decision(pre_run_bundle, "missing_dry_run_summary_blocks_scan", "manual_review_required")


def test_missing_audit_proof_blocks_scan(pre_run_bundle: dict[str, Any]) -> None:
    _assert_case_decision(pre_run_bundle, "missing_audit_proof_blocks_scan", "manual_review_required")


def test_safety_finding_blocks_scan(pre_run_bundle: dict[str, Any]) -> None:
    assert _decision_by_group(pre_run_bundle, "audit_export_failure")["decision"] in {"blocked_safety_finding", "blocked_credential_finding"}


def test_credential_finding_blocks_scan(pre_run_bundle: dict[str, Any]) -> None:
    assert any(record["decision"] == "blocked_credential_finding" for record in pre_run_bundle["decisions"])


def test_timeout_misclassified_as_pass_blocks_scan(pre_run_bundle: dict[str, Any]) -> None:
    _assert_case_decision(pre_run_bundle, "timeout_misclassified_as_pass_blocks_scan", "blocked_timeout_misclassified")


def test_windows_stdout_flush_oserror_recorded_not_pass(pre_run_bundle: dict[str, Any]) -> None:
    _assert_case_decision(pre_run_bundle, "windows_stdout_flush_oserror_recorded_not_pass", "blocked_timeout_misclassified")


for _test_name, _case_name in {
    "test_active_env_reference_blocks_scan": "active_env_reference_blocks_scan",
    "test_active_token_reference_blocks_scan": "active_token_reference_blocks_scan",
    "test_active_broker_connection_reference_blocks_scan": "active_broker_connection_reference_blocks_scan",
    "test_active_robinhood_mcp_invocation_blocks_scan": "active_robinhood_mcp_invocation_blocks_scan",
    "test_active_order_placement_reference_blocks_scan": "active_order_placement_reference_blocks_scan",
    "test_active_order_cancellation_reference_blocks_scan": "active_order_cancellation_reference_blocks_scan",
    "test_active_review_option_order_reference_blocks_scan": "active_review_option_order_reference_blocks_scan",
    "test_active_account_balance_reference_blocks_scan": "active_account_balance_reference_blocks_scan",
    "test_active_buying_power_reference_blocks_scan": "active_buying_power_reference_blocks_scan",
    "test_active_real_sizing_reference_blocks_scan": "active_real_sizing_reference_blocks_scan",
    "test_active_scheduler_reference_blocks_scan": "active_scheduler_reference_blocks_scan",
    "test_active_network_market_data_reference_blocks_scan": "active_network_market_data_reference_blocks_scan",
}.items():
    globals()[_test_name] = _generated_case_test(_case_name, "terminal_block")


def _assert_incident(bundle: dict[str, Any], incident_type: str) -> None:
    assert any(record["incident_type"] == incident_type for record in bundle["escalations"])


for _test_name, _incident_type in {
    "test_pre_run_runtime_permission_leak_terminal_blocks": "pre_run_runtime_permission_leak",
    "test_pre_run_enabled_command_template_terminal_blocks": "pre_run_enabled_command_template",
    "test_pre_run_credential_reference_terminal_blocks": "pre_run_credential_reference",
    "test_pre_run_broker_connection_reference_terminal_blocks": "pre_run_broker_connection_reference",
    "test_pre_run_robinhood_mcp_invocation_terminal_blocks": "pre_run_robinhood_mcp_invocation",
    "test_pre_run_order_placement_reference_terminal_blocks": "pre_run_order_placement_reference",
    "test_pre_run_order_cancellation_reference_terminal_blocks": "pre_run_order_cancellation_reference",
    "test_pre_run_scheduler_reference_terminal_blocks": "pre_run_scheduler_reference",
    "test_pre_run_real_sizing_reference_terminal_blocks": "pre_run_real_sizing_reference",
    "test_pre_run_timeout_recorded_as_pass_terminal_blocks": "pre_run_timeout_recorded_as_pass",
    "test_pre_run_missing_proof_manual_review": "pre_run_missing_proof",
}.items():
    def _make_incident_test(incident_type: str) -> Callable[[dict[str, Any]], None]:
        def test_func(pre_run_bundle: dict[str, Any]) -> None:
            _assert_incident(pre_run_bundle, incident_type)
        return test_func
    globals()[_test_name] = _make_incident_test(_incident_type)


for _path_name, _path_attribute in {
    "pre_run_safety_scan_inputs": "PRE_RUN_SAFETY_SCAN_INPUTS_PATH",
    "pre_run_boundary_scan_results": "PRE_RUN_BOUNDARY_SCAN_RESULTS_PATH",
    "pre_run_safety_decisions": "PRE_RUN_SAFETY_DECISIONS_PATH",
    "pre_run_forbidden_boundary_patterns": "PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_PATH",
    "pre_run_boundary_classifications": "PRE_RUN_BOUNDARY_CLASSIFICATIONS_PATH",
    "pre_run_incident_escalations": "PRE_RUN_INCIDENT_ESCALATIONS_PATH",
    "pre_run_safety_summary": "PRE_RUN_SAFETY_SUMMARY_PATH",
    "pre_run_safety_proof": "PRE_RUN_SAFETY_PROOF_PATH",
}.items():
    def _make_artifact_test(path_attribute: str) -> Callable[[dict[str, Any]], None]:
        def test_func(pre_run_bundle: dict[str, Any]) -> None:
            path = getattr(pre_run_module, path_attribute)
            if not isinstance(path, Path):
                raise TypeError(
                    "pre-run safety artifact binding must be a Path: "
                    f"attribute={path_attribute}, actual={type(path).__name__}"
                )
            assert path.exists()
            assert path.stat().st_size > 0
        return test_func
    globals()[f"test_{_path_name}_artifact_written"] = _make_artifact_test(_path_attribute)


def test_audit_recognizes_pre_run_safety_artifacts(pre_run_bundle: dict[str, Any]) -> None:
    types = {artifact_type for artifact_type, _, _, _ in ARTIFACT_SPECS}
    assert {"pre_run_safety_scan_inputs", "pre_run_boundary_scan_results", "pre_run_safety_decisions", "pre_run_safety_summary", "pre_run_safety_proof"}.issubset(types)


def test_audit_confirms_future_bundle_preparation_not_detector_run(pre_run_bundle: dict[str, Any]) -> None:
    assert audit_pre_run_safety_summary(pre_run_bundle["summary"]) == []
    assert pre_run_bundle["summary"]["future_bundle_preparation_allowed_count"] > 0
    assert pre_run_bundle["summary"]["detector_run_allowed_now_count"] == 0


for _field in [
    "detector_run_allowed_now",
    "broker_connection_allowed_now",
    "credential_allowed_now",
    "live_order_allowed_now",
    "scheduler_allowed_now",
    "real_sizing_allowed_now",
]:
    globals()[f"test_audit_confirms_{_field}_false"] = (lambda field_name: (lambda pre_run_bundle: assert_false_decision_field(pre_run_bundle, field_name)))(_field)


def assert_false_decision_field(pre_run_bundle: dict[str, Any], field_name: str) -> None:
    assert all(record[field_name] is False for record in pre_run_bundle["decisions"])


def test_audit_confirms_command_templates_disabled(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["command_templates_disabled"] is True


def test_audit_confirms_reapproval_required(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["explicit_reapproval_required"] is True


def test_audit_confirms_post_run_evidence_required(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["post_run_evidence_required"] is True


def test_audit_confirms_no_active_forbidden_live_decisions_after_pre_run(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["active_forbidden_live_decisions"] == 0


def test_reporting_includes_pre_run_safety_summary(pre_run_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _pre_run_safety_summary(evidence)
    assert summary["pre_run_safety_status"] == "pre_run_safety_scanner_validated"


for _field, _expected in {
    "future_bundle_preparation_allowed_count": 16,
    "detector_run_allowed_now_count": 0,
    "broker_connection_allowed_now_count": 0,
    "credential_allowed_now_count": 0,
    "live_order_allowed_now_count": 0,
    "scheduler_allowed_now_count": 0,
    "real_sizing_allowed_now_count": 0,
}.items():
    def _make_reporting_count_test(field_name: str, expected: int) -> Callable[[dict[str, Any]], None]:
        def test_func(pre_run_bundle: dict[str, Any]) -> None:
            evidence = load_reporting_evidence(EVIDENCE_PATHS)
            assert _pre_run_safety_summary(evidence)[field_name] == expected
        return test_func
    globals()[f"test_reporting_{_field if _field != 'future_bundle_preparation_allowed_count' else 'future_bundle_preparation_allowed_count'}"] = _make_reporting_count_test(_field, _expected)

test_reporting_detector_run_allowed_now_zero = _make_reporting_count_test("detector_run_allowed_now_count", 0)
test_reporting_broker_connection_allowed_now_zero = _make_reporting_count_test("broker_connection_allowed_now_count", 0)
test_reporting_credential_allowed_now_zero = _make_reporting_count_test("credential_allowed_now_count", 0)
test_reporting_live_order_allowed_now_zero = _make_reporting_count_test("live_order_allowed_now_count", 0)
test_reporting_scheduler_allowed_now_zero = _make_reporting_count_test("scheduler_allowed_now_count", 0)
test_reporting_real_sizing_allowed_now_zero = _make_reporting_count_test("real_sizing_allowed_now_count", 0)


def test_reporting_boundary_classification_distribution(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["boundary_classification_distribution"][ACTIVE_RUNTIME_CLASSIFICATION] > 0


def test_export_verifier_selects_pre_run_safety_artifacts(pre_run_bundle: dict[str, Any]) -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"pre_run_safety_summary", "pre_run_safety_proof", "pre_run_safety_decisions"}.issubset(ids)


def test_export_review_includes_pre_run_safety_summary(pre_run_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(reporting_summary={"pre_run_safety_summary": pre_run_bundle["summary"]}, shared_export_path="shared", safety_state={}, export_safety_scan={})
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "read-only detector pre-run safety scanner", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "approve_for_offline_review", "offline_review_only", [], [], "read-only detector pre-run safety scanner", True, True, "hash")
    assert "Pre-Run Safety Scanner" in render_executive_summary(ctx, bundle, [], decision)


def test_pre_run_safety_artifact_ledger_written(pre_run_bundle: dict[str, Any]) -> None:
    assert PRE_RUN_SAFETY_LEDGER_PATH.exists()


def test_shard_plan_includes_pre_run_safety_tests() -> None:
    assert _pre_run_shard_plan()["split_suite_lanes"]["pre_run_safety_scanner_tests"] == ["tests/test_read_only_detector_pre_run_safety_scanner.py"]


def test_shard_plan_marks_pre_run_artifact_tests_sequential() -> None:
    assert "tests/test_read_only_detector_pre_run_safety_scanner.py" in _pre_run_shard_plan()["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    plan = _pre_run_shard_plan()
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["live_blocked"] is True


def test_robinhood_stub_still_blocks_live_after_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert not Path(".env").exists()
    assert pre_run_bundle["summary"]["credentials_created"] is False


def test_no_scheduler_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["scheduler_created"] is False


def test_no_network_market_data_dependency_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["real_market_data_used"] is False


def test_no_same_day_churn_loophole_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    fixture = json.loads((Path(__file__).resolve().parents[1] / "dopey_data" / "fixtures" / "active_trading_policy" / "long_premium_policy_cases.json").read_text(encoding="utf-8"))
    row = next(record for record in fixture["candidates"] if record["case_id"] == "same_day_churn_rejected")
    candidate = active_trading_candidate_from_dict(row["candidate"])
    assert evaluate_active_trading_policy(candidate, default_active_trading_thresholds()).allowed is False


def test_no_real_capital_allocator_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["real_sizing_created"] is False


def test_no_real_buying_power_logic_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["real_sizing_allowed_now_count"] == 0


def test_no_robinhood_mcp_integration_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["robinhood_mcp_integration_created"] is False


def test_no_broker_connection_created_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["broker_connection_created"] is False


def test_no_read_only_detector_run_by_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    assert pre_run_bundle["summary"]["read_only_detector_run"] is False


def test_blunder_integrity_unchanged_if_manifest_available(pre_run_bundle: dict[str, Any]) -> None:
    findings = audit_blunder_integrity()
    assert not any(finding.severity == "safety_error" for finding in findings)


def test_paper_broker_still_refuses_live_allowed_after_pre_run_safety_scanner(pre_run_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())
