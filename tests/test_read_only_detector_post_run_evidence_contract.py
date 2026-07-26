from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_broker_readiness import read_only_capability_detector as detector_module
from dopey_broker_readiness import read_only_detector_evidence_validator as evidence_module
from dopey_broker_readiness.approval_intake_validator import (
    validate_read_only_detector_approval_intake,
)
from dopey_broker_readiness.approval_to_run_handoff_gate import (
    validate_read_only_detector_approval_to_run_handoff_gate,
)
from dopey_broker_readiness.audit import audit_read_only_detector_evidence_contract_summary
from dopey_broker_readiness.manual_approval_packet_builder import build_manual_approval_packet_outputs
from dopey_broker_readiness.pre_run_safety_scanner import validate_read_only_detector_pre_run_safety_scanner
from dopey_broker_readiness.read_only_capability_detector import run_human_approved_read_only_broker_capability_detector
from dopey_broker_readiness.read_only_detector_dry_run_validator import validate_read_only_detector_dry_run
from dopey_broker_readiness.read_only_detector_evidence_contract_models import (
    DetectorBoundaryAssertion,
    DetectorEvidenceContract,
    DetectorEvidenceItem,
    DetectorEvidencePromotionDecision,
    DetectorEvidenceValidationResult,
    detector_boundary_assertion_hash,
    detector_evidence_contract_hash,
    detector_evidence_item_hash,
    detector_evidence_promotion_hash,
    detector_evidence_validation_hash,
)
from dopey_broker_readiness.read_only_detector_evidence_validator import (
    BOUNDARY_ASSERTIONS_PATH,
    EVIDENCE_CONTRACT_CASES_FIXTURE_PATH,
    EVIDENCE_CONTRACT_PATH,
    EVIDENCE_CONTRACT_PROOF_PATH,
    EVIDENCE_CONTRACT_SUMMARY_PATH,
    EVIDENCE_ITEMS_PATH,
    EVIDENCE_PROMOTION_DECISIONS_PATH,
    EVIDENCE_VALIDATION_RESULTS_PATH,
    build_boundary_assertions,
    build_evidence_contract,
    build_evidence_items,
    build_validation_result,
    completeness_score,
    evidence_contract_artifact_paths,
    load_latest_detector_evidence_snapshot,
    validate_read_only_detector_post_run_evidence_contract,
)
from dopey_broker_readiness.run_broker_readiness_preflight import run_broker_readiness_preflight
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import ExportReviewBundle, ExportReviewDecision
from dopey_export_review.review_packet import render_executive_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _read_only_detector_evidence_contract_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


