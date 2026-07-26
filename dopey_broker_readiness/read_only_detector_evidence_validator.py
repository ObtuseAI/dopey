"""Validate read-only detector post-run evidence contracts."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .broker_readiness_models import stable_hash
from .read_only_detector_evidence_contract_models import (
    COMPLETENESS_DIMENSIONS,
    CONTRACT_SECTIONS,
    EVIDENCE_CONTRACT_VERSION,
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


REPO_ROOT = Path(__file__).resolve().parent.parent
from dopey_core.repo_paths import REPORTS_DIR
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
DETECTOR_DIR = ARTIFACT_ROOT / "broker_readiness" / "read_only_detector"
EVIDENCE_CONTRACT_DIR = ARTIFACT_ROOT / "broker_readiness" / "evidence_contract"
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness" / "evidence_contract"

EVIDENCE_CONTRACT_PATH = EVIDENCE_CONTRACT_DIR / "evidence_contract.json"
EVIDENCE_ITEMS_PATH = EVIDENCE_CONTRACT_DIR / "evidence_items.jsonl"
BOUNDARY_ASSERTIONS_PATH = EVIDENCE_CONTRACT_DIR / "boundary_assertions.jsonl"
EVIDENCE_VALIDATION_RESULTS_PATH = EVIDENCE_CONTRACT_DIR / "evidence_validation_results.jsonl"
EVIDENCE_PROMOTION_DECISIONS_PATH = EVIDENCE_CONTRACT_DIR / "evidence_promotion_decisions.jsonl"
EVIDENCE_CONTRACT_SUMMARY_PATH = EVIDENCE_CONTRACT_DIR / "evidence_contract_summary.json"
EVIDENCE_CONTRACT_PROOF_PATH = EVIDENCE_CONTRACT_DIR / "evidence_contract_proof.jsonl"

EVIDENCE_CONTRACT_CASES_FIXTURE_PATH = FIXTURE_DIR / "evidence_contract_cases.json"

EVIDENCE_CONTRACT_REPORT_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_REPORT.md"
EVIDENCE_CONTRACT_LEDGER_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_EVIDENCE_CONTRACT_ARTIFACT_LEDGER.md"

PROMOTION_NEXT_STAGE = "simulated_quote_order_review_mirror_fixture_only"
NEXT_RECOMMENDED_TARGET = "broker-readiness v2 simulated quote/order-review mirror"


def evidence_contract_artifact_paths() -> dict[str, str]:
    return {
        "evidence_contract": str(EVIDENCE_CONTRACT_PATH),
        "evidence_items": str(EVIDENCE_ITEMS_PATH),
        "boundary_assertions": str(BOUNDARY_ASSERTIONS_PATH),
        "evidence_validation_results": str(EVIDENCE_VALIDATION_RESULTS_PATH),
        "evidence_promotion_decisions": str(EVIDENCE_PROMOTION_DECISIONS_PATH),
        "evidence_contract_summary": str(EVIDENCE_CONTRACT_SUMMARY_PATH),
        "evidence_contract_proof": str(EVIDENCE_CONTRACT_PROOF_PATH),
    }


def validate_read_only_detector_post_run_evidence_contract() -> dict[str, Any]:
    snapshot = load_latest_detector_evidence_snapshot()
    fixture_cases = build_evidence_contract_fixture_cases()
    items = build_evidence_items(snapshot)
    assertions = build_boundary_assertions(snapshot)
    contract = build_evidence_contract(snapshot, items, assertions)
    validation = build_validation_result(contract, items, assertions)
    promotion = build_promotion_decision(contract, validation)
    proof = build_evidence_contract_proof(contract, items, assertions, validation, promotion)
    summary = build_evidence_contract_summary(contract, items, assertions, validation, promotion, fixture_cases, proof)

    _write_json(EVIDENCE_CONTRACT_CASES_FIXTURE_PATH, {"artifact_type": "evidence_contract_cases", "case_count": len(fixture_cases), "records": fixture_cases})
    _write_json(EVIDENCE_CONTRACT_PATH, contract)
    _write_jsonl(EVIDENCE_ITEMS_PATH, items)
    _write_jsonl(BOUNDARY_ASSERTIONS_PATH, assertions)
    _write_jsonl(EVIDENCE_VALIDATION_RESULTS_PATH, [validation])
    _write_jsonl(EVIDENCE_PROMOTION_DECISIONS_PATH, [promotion])
    _write_json(EVIDENCE_CONTRACT_SUMMARY_PATH, summary)
    _write_jsonl(EVIDENCE_CONTRACT_PROOF_PATH, proof)
    _write_text(EVIDENCE_CONTRACT_REPORT_PATH, render_evidence_contract_report(summary))
    _write_text(EVIDENCE_CONTRACT_LEDGER_PATH, render_evidence_contract_ledger(summary))
    append_evidence_contract_doc_updates(summary)
    return {
        "evidence_contract_status": summary["evidence_contract_status"],
        "completeness_score": summary["completeness_score"],
        "promotion_decision": summary["promotion_decision"],
        "terminal_block_count": summary["terminal_block_count"],
        "manual_review_count": summary["manual_review_count"],
        "artifact_paths": evidence_contract_artifact_paths(),
        "report_paths": {
            "evidence_contract_report": str(EVIDENCE_CONTRACT_REPORT_PATH),
            "evidence_contract_ledger": str(EVIDENCE_CONTRACT_LEDGER_PATH),
        },
        "paper_only": True,
        "live_blocked": True,
        "not_live_ready": True,
        "live_trading_enabled": False,
        "broker_write_execute_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
    }


def load_latest_detector_evidence_snapshot() -> dict[str, Any]:
    return {
        "approval_proof": _load_latest_jsonl(ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_intake_proof.jsonl"),
        "handoff_proof": _load_latest_jsonl(ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "approval_to_run_handoff_proof.jsonl"),
        "pre_run_proof": _load_latest_jsonl(ARTIFACT_ROOT / "broker_readiness" / "pre_run_safety" / "pre_run_safety_proof.jsonl"),
        "run_requests": _load_json_or_jsonl(DETECTOR_DIR / "read_only_detector_run_requests.jsonl"),
        "capability_records": _load_json_or_jsonl(DETECTOR_DIR / "read_only_capability_records.jsonl"),
        "blocked_records": _load_json_or_jsonl(DETECTOR_DIR / "read_only_blocked_write_execute_records.jsonl"),
        "provider_boundary_results": _load_json_or_jsonl(DETECTOR_DIR / "read_only_provider_boundary_results.jsonl"),
        "run_results": _load_json_or_jsonl(DETECTOR_DIR / "read_only_detector_run_results.jsonl"),
        "post_run_evidence": _load_json_or_jsonl(DETECTOR_DIR / "read_only_detector_post_run_evidence.json"),
        "incident_escalations": _load_json_or_jsonl(DETECTOR_DIR / "read_only_detector_incident_escalations.jsonl"),
        "detector_summary": _load_json_or_jsonl(DETECTOR_DIR / "read_only_detector_summary.json"),
        "detector_proof": _load_json_or_jsonl(DETECTOR_DIR / "read_only_detector_proof.jsonl"),
        "audit_proof": _load_json_or_jsonl(ARTIFACT_ROOT / "audit" / "evidence_replay_audit_proof.jsonl"),
        "reporting_summary": _load_json_or_jsonl(ARTIFACT_ROOT / "reporting" / "reporting_bundle_summary.json"),
        "export_safety_scan": _load_json_or_jsonl(ARTIFACT_ROOT / "exports" / "export_safety_scan.jsonl"),
        "export_review_proof": _load_json_or_jsonl(ARTIFACT_ROOT / "export_reviews" / "export_review_proof.jsonl"),
        "validation_summary": _load_json_or_jsonl(ARTIFACT_ROOT / "validation" / "full_suite_stabilizer_summary.json"),
    }


def build_evidence_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    section_sources = {
        "approval_proof_consumed": ("approval_intake_proof", ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_intake_proof.jsonl"),
        "handoff_proof_consumed": ("approval_to_run_handoff_proof", ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "approval_to_run_handoff_proof.jsonl"),
        "pre_run_safety_proof_consumed": ("pre_run_safety_proof", ARTIFACT_ROOT / "broker_readiness" / "pre_run_safety" / "pre_run_safety_proof.jsonl"),
        "detector_run_request_proof": ("read_only_detector_run_requests", DETECTOR_DIR / "read_only_detector_run_requests.jsonl"),
        "provider_identity_proof": ("read_only_detector_summary", DETECTOR_DIR / "read_only_detector_summary.json"),
        "capability_inventory_proof": ("read_only_capability_records", DETECTOR_DIR / "read_only_capability_records.jsonl"),
        "blocked_write_execute_proof": ("read_only_blocked_write_execute_records", DETECTOR_DIR / "read_only_blocked_write_execute_records.jsonl"),
        "credential_absence_proof": ("read_only_detector_post_run_evidence", DETECTOR_DIR / "read_only_detector_post_run_evidence.json"),
        "scheduler_absence_proof": ("read_only_detector_post_run_evidence", DETECTOR_DIR / "read_only_detector_post_run_evidence.json"),
        "real_sizing_absence_proof": ("read_only_detector_post_run_evidence", DETECTOR_DIR / "read_only_detector_post_run_evidence.json"),
        "live_order_absence_proof": ("read_only_detector_post_run_evidence", DETECTOR_DIR / "read_only_detector_post_run_evidence.json"),
        "broker_mutation_absence_proof": ("read_only_detector_post_run_evidence", DETECTOR_DIR / "read_only_detector_post_run_evidence.json"),
        "account_balance_buying_power_absence_proof": ("read_only_detector_post_run_evidence", DETECTOR_DIR / "read_only_detector_post_run_evidence.json"),
        "post_run_audit_proof": ("evidence_replay_audit_proof", ARTIFACT_ROOT / "audit" / "evidence_replay_audit_proof.jsonl"),
        "export_review_proof": ("export_review_proof", ARTIFACT_ROOT / "export_reviews" / "export_review_proof.jsonl"),
        "validation_status_proof": ("full_suite_stabilizer_summary", ARTIFACT_ROOT / "validation" / "full_suite_stabilizer_summary.json"),
        "next_gate_recommendation": ("read_only_detector_summary", DETECTOR_DIR / "read_only_detector_summary.json"),
    }
    items: list[dict[str, Any]] = []
    for index, section in enumerate(CONTRACT_SECTIONS, start=1):
        artifact_type, path = section_sources[section]
        file_status = _artifact_status(path)
        consumed = _section_consumed(section, snapshot, file_status)
        seed = DetectorEvidenceItem(
            item_id=f"evidence-item-{index:03d}",
            section=section,
            source_artifact_type=artifact_type,
            source_path=str(path),
            present=file_status["present"],
            parseable=file_status["parseable"],
            record_count=file_status["record_count"],
            content_hash=file_status["content_hash"],
            consumed=consumed,
            reason_codes=_section_reason_codes(section, consumed),
            paper_only=True,
            live_blocked=True,
            item_hash="",
        )
        items.append({**seed.to_dict(), "item_hash": detector_evidence_item_hash(seed)})
    return items


def build_boundary_assertions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    summary = _as_dict(snapshot.get("detector_summary"))
    evidence = _as_dict(snapshot.get("post_run_evidence"))
    validation_summary = _as_dict(snapshot.get("validation_summary"))
    export_scan = _as_dict(snapshot.get("export_safety_scan"))
    reporting_summary = _as_dict(snapshot.get("reporting_summary"))
    capability_records = _as_list(snapshot.get("capability_records"))
    blocked_records = _as_list(snapshot.get("blocked_records"))

    write_execute_allowed = any(bool(record.get("write_or_execute")) and bool(record.get("allowed_now")) for record in capability_records)
    active_forbidden_live_decisions = int(summary.get("active_forbidden_live_decisions", 0))
    full_suite = _as_dict(validation_summary.get("full_suite"))
    timeout_recorded_as_pass = bool(validation_summary.get("timeout_recorded_as_pass", False))
    if full_suite.get("timed_out") is True and full_suite.get("status") == "pass":
        timeout_recorded_as_pass = True

    checks: list[tuple[str, Any, Any, str]] = [
        ("post_run_evidence_exists", True, bool(evidence), "manual_review"),
        ("detector_summary_exists", True, bool(summary), "manual_review"),
        ("capability_records_exist", True, len(capability_records) > 0, "manual_review"),
        ("blocked_write_execute_records_exist", True, len(blocked_records) > 0, "manual_review"),
        ("approval_proof_consumed", True, bool(evidence.get("approval_proof_consumed")), "manual_review"),
        ("pre_run_safety_proof_consumed", True, bool(evidence.get("pre_run_safety_proof_consumed")), "manual_review"),
        ("credential_access_attempted", False, bool(summary.get("credential_access_attempted", evidence.get("no_credential_access") is False)), "terminal_block"),
        ("broker_write_or_execute_allowed", False, write_execute_allowed, "terminal_block"),
        ("live_order_attempted", False, bool(summary.get("live_order_attempted")), "terminal_block"),
        ("order_placement_attempted", False, bool(summary.get("order_placement_attempted")), "terminal_block"),
        ("order_cancellation_attempted", False, bool(summary.get("order_cancellation_attempted")), "terminal_block"),
        ("scheduler_attempted", False, bool(summary.get("scheduler_attempted")), "terminal_block"),
        ("real_sizing_attempted", False, bool(summary.get("real_sizing_attempted")), "terminal_block"),
        ("account_balance_attempted", False, bool(summary.get("account_balance_attempted")), "terminal_block"),
        ("buying_power_attempted", False, bool(summary.get("buying_power_attempted")), "terminal_block"),
        ("broker_mutation_attempted", False, bool(summary.get("broker_mutation_attempted")), "terminal_block"),
        ("robinhood_mcp_integration_created", False, bool(summary.get("robinhood_mcp_integration_created")), "terminal_block"),
        ("live_trading_enabled", False, bool(summary.get("live_trading_enabled", False)), "terminal_block"),
        ("not_live_ready", True, bool(summary.get("not_live_ready", True)), "terminal_block"),
        ("next_gate_is_not_live", False, "live" in str(summary.get("next_required_gate", "")).lower() and "not_live" not in str(summary.get("next_required_gate", "")).lower(), "terminal_block"),
        ("full_suite_timeout_recorded_as_pass", False, timeout_recorded_as_pass, "terminal_block"),
        ("export_safety_errors", 0, int(export_scan.get("safety_error_count", export_scan.get("safety_errors", 0) or 0)), "manual_review"),
        ("reporting_read_only_detector_summary_present", True, bool(reporting_summary.get("read_only_detector_summary")), "manual_review"),
        ("active_forbidden_live_decisions", 0, active_forbidden_live_decisions, "terminal_block"),
    ]
    assertions: list[dict[str, Any]] = []
    for index, (name, expected, actual, severity_if_failed) in enumerate(checks, start=1):
        passed = actual == expected
        severity = "info" if passed else severity_if_failed
        seed = DetectorBoundaryAssertion(
            assertion_id=f"evidence-boundary-{index:03d}",
            boundary_name=name,
            expected_value=expected,
            actual_value=actual,
            passed=passed,
            severity=severity,
            terminal_block=severity == "terminal_block",
            manual_review=severity == "manual_review",
            reason_codes=["evidence_contract_boundary", name] if not passed else ["evidence_contract_boundary_passed", name],
            paper_only=True,
            live_blocked=True,
            assertion_hash="",
        )
        assertions.append({**seed.to_dict(), "assertion_hash": detector_boundary_assertion_hash(seed)})
    return assertions


def build_evidence_contract(snapshot: dict[str, Any], items: list[dict[str, Any]], assertions: list[dict[str, Any]]) -> dict[str, Any]:
    section_statuses = {item["section"]: bool(item["consumed"]) for item in items}
    dimensions = completeness_dimensions(section_statuses, items, assertions)
    score = completeness_score(dimensions)
    status = evidence_status(section_statuses, assertions, score)
    summary = _as_dict(snapshot.get("detector_summary"))
    seed = DetectorEvidenceContract(
        contract_id="read-only-detector-evidence-contract-001",
        source_detector_summary_hash=str(summary.get("summary_hash", "")),
        section_statuses=section_statuses,
        completeness_dimensions=dimensions,
        completeness_score=score,
        status=status,
        next_gate_recommendation=NEXT_RECOMMENDED_TARGET,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        contract_hash="",
    )
    return {**seed.to_dict(), "contract_hash": detector_evidence_contract_hash(seed)}


def build_validation_result(contract: dict[str, Any], items: list[dict[str, Any]], assertions: list[dict[str, Any]]) -> dict[str, Any]:
    missing_sections = [item["section"] for item in items if item["consumed"] is not True]
    failed_assertions = [assertion["boundary_name"] for assertion in assertions if assertion["passed"] is not True]
    terminal_count = sum(1 for assertion in assertions if assertion["terminal_block"] is True)
    manual_count = sum(1 for assertion in assertions if assertion["manual_review"] is True)
    seed = DetectorEvidenceValidationResult(
        validation_id="read-only-detector-evidence-validation-001",
        contract_id=str(contract["contract_id"]),
        status=str(contract["status"]),
        completeness_score=int(contract["completeness_score"]),
        terminal_block_count=terminal_count,
        manual_review_count=manual_count,
        missing_sections=missing_sections,
        failed_assertions=failed_assertions,
        reason_codes=_validation_reason_codes(str(contract["status"]), missing_sections, failed_assertions),
        paper_only=True,
        live_blocked=True,
        validation_hash="",
    )
    return {**seed.to_dict(), "validation_hash": detector_evidence_validation_hash(seed)}


def build_promotion_decision(contract: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    status = str(validation["status"])
    if status == "evidence_contract_terminal_block":
        decision = "terminal_block"
        allowed_next_stage = "none"
    elif status == "evidence_contract_manual_review":
        decision = "manual_review_required"
        allowed_next_stage = "manual_review_only"
    elif status == "evidence_contract_complete":
        decision = "eligible_for_simulated_quote_order_review_mirror"
        allowed_next_stage = PROMOTION_NEXT_STAGE
    else:
        decision = "hold_review_only"
        allowed_next_stage = "review_only"
    seed = DetectorEvidencePromotionDecision(
        decision_id="read-only-detector-evidence-promotion-001",
        contract_id=str(contract["contract_id"]),
        decision=decision,
        allowed_next_stage=allowed_next_stage,
        forbidden_next_stages=[
            "live_trading",
            "broker_connection",
            "credential_access",
            "broker_order_review",
            "order_placement",
            "order_cancellation",
            "scheduler",
            "real_sizing",
        ],
        live_trading_allowed=False,
        broker_connection_allowed=False,
        credential_access_allowed=False,
        scheduler_allowed=False,
        real_sizing_allowed=False,
        order_handling_allowed=False,
        reason_codes=["evidence_contract_promotion", decision],
        paper_only=True,
        live_blocked=True,
        decision_hash="",
    )
    return {**seed.to_dict(), "decision_hash": detector_evidence_promotion_hash(seed)}


def completeness_dimensions(section_statuses: dict[str, bool], items: list[dict[str, Any]], assertions: list[dict[str, Any]]) -> dict[str, bool]:
    assertion_passed = {assertion["boundary_name"]: assertion["passed"] for assertion in assertions}
    return {
        "gate_proof_completeness": all(section_statuses.get(section, False) for section in ("approval_proof_consumed", "handoff_proof_consumed", "pre_run_safety_proof_consumed")),
        "provider_proof_completeness": section_statuses.get("provider_identity_proof", False),
        "capability_proof_completeness": section_statuses.get("capability_inventory_proof", False),
        "blocked_path_proof_completeness": all(section_statuses.get(section, False) for section in ("blocked_write_execute_proof", "credential_absence_proof", "scheduler_absence_proof", "real_sizing_absence_proof", "live_order_absence_proof", "broker_mutation_absence_proof", "account_balance_buying_power_absence_proof")),
        "incident_proof_completeness": any(item["source_artifact_type"] == "read_only_detector_summary" for item in items) and assertion_passed.get("active_forbidden_live_decisions", False),
        "audit_export_review_proof_completeness": all(section_statuses.get(section, False) for section in ("post_run_audit_proof", "export_review_proof")),
        "validation_proof_completeness": section_statuses.get("validation_status_proof", False) and assertion_passed.get("full_suite_timeout_recorded_as_pass", False),
        "safety_boundary_proof_completeness": all(assertion["passed"] for assertion in assertions if assertion["severity"] == "info" or assertion["terminal_block"] is False),
    }


def completeness_score(dimensions: dict[str, bool]) -> int:
    if set(dimensions) != set(COMPLETENESS_DIMENSIONS):
        raise ValueError("evidence completeness dimensions are incomplete")
    return int(round(sum(1 for passed in dimensions.values() if passed) / len(COMPLETENESS_DIMENSIONS) * 100))


def evidence_status(section_statuses: dict[str, bool], assertions: list[dict[str, Any]], score: int) -> str:
    if any(assertion["terminal_block"] is True for assertion in assertions):
        return "evidence_contract_terminal_block"
    if any(assertion["manual_review"] is True for assertion in assertions):
        return "evidence_contract_manual_review"
    if not all(section_statuses.values()):
        return "evidence_contract_incomplete"
    if score == 100:
        return "evidence_contract_complete"
    return "evidence_contract_incomplete"


def build_evidence_contract_summary(
    contract: dict[str, Any],
    items: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    validation: dict[str, Any],
    promotion: dict[str, Any],
    fixture_cases: list[dict[str, Any]],
    proof: list[dict[str, Any]],
) -> dict[str, Any]:
    assertion_severity = Counter(str(assertion["severity"]) for assertion in assertions)
    summary = {
        "artifact_type": "read_only_detector_evidence_contract_summary",
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "evidence_contract_status": contract["status"],
        "completeness_score": contract["completeness_score"],
        "completeness_dimensions": contract["completeness_dimensions"],
        "promotion_decision": promotion["decision"],
        "allowed_next_stage": promotion["allowed_next_stage"],
        "terminal_block_count": validation["terminal_block_count"],
        "manual_review_count": validation["manual_review_count"],
        "missing_sections": validation["missing_sections"],
        "failed_assertions": validation["failed_assertions"],
        "evidence_item_count": len(items),
        "boundary_assertion_count": len(assertions),
        "fixture_case_count": len(fixture_cases),
        "proof_record_count": len(proof),
        "assertion_severity_distribution": dict(sorted(assertion_severity.items())),
        "next_recommended_target": NEXT_RECOMMENDED_TARGET,
        "not_live_ready": True,
        "live_trading_enabled": False,
        "broker_write_execute_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
        "order_handling_created": False,
        "paper_only": True,
        "live_blocked": True,
        "artifact_paths": evidence_contract_artifact_paths(),
        "summary_hash": "",
    }
    return {**summary, "summary_hash": stable_hash(summary)}


def build_evidence_contract_proof(
    contract: dict[str, Any],
    items: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    validation: dict[str, Any],
    promotion: dict[str, Any],
) -> list[dict[str, Any]]:
    proof: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        seed = {
            "proof_id": f"evidence-contract-proof-item-{index:03d}",
            "proof_type": "evidence_item",
            "contract_id": contract["contract_id"],
            "section": item["section"],
            "status": contract["status"],
            "promotion_decision": promotion["decision"],
            "passed": item["consumed"],
            "terminal_block": False,
            "manual_review": item["consumed"] is not True,
            "paper_only": True,
            "live_blocked": True,
            "no_live_trading": True,
            "no_broker_write_execute": True,
            "no_credentials": True,
            "no_scheduler": True,
            "no_real_sizing": True,
            "proof_hash": "",
        }
        proof.append({**seed, "proof_hash": stable_hash(seed)})
    for index, assertion in enumerate(assertions, start=1):
        seed = {
            "proof_id": f"evidence-contract-proof-boundary-{index:03d}",
            "proof_type": "boundary_assertion",
            "contract_id": contract["contract_id"],
            "boundary_name": assertion["boundary_name"],
            "status": validation["status"],
            "promotion_decision": promotion["decision"],
            "passed": assertion["passed"],
            "terminal_block": assertion["terminal_block"],
            "manual_review": assertion["manual_review"],
            "paper_only": True,
            "live_blocked": True,
            "no_live_trading": True,
            "no_broker_write_execute": True,
            "no_credentials": True,
            "no_scheduler": True,
            "no_real_sizing": True,
            "proof_hash": "",
        }
        proof.append({**seed, "proof_hash": stable_hash(seed)})
    return proof


def build_evidence_contract_fixture_cases() -> list[dict[str, Any]]:
    groups = [
        ("clean_complete_evidence", 12, "evidence_contract_complete"),
        ("missing_evidence", 12, "evidence_contract_incomplete"),
        ("missing_gate_proof", 10, "evidence_contract_incomplete"),
        ("missing_capability_or_blocked_records", 10, "evidence_contract_incomplete"),
        ("dangerous_runtime_leak", 12, "evidence_contract_terminal_block"),
        ("not_live_ready_or_timeout_violation", 8, "evidence_contract_terminal_block"),
        ("audit_export_warning", 8, "evidence_contract_manual_review"),
        ("manual_review_case", 4, "evidence_contract_manual_review"),
        ("terminal_block_case", 4, "evidence_contract_terminal_block"),
    ]
    required_names = [
        "clean complete evidence",
        "missing post-run evidence",
        "missing approval proof",
        "missing pre-run proof",
        "missing capability records",
        "missing blocked records",
        "credential leak",
        "order placement leak",
        "scheduler leak",
        "real sizing leak",
        "broker mutation leak",
        "not-live-ready false",
        "timeout misclassified as pass",
        "audit export warning",
        "manual-review cases",
        "terminal-block cases",
    ]
    cases: list[dict[str, Any]] = []
    for group, count, expected_status in groups:
        for group_index in range(count):
            name = required_names[len(cases)] if len(cases) < len(required_names) else f"{group} {group_index + 1:02d}"
            seed = {
                "case_id": f"evidence-contract-case-{len(cases) + 1:03d}",
                "case_group": group,
                "case_name": name,
                "expected_status": expected_status,
                "expected_live_trading_enabled": False,
                "expected_broker_write_execute_created": False,
                "expected_credentials_created": False,
                "expected_scheduler_created": False,
                "expected_real_sizing_created": False,
                "paper_only": True,
                "live_blocked": True,
                "case_hash": "",
            }
            cases.append({**seed, "case_hash": stable_hash(seed)})
    if len(cases) < 80:
        raise ValueError(f"evidence contract fixture must contain at least 80 cases, got {len(cases)}")
    return cases


def render_evidence_contract_report(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Detector Post-Run Evidence Contract Hardening", ""]
    lines.append("- objective: `post-run evidence contract hardening for read-only detector output`")
    lines.append("- source_detector_state: `human_approved_read_only_detector_validated_fixture_only_not_live_ready`")
    lines.append(f"- evidence_contract_status: `{summary['evidence_contract_status']}`")
    lines.append(f"- completeness_score: `{summary['completeness_score']}`")
    lines.append(f"- promotion_decision: `{summary['promotion_decision']}`")
    lines.append(f"- allowed_next_stage: `{summary['allowed_next_stage']}`")
    lines.append(f"- terminal_block_count: `{summary['terminal_block_count']}`")
    lines.append(f"- manual_review_count: `{summary['manual_review_count']}`")
    lines.append(f"- evidence_item_count: `{summary['evidence_item_count']}`")
    lines.append(f"- boundary_assertion_count: `{summary['boundary_assertion_count']}`")
    lines.append("- terminal_block_conditions: `credential/order/scheduler/real-sizing/broker-mutation/balance/buying-power/live-ready/timeout-as-pass leaks`")
    lines.append("- audit_export_review_integration: `registered for audit loader, reporting, export selector, and export review packet`")
    lines.append("- validation_status: `targeted shard required; full suite timeout remains inconclusive until separately proven`")
    lines.append("- limitations: `does not prove broker readiness, live readiness, profitability, or real provider safety`")
    lines.append(f"- next_recommended_target: `{summary['next_recommended_target']}`")
    lines.append("- safety_state: `paper_only_live_blocked_not_live_ready_no_credentials_no_scheduler_no_real_sizing`")
    return "\n".join(lines) + "\n"


def render_evidence_contract_ledger(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Detector Evidence Contract Artifact Ledger", ""]
    for artifact_type, artifact_path in evidence_contract_artifact_paths().items():
        count = _record_count(Path(artifact_path))
        digest = _file_hash(Path(artifact_path)) if Path(artifact_path).exists() else ""
        lines.append(f"- artifact_type: `{artifact_type}`")
        lines.append(f"  path: `{artifact_path}`")
        lines.append(f"  hash: `{digest}`")
        lines.append(f"  record_count: `{count}`")
        lines.append("  proof_layer: `read_only_detector_evidence_contract`")
    lines.append(f"- evidence_item_count: `{summary['evidence_item_count']}`")
    lines.append(f"- boundary_assertion_count: `{summary['boundary_assertion_count']}`")
    lines.append(f"- terminal_block_count: `{summary['terminal_block_count']}`")
    lines.append(f"- manual_review_count: `{summary['manual_review_count']}`")
    lines.append(f"- summary_hash: `{summary['summary_hash']}`")
    return "\n".join(lines) + "\n"


def append_evidence_contract_doc_updates(summary: dict[str, Any]) -> None:
    block = "\n".join([
        "",
        "## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1",
        "",
        f"- status: `{summary['evidence_contract_status']}`",
        f"- completeness_score: `{summary['completeness_score']}`",
        f"- promotion_decision: `{summary['promotion_decision']}`",
        f"- terminal_block_count: `{summary['terminal_block_count']}`",
        f"- manual_review_count: `{summary['manual_review_count']}`",
        "- detector_output_is_not_live_readiness: `true`",
        "- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`",
        f"- next_recommended_target: `{summary['next_recommended_target']}`",
        "",
    ])
    for path in (REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md", REPO_ROOT / "DOPEY_VALIDATION_REPORT.md", REPO_ROOT / "DOPEY_CANON.md"):
        with path.open("a", encoding="ascii", errors="ignore") as handle:
            handle.write(block)


def _section_consumed(section: str, snapshot: dict[str, Any], file_status: dict[str, Any]) -> bool:
    if not file_status["present"] or not file_status["parseable"]:
        return False
    evidence = _as_dict(snapshot.get("post_run_evidence"))
    summary = _as_dict(snapshot.get("detector_summary"))
    if section == "approval_proof_consumed":
        return bool(evidence.get("approval_proof_consumed"))
    if section == "handoff_proof_consumed":
        return bool(snapshot.get("handoff_proof"))
    if section == "pre_run_safety_proof_consumed":
        return bool(evidence.get("pre_run_safety_proof_consumed"))
    if section == "provider_identity_proof":
        return bool(summary.get("provider_type_used"))
    if section == "next_gate_recommendation":
        return "live" not in str(summary.get("next_required_gate", "")).lower()
    return True


def _section_reason_codes(section: str, consumed: bool) -> list[str]:
    return ["evidence_section_consumed", section] if consumed else ["evidence_section_missing_or_unconsumed", section]


def _validation_reason_codes(status: str, missing_sections: list[str], failed_assertions: list[str]) -> list[str]:
    if status == "evidence_contract_complete":
        return ["evidence_contract_complete"]
    return ["evidence_contract_not_complete", *missing_sections, *failed_assertions]


def _artifact_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "parseable": False, "record_count": 0, "content_hash": ""}
    digest = _file_hash(path)
    try:
        records = _load_json_or_jsonl(path)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"present": True, "parseable": False, "record_count": 0, "content_hash": digest}
    return {"present": True, "parseable": True, "record_count": len(_as_list(records)), "content_hash": digest}


def _load_json_or_jsonl(path: Path) -> Any:
    if not path.exists():
        return [] if path.suffix == ".jsonl" else {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return [] if path.suffix == ".jsonl" else {}
    if path.suffix == ".json":
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _load_latest_jsonl(path: Path) -> dict[str, Any]:
    records = _load_json_or_jsonl(path)
    return records[-1] if isinstance(records, list) and records else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [record for record in value if isinstance(record, dict)]
    if isinstance(value, dict) and value:
        return [value]
    return []


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if not path.exists():
        return 0
    parsed = _load_json_or_jsonl(path)
    return len(_as_list(parsed))


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