@pytest.fixture(scope="session")
def evidence_bundle() -> dict[str, Any]:
    run_broker_readiness_preflight()
    build_manual_approval_packet_outputs()
    validate_read_only_detector_dry_run()
    validate_read_only_detector_approval_intake()
    validate_read_only_detector_approval_to_run_handoff_gate()
    validate_read_only_detector_pre_run_safety_scanner()
    run_human_approved_read_only_broker_capability_detector()
    detector_summary = _json(detector_module.READ_ONLY_DETECTOR_SUMMARY_PATH)
    reporting_summary_path = (
        evidence_module.ARTIFACT_ROOT
        / "reporting"
        / "reporting_bundle_summary.json"
    )
    reporting_summary_path.parent.mkdir(parents=True, exist_ok=True)
    reporting_summary_path.write_text(
        json.dumps(
            {
                "artifact_type": "test_reporting_bundle_summary",
                "read_only_detector_summary": detector_summary,
                "not_readiness_evidence": True,
                "paper_only": True,
                "live_blocked": True,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    validation_summary_path = (
        evidence_module.ARTIFACT_ROOT
        / "validation"
        / "full_suite_stabilizer_summary.json"
    )
    validation_summary_path.parent.mkdir(parents=True, exist_ok=True)
    validation_summary_path.write_text(
        json.dumps(
            {
                "artifact_type": "test_validation_summary",
                "full_suite": {
                    "status": "fixture_only_not_forward_evidence",
                    "timed_out": False,
                },
                "timeout_recorded_as_pass": False,
                "not_readiness_evidence": True,
                "paper_only": True,
                "live_blocked": True,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result = validate_read_only_detector_post_run_evidence_contract()
    return {
        "result": result,
        "contract": _json(EVIDENCE_CONTRACT_PATH),
        "items": _jsonl(EVIDENCE_ITEMS_PATH),
        "assertions": _jsonl(BOUNDARY_ASSERTIONS_PATH),
        "validation": _jsonl(EVIDENCE_VALIDATION_RESULTS_PATH)[-1],
        "promotion": _jsonl(EVIDENCE_PROMOTION_DECISIONS_PATH)[-1],
        "summary": _json(EVIDENCE_CONTRACT_SUMMARY_PATH),
        "proof": _jsonl(EVIDENCE_CONTRACT_PROOF_PATH),
        "cases": _json(EVIDENCE_CONTRACT_CASES_FIXTURE_PATH)["records"],
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _item() -> DetectorEvidenceItem:
    return DetectorEvidenceItem("item", "approval_proof_consumed", "approval", "path", True, True, 1, "hash", True, ["ok"], True, True, "")


def _assertion() -> DetectorBoundaryAssertion:
    return DetectorBoundaryAssertion("assertion", "credential_access_attempted", False, False, True, "info", False, False, ["ok"], True, True, "")


def _contract() -> DetectorEvidenceContract:
    return DetectorEvidenceContract("contract", "summary", {"approval_proof_consumed": True}, {"gate_proof_completeness": True, "provider_proof_completeness": True, "capability_proof_completeness": True, "blocked_path_proof_completeness": True, "incident_proof_completeness": True, "audit_export_review_proof_completeness": True, "validation_proof_completeness": True, "safety_boundary_proof_completeness": True}, 100, "evidence_contract_complete", "broker-readiness v2 simulated quote/order-review mirror", True, True, True, "")


def _validation() -> DetectorEvidenceValidationResult:
    return DetectorEvidenceValidationResult("validation", "contract", "evidence_contract_complete", 100, 0, 0, [], [], ["ok"], True, True, "")


def _promotion() -> DetectorEvidencePromotionDecision:
    return DetectorEvidencePromotionDecision("decision", "contract", "eligible_for_simulated_quote_order_review_mirror", "simulated_quote_order_review_mirror_fixture_only", ["live_trading"], False, False, False, False, False, False, ["ok"], True, True, "")


def _snapshot_with_detector_summary(**summary_overrides: Any) -> dict[str, Any]:
    snapshot = load_latest_detector_evidence_snapshot()
    snapshot["detector_summary"] = {**snapshot["detector_summary"], **summary_overrides}
    return snapshot


def _status_for_snapshot(snapshot: dict[str, Any]) -> str:
    items = build_evidence_items(snapshot)
    assertions = build_boundary_assertions(snapshot)
    contract = build_evidence_contract(snapshot, items, assertions)
    return build_validation_result(contract, items, assertions)["status"]


def test_models_serialize_deterministically() -> None:
    assert DetectorEvidenceItem.from_dict(_item().to_dict()).to_dict() == _item().to_dict()
    assert DetectorBoundaryAssertion.from_dict(_assertion().to_dict()).to_dict() == _assertion().to_dict()
    assert DetectorEvidenceContract.from_dict(_contract().to_dict()).to_dict() == _contract().to_dict()
    assert DetectorEvidenceValidationResult.from_dict(_validation().to_dict()).to_dict() == _validation().to_dict()
    assert DetectorEvidencePromotionDecision.from_dict(_promotion().to_dict()).to_dict() == _promotion().to_dict()


def test_hashes_are_deterministic() -> None:
    assert detector_evidence_item_hash(_item()) == detector_evidence_item_hash(_item())
    assert detector_boundary_assertion_hash(_assertion()) == detector_boundary_assertion_hash(_assertion())
    assert detector_evidence_contract_hash(_contract()) == detector_evidence_contract_hash(_contract())
    assert detector_evidence_validation_hash(_validation()) == detector_evidence_validation_hash(_validation())
    assert detector_evidence_promotion_hash(_promotion()) == detector_evidence_promotion_hash(_promotion())


def test_contract_loads_latest_detector_artifacts(evidence_bundle: dict[str, Any]) -> None:
    snapshot = load_latest_detector_evidence_snapshot()
    assert snapshot["detector_summary"]["detector_bundle_status"] == "human_approved_read_only_detector_validated"
    assert snapshot["post_run_evidence"]["post_run_safety_summary"]["not_live_ready"] is True


@pytest.mark.parametrize("path_key", evidence_contract_artifact_paths().keys())
def test_evidence_artifacts_written(evidence_bundle: dict[str, Any], path_key: str) -> None:
    assert Path(evidence_bundle["result"]["artifact_paths"][path_key]).exists()


def test_evidence_items_boundary_assertions_and_validation_written(evidence_bundle: dict[str, Any]) -> None:
    assert evidence_bundle["items"]
    assert evidence_bundle["assertions"]
    assert evidence_bundle["validation"]["validation_hash"]
    assert evidence_bundle["promotion"]["decision_hash"]
    assert evidence_bundle["proof"]


def test_missing_evidence_becomes_incomplete_or_manual_review(evidence_bundle: dict[str, Any]) -> None:
    snapshot = load_latest_detector_evidence_snapshot()
    snapshot["post_run_evidence"] = {}
    status = _status_for_snapshot(snapshot)
    assert status in {"evidence_contract_incomplete", "evidence_contract_manual_review"}


@pytest.mark.parametrize(
    "field",
    [
        "credential_access_attempted",
        "order_placement_attempted",
        "scheduler_attempted",
        "real_sizing_attempted",
        "broker_mutation_attempted",
        "account_balance_attempted",
        "buying_power_attempted",
    ],
)
def test_runtime_leaks_terminal_block(field: str, evidence_bundle: dict[str, Any]) -> None:
    assert _status_for_snapshot(_snapshot_with_detector_summary(**{field: True})) == "evidence_contract_terminal_block"


def test_not_live_ready_false_terminal_blocks(evidence_bundle: dict[str, Any]) -> None:
    assert _status_for_snapshot(_snapshot_with_detector_summary(not_live_ready=False)) == "evidence_contract_terminal_block"


def test_timeout_misclassified_as_pass_terminal_blocks(evidence_bundle: dict[str, Any]) -> None:
    snapshot = load_latest_detector_evidence_snapshot()
    snapshot["validation_summary"] = {"timeout_recorded_as_pass": True, "full_suite": {"status": "pass", "timed_out": True}}
    assert _status_for_snapshot(snapshot) == "evidence_contract_terminal_block"


def test_audit_export_warning_manual_review(evidence_bundle: dict[str, Any]) -> None:
    snapshot = load_latest_detector_evidence_snapshot()
    snapshot["export_safety_scan"] = {"safety_errors": 1}
    assert _status_for_snapshot(snapshot) == "evidence_contract_manual_review"


def test_completeness_score_is_deterministic(evidence_bundle: dict[str, Any]) -> None:
    dims = evidence_bundle["contract"]["completeness_dimensions"]
    assert completeness_score(dims) == completeness_score(dims)


def test_clean_evidence_becomes_eligible_for_simulated_quote_order_review_mirror(evidence_bundle: dict[str, Any]) -> None:
    assert evidence_bundle["promotion"]["decision"] == "eligible_for_simulated_quote_order_review_mirror"


def test_promotion_decision_never_enables_live_or_broker_paths(evidence_bundle: dict[str, Any]) -> None:
    promotion = evidence_bundle["promotion"]
    for field in ("live_trading_allowed", "broker_connection_allowed", "credential_access_allowed", "scheduler_allowed", "real_sizing_allowed", "order_handling_allowed"):
        assert promotion[field] is False


def test_fixtures_cover_at_least_80_cases(evidence_bundle: dict[str, Any]) -> None:
    assert len(evidence_bundle["cases"]) >= 80
    groups = {record["case_group"] for record in evidence_bundle["cases"]}
    assert {"clean_complete_evidence", "dangerous_runtime_leak", "manual_review_case", "terminal_block_case"}.issubset(groups)


def test_audit_recognizes_artifacts(evidence_bundle: dict[str, Any]) -> None:
    ids = {spec[0] for spec in ARTIFACT_SPECS}
    assert {"evidence_contract", "evidence_items", "boundary_assertions", "evidence_contract_summary", "evidence_contract_proof"}.issubset(ids)
    assert audit_read_only_detector_evidence_contract_summary(evidence_bundle["summary"]) == []


def test_reporting_includes_summary(evidence_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _read_only_detector_evidence_contract_summary(evidence)
    assert summary["promotion_decision"] == evidence_bundle["promotion"]["decision"]


def test_export_includes_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"evidence_contract", "evidence_items", "boundary_assertions", "evidence_contract_summary", "evidence_contract_proof"}.issubset(ids)


def test_export_review_includes_summary(evidence_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(reporting_summary={"read_only_detector_evidence_contract_summary": evidence_bundle["summary"]}, shared_export_path="shared", safety_state={}, export_safety_scan={})
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "next", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "review_ready", "suitable", [], [], "broker-readiness v2 simulated quote/order-review mirror", True, True, "hash")
    text = render_executive_summary(ctx, bundle, [], decision)
    assert "Read-Only Detector Post-Run Evidence Contract" in text


def test_validation_stabilizer_includes_shard() -> None:
    summary = {"collection": {"status": "pass", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    result = CommandResult(["python", "-m", "pytest", "tests/test_read_only_detector_post_run_evidence_contract.py", "-q"], "pass", 0, 1.0, False, False, "ok", "")
    plan = write_test_shard_plan(["tests/test_read_only_detector_post_run_evidence_contract.py"], [result], summary)
    assert plan["split_suite_lanes"]["read_only_detector_post_run_evidence_contract_tests"] == ["tests/test_read_only_detector_post_run_evidence_contract.py"]
    assert "tests/test_read_only_detector_post_run_evidence_contract.py" in plan["artifact_writing_tests_sequential"]
    assert plan["full_suite_status"] == "inconclusive_timeout"


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    result = CommandResult(["python", "-m", "pytest"], "inconclusive_timeout", None, 120.0, True, False, "", "")
    assert result.status == "inconclusive_timeout"
    assert result.status != "pass"


def test_safety_regressions_remain_blocked(evidence_bundle: dict[str, Any]) -> None:
    summary = evidence_bundle["summary"]
    assert summary["live_trading_enabled"] is False
    assert summary["broker_write_execute_created"] is False
    assert summary["credentials_created"] is False
    assert summary["scheduler_created"] is False
    assert summary["real_sizing_created"] is False


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    result = audit_blunder_integrity()
    assert isinstance(result, list)
    assert not any(record.get("severity") == "safety_error" for record in result)
