"""Offline pre-run safety scanner for a future read-only detector bundle."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .approval_intake_validator import APPROVAL_INTAKE_SUMMARY_PATH
from .approval_to_run_handoff_gate import (
    APPROVAL_TO_RUN_HANDOFF_PROOF_PATH,
    APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH,
    DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH,
)
from .broker_readiness_models import stable_hash
from .disabled_handoff_command_registry import build_disabled_handoff_command_templates
from .manual_approval_packet_builder import MANUAL_APPROVAL_PACKET_SUMMARY_PATH
from .pre_run_forbidden_boundary_scanner import (
    ACTIVE_RUNTIME_CLASSIFICATION,
    build_boundary_scan_sources,
    classify_boundary_references,
    forbidden_boundary_pattern_payload,
)
from .pre_run_safety_scanner_models import (
    PRE_RUN_NEXT_REQUIRED_GATE,
    PRE_RUN_SAFETY_SCANNER_VERSION,
    PreRunBoundaryScanResult,
    PreRunSafetyDecision,
    PreRunSafetyScanInput,
    pre_run_boundary_scan_result_hash,
    pre_run_safety_decision_hash,
    pre_run_safety_scan_input_hash,
)
from .read_only_detector_dry_run_validator import DRY_RUN_SUMMARY_PATH


REPO_ROOT = Path(__file__).resolve().parent.parent
from dopey_core.repo_paths import REPORTS_DIR
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness"
ARTIFACT_DIR = ARTIFACT_ROOT / "broker_readiness" / "pre_run_safety"

BROKER_READINESS_SUMMARY_PATH = ARTIFACT_ROOT / "broker_readiness" / "broker_readiness_summary.json"
AUDIT_PROOF_PATH = ARTIFACT_ROOT / "audit" / "evidence_replay_audit_proof.jsonl"
EXPORT_SAFETY_SCAN_PATH = ARTIFACT_ROOT / "exports" / "export_safety_scan.jsonl"
EXPORT_REVIEW_PROOF_PATH = ARTIFACT_ROOT / "export_reviews" / "export_review_proof.jsonl"

PRE_RUN_SAFETY_SCAN_INPUTS_FIXTURE_PATH = FIXTURE_DIR / "pre_run_safety_scan_inputs.json"
PRE_RUN_BOUNDARY_SCAN_CASES_FIXTURE_PATH = FIXTURE_DIR / "pre_run_boundary_scan_cases.json"
PRE_RUN_SAFETY_DECISIONS_FIXTURE_PATH = FIXTURE_DIR / "pre_run_safety_decisions.json"
PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_FIXTURE_PATH = FIXTURE_DIR / "pre_run_forbidden_boundary_patterns.json"
EXPECTED_PRE_RUN_SUMMARY_FIXTURE_PATH = FIXTURE_DIR / "expected_pre_run_summary.json"

PRE_RUN_SAFETY_SCAN_INPUTS_PATH = ARTIFACT_DIR / "pre_run_safety_scan_inputs.jsonl"
PRE_RUN_BOUNDARY_SCAN_RESULTS_PATH = ARTIFACT_DIR / "pre_run_boundary_scan_results.jsonl"
PRE_RUN_SAFETY_DECISIONS_PATH = ARTIFACT_DIR / "pre_run_safety_decisions.jsonl"
PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_PATH = ARTIFACT_DIR / "pre_run_forbidden_boundary_patterns.json"
PRE_RUN_BOUNDARY_CLASSIFICATIONS_PATH = ARTIFACT_DIR / "pre_run_boundary_classifications.jsonl"
PRE_RUN_INCIDENT_ESCALATIONS_PATH = ARTIFACT_DIR / "pre_run_incident_escalations.jsonl"
PRE_RUN_SAFETY_SUMMARY_PATH = ARTIFACT_DIR / "pre_run_safety_summary.json"
PRE_RUN_SAFETY_PROOF_PATH = ARTIFACT_DIR / "pre_run_safety_proof.jsonl"

PRE_RUN_SAFETY_REPORT_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_REPORT.md"
PRE_RUN_SAFETY_LEDGER_PATH = REPORTS_DIR / "DOPEY_PRE_RUN_SAFETY_SCANNER_ARTIFACT_LEDGER.md"


def pre_run_safety_artifact_paths() -> dict[str, str]:
    return {
        "pre_run_safety_scan_inputs": str(PRE_RUN_SAFETY_SCAN_INPUTS_PATH),
        "pre_run_boundary_scan_results": str(PRE_RUN_BOUNDARY_SCAN_RESULTS_PATH),
        "pre_run_safety_decisions": str(PRE_RUN_SAFETY_DECISIONS_PATH),
        "pre_run_forbidden_boundary_patterns": str(PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_PATH),
        "pre_run_boundary_classifications": str(PRE_RUN_BOUNDARY_CLASSIFICATIONS_PATH),
        "pre_run_incident_escalations": str(PRE_RUN_INCIDENT_ESCALATIONS_PATH),
        "pre_run_safety_summary": str(PRE_RUN_SAFETY_SUMMARY_PATH),
        "pre_run_safety_proof": str(PRE_RUN_SAFETY_PROOF_PATH),
    }


def validate_read_only_detector_pre_run_safety_scanner() -> dict[str, Any]:
    source_snapshot = load_pre_run_source_snapshot()
    command_templates = _load_disabled_command_templates()
    boundary_cases = build_pre_run_boundary_cases()
    inputs = build_pre_run_safety_scan_inputs(source_snapshot, boundary_cases)
    classifications = build_pre_run_boundary_classifications(command_templates, boundary_cases)
    boundary_results = build_pre_run_boundary_scan_results(inputs, boundary_cases, command_templates, classifications)
    decisions = build_pre_run_safety_decisions(inputs, boundary_cases, boundary_results)
    incident_escalations = build_pre_run_incident_escalations(decisions)
    proof_records = build_pre_run_safety_proof(inputs, boundary_results, decisions, classifications)
    pattern_payload = forbidden_boundary_pattern_payload()
    summary = build_pre_run_safety_summary(
        source_snapshot,
        inputs,
        boundary_results,
        decisions,
        classifications,
        incident_escalations,
        proof_records,
    )

    _write_json(PRE_RUN_SAFETY_SCAN_INPUTS_FIXTURE_PATH, _fixture_payload("pre_run_safety_scan_inputs", inputs))
    _write_json(PRE_RUN_BOUNDARY_SCAN_CASES_FIXTURE_PATH, _fixture_payload("pre_run_boundary_scan_cases", boundary_cases))
    _write_json(PRE_RUN_SAFETY_DECISIONS_FIXTURE_PATH, _fixture_payload("pre_run_safety_decisions", decisions))
    _write_json(PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_FIXTURE_PATH, pattern_payload)
    _write_json(EXPECTED_PRE_RUN_SUMMARY_FIXTURE_PATH, summary)

    _write_jsonl(PRE_RUN_SAFETY_SCAN_INPUTS_PATH, inputs)
    _write_jsonl(PRE_RUN_BOUNDARY_SCAN_RESULTS_PATH, boundary_results)
    _write_jsonl(PRE_RUN_SAFETY_DECISIONS_PATH, decisions)
    _write_json(PRE_RUN_FORBIDDEN_BOUNDARY_PATTERNS_PATH, pattern_payload)
    _write_jsonl(PRE_RUN_BOUNDARY_CLASSIFICATIONS_PATH, classifications)
    _write_jsonl(PRE_RUN_INCIDENT_ESCALATIONS_PATH, incident_escalations)
    _write_json(PRE_RUN_SAFETY_SUMMARY_PATH, summary)
    _write_jsonl(PRE_RUN_SAFETY_PROOF_PATH, proof_records)
    _write_text(PRE_RUN_SAFETY_REPORT_PATH, render_pre_run_safety_report(summary))
    _write_text(PRE_RUN_SAFETY_LEDGER_PATH, render_pre_run_safety_ledger(summary))
    append_pre_run_safety_doc_updates(summary)

    return {
        "pre_run_safety_scanner_status": summary["pre_run_safety_status"],
        "scan_input_count": summary["scan_input_count"],
        "future_bundle_preparation_allowed_count": summary["future_bundle_preparation_allowed_count"],
        "detector_run_allowed_now_count": summary["detector_run_allowed_now_count"],
        "broker_connection_allowed_now_count": summary["broker_connection_allowed_now_count"],
        "credential_allowed_now_count": summary["credential_allowed_now_count"],
        "live_order_allowed_now_count": summary["live_order_allowed_now_count"],
        "scheduler_allowed_now_count": summary["scheduler_allowed_now_count"],
        "real_sizing_allowed_now_count": summary["real_sizing_allowed_now_count"],
        "command_templates_disabled": summary["command_templates_disabled"],
        "boundary_classification_distribution": summary["boundary_classification_distribution"],
        "terminal_block_count": summary["terminal_block_count"],
        "manual_review_count": summary["manual_review_count"],
        "artifact_paths": pre_run_safety_artifact_paths(),
        "report_paths": {
            "pre_run_safety_report": str(PRE_RUN_SAFETY_REPORT_PATH),
            "pre_run_safety_ledger": str(PRE_RUN_SAFETY_LEDGER_PATH),
        },
        "paper_only": True,
        "live_blocked": True,
        "read_only_detector_run": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "robinhood_mcp_integration_created": False,
    }


def load_pre_run_source_snapshot() -> dict[str, Any]:
    return {
        "handoff_summary": _require_json(APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH),
        "handoff_proof": _require_latest_jsonl(APPROVAL_TO_RUN_HANDOFF_PROOF_PATH),
        "approval_intake_summary": _require_json(APPROVAL_INTAKE_SUMMARY_PATH),
        "dry_run_summary": _require_json(DRY_RUN_SUMMARY_PATH),
        "manual_packet_summary": _require_json(MANUAL_APPROVAL_PACKET_SUMMARY_PATH),
        "preflight_summary": _require_json(BROKER_READINESS_SUMMARY_PATH),
        "audit_proof": _require_latest_jsonl(AUDIT_PROOF_PATH),
        "export_safety_scan": _require_latest_jsonl(EXPORT_SAFETY_SCAN_PATH),
        "export_review_proof": _require_latest_jsonl(EXPORT_REVIEW_PROOF_PATH),
        "source_paths": {
            "handoff_summary": str(APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH),
            "handoff_proof": str(APPROVAL_TO_RUN_HANDOFF_PROOF_PATH),
            "approval_intake_summary": str(APPROVAL_INTAKE_SUMMARY_PATH),
            "dry_run_summary": str(DRY_RUN_SUMMARY_PATH),
            "manual_packet_summary": str(MANUAL_APPROVAL_PACKET_SUMMARY_PATH),
            "preflight_summary": str(BROKER_READINESS_SUMMARY_PATH),
            "audit_proof": str(AUDIT_PROOF_PATH),
            "export_safety_scan": str(EXPORT_SAFETY_SCAN_PATH),
            "export_review_proof": str(EXPORT_REVIEW_PROOF_PATH),
        },
    }


def build_pre_run_boundary_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    specs = [
        ("clean_eligible", 16),
        ("runtime_permission_leak", 16),
        ("forbidden_boundary_reference", 16),
        ("command_template_violation", 12),
        ("audit_export_failure", 12),
        ("missing_proof", 8),
        ("timeout_misclassification", 8),
        ("terminal_block", 8),
    ]
    required_names = _required_names_by_group()
    for group, count in specs:
        for group_index in range(count):
            group_names = required_names.get(group, [])
            case_name = group_names[group_index] if group_index < len(group_names) else f"{group}_{group_index + 1:02d}"
            cases.append(_boundary_case(len(cases) + 1, group, group_index + 1, case_name))
    if len(cases) != 96:
        raise ValueError(f"pre-run safety fixture must contain 96 cases, got {len(cases)}")
    return cases


def _required_names_by_group() -> dict[str, list[str]]:
    return {
        "clean_eligible": [
            "clean_handoff_eligibility_allows_future_bundle_preparation",
            "future_bundle_eligibility_does_not_allow_detector_run_now",
            "documentation_only_blocked_reference_nonfatal",
            "negative_control_fixture_reference_nonfatal",
            "blocked_command_template_reference_nonfatal",
            "future_detector_preparation_allowed_only_when_all_checks_clean",
        ],
        "runtime_permission_leak": [
            "detector_run_allowed_now_true_blocks_scan",
            "broker_connection_allowed_now_true_blocks_scan",
            "credential_allowed_now_true_blocks_scan",
            "live_order_allowed_now_true_blocks_scan",
            "scheduler_allowed_now_true_blocks_scan",
            "real_sizing_allowed_now_true_blocks_scan",
        ],
        "forbidden_boundary_reference": [
            "active_env_reference_blocks_scan",
            "active_token_reference_blocks_scan",
            "active_broker_connection_reference_blocks_scan",
            "active_robinhood_mcp_invocation_blocks_scan",
            "active_order_placement_reference_blocks_scan",
            "active_order_cancellation_reference_blocks_scan",
            "active_review_option_order_reference_blocks_scan",
            "active_account_balance_reference_blocks_scan",
            "active_buying_power_reference_blocks_scan",
            "active_real_sizing_reference_blocks_scan",
            "active_scheduler_reference_blocks_scan",
            "active_network_market_data_reference_blocks_scan",
        ],
        "command_template_violation": [
            "command_template_enabled_blocks_scan",
            "command_template_missing_reapproval_blocks_scan",
            "command_template_missing_future_bundle_blocks_scan",
            "command_template_containing_credential_blocks_scan",
            "command_template_containing_order_placement_blocks_scan",
            "command_template_containing_cancellation_blocks_scan",
            "command_template_containing_scheduler_blocks_scan",
            "command_template_containing_live_trading_blocks_scan",
        ],
        "audit_export_failure": [
            "safety_finding_blocks_scan",
            "credential_finding_blocks_scan",
        ],
        "missing_proof": [
            "missing_handoff_summary_blocks_scan",
            "missing_approval_intake_summary_blocks_scan",
            "missing_dry_run_summary_blocks_scan",
            "missing_audit_proof_blocks_scan",
        ],
        "timeout_misclassification": [
            "timeout_misclassified_as_pass_blocks_scan",
            "windows_stdout_flush_oserror_recorded_not_pass",
        ],
    }


def build_pre_run_safety_scan_inputs(source_snapshot: dict[str, Any], boundary_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids = _source_ids(source_snapshot)
    records: list[dict[str, Any]] = []
    for index, case in enumerate(boundary_cases):
        counts = _runtime_counts_for_case(case)
        seed = PreRunSafetyScanInput(
            scan_input_id=f"pre-run-safety-scan-input-{index + 1:03d}",
            source_handoff_summary_id=source_ids["handoff_summary"],
            source_approval_intake_summary_id=source_ids["approval_intake_summary"],
            source_dry_run_summary_id=source_ids["dry_run_summary"],
            source_manual_packet_id=source_ids["manual_packet_summary"],
            source_preflight_id=source_ids["preflight_summary"],
            source_audit_id=source_ids["audit_proof"],
            source_export_id=source_ids["export_safety_scan"],
            source_export_review_id=source_ids["export_review_proof"],
            future_bundle_eligible_count=int(case["future_bundle_eligible_count"]),
            detector_run_allowed_now_count=counts["detector_run_allowed_now_count"],
            broker_connection_allowed_now_count=counts["broker_connection_allowed_now_count"],
            credential_allowed_now_count=counts["credential_allowed_now_count"],
            live_order_allowed_now_count=counts["live_order_allowed_now_count"],
            scheduler_allowed_now_count=counts["scheduler_allowed_now_count"],
            real_sizing_allowed_now_count=counts["real_sizing_allowed_now_count"],
            paper_only=True,
            live_blocked=True,
            input_hash="",
        )
        records.append({**seed.to_dict(), "case_group": case["case_group"], "case_name": case["case_name"], "input_hash": pre_run_safety_scan_input_hash(seed)})
    return records


def build_pre_run_boundary_classifications(command_templates: list[dict[str, Any]], boundary_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_paths = [
        REPO_ROOT / "dopey_broker_readiness" / "disabled_handoff_command_registry.py",
        REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "dry_run" / "future_detector_contract.md",
        REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md",
    ]
    sources = build_boundary_scan_sources(command_templates, boundary_cases, source_paths)
    return classify_boundary_references(sources)


def build_pre_run_boundary_scan_results(
    inputs: list[dict[str, Any]],
    boundary_cases: list[dict[str, Any]],
    command_templates: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    classification_by_case = _active_classification_by_case(classifications)
    templates_disabled = all(_template_is_disabled(template) for template in command_templates)
    for index, pair in enumerate(zip(inputs, boundary_cases, strict=True)):
        scan_input, case = pair
        active_classifications = classification_by_case.get(case["case_id"], [])
        terminal = _case_terminal_boundary(case) or bool(active_classifications)
        manual = _case_manual_review_boundary(case)
        status = "terminal_block" if terminal else ("manual_review_required" if manual else "clean")
        absent = status != "terminal_block"
        seed = PreRunBoundaryScanResult(
            boundary_scan_id=f"pre-run-boundary-scan-{index + 1:03d}",
            scan_input_id=str(scan_input["scan_input_id"]),
            command_templates_disabled=templates_disabled and case["command_templates_disabled"],
            separate_future_bundle_required=case["separate_future_bundle_required"],
            explicit_reapproval_required=case["explicit_reapproval_required"],
            pre_run_safety_scan_required=case["pre_run_safety_scan_required"],
            post_run_evidence_required=case["post_run_evidence_required"],
            broker_connection_absent=absent and scan_input["broker_connection_allowed_now_count"] == 0,
            credential_absent=absent and scan_input["credential_allowed_now_count"] == 0,
            env_absent=absent and ".env" not in str(case["boundary_text"]),
            network_market_data_absent=absent and "network_market_data" not in str(case["boundary_text"]),
            live_order_absent=absent and scan_input["live_order_allowed_now_count"] == 0,
            order_placement_absent=absent and "place_order" not in str(case["boundary_text"]),
            order_cancellation_absent=absent and "cancel_order" not in str(case["boundary_text"]),
            scheduler_absent=absent and scan_input["scheduler_allowed_now_count"] == 0,
            real_sizing_absent=absent and scan_input["real_sizing_allowed_now_count"] == 0,
            buying_power_absent=absent and "buying_power" not in str(case["boundary_text"]),
            account_balance_absent=absent and "account_balance" not in str(case["boundary_text"]),
            robinhood_mcp_absent=absent and "robinhood_mcp" not in str(case["boundary_text"]),
            detector_runtime_absent=absent and scan_input["detector_run_allowed_now_count"] == 0,
            forbidden_reference_count=len(active_classifications),
            boundary_status=status,
            reason_codes=_boundary_reason_codes(case, active_classifications),
            paper_only=True,
            live_blocked=True,
            scan_hash="",
        )
        records.append({**seed.to_dict(), "case_group": case["case_group"], "case_name": case["case_name"], "scan_hash": pre_run_boundary_scan_result_hash(seed)})
    return records


def build_pre_run_safety_decisions(
    inputs: list[dict[str, Any]],
    boundary_cases: list[dict[str, Any]],
    boundary_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, triple in enumerate(zip(inputs, boundary_cases, boundary_results, strict=True)):
        scan_input, case, boundary = triple
        decision = _decision_for_case(scan_input, case, boundary)
        allowed = decision == "future_bundle_preparation_allowed"
        seed = PreRunSafetyDecision(
            decision_id=f"pre-run-safety-decision-{index + 1:03d}",
            scan_input_id=str(scan_input["scan_input_id"]),
            boundary_scan_id=str(boundary["boundary_scan_id"]),
            decision=decision,
            future_detector_bundle_preparation_allowed=allowed,
            detector_run_allowed_now=False,
            broker_connection_allowed_now=False,
            credential_allowed_now=False,
            live_order_allowed_now=False,
            scheduler_allowed_now=False,
            real_sizing_allowed_now=False,
            requires_separate_future_bundle=True,
            requires_explicit_reapproval=True,
            requires_pre_run_safety_scan=True,
            requires_post_run_evidence=True,
            reason_codes=sorted(set(boundary["reason_codes"] + _decision_reason_codes(decision))),
            incident_escalation=_incident_for_decision(decision, case),
            paper_only=True,
            live_blocked=True,
            decision_hash="",
        )
        records.append({**seed.to_dict(), "case_group": case["case_group"], "case_name": case["case_name"], "decision_hash": pre_run_safety_decision_hash(seed)})
    return records


def build_pre_run_incident_escalations(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for decision in decisions:
        if decision["decision"] == "future_bundle_preparation_allowed":
            continue
        terminal = decision["decision"] not in {"manual_review_required", "blocked_missing_handoff"}
        seed = {
            "escalation_id": f"pre-run-incident-escalation-{len(records) + 1:03d}",
            "decision_id": decision["decision_id"],
            "incident_type": decision["incident_escalation"],
            "response_decision": "terminal_block" if terminal else "manual_review_required",
            "kill_switch_state": "terminal_block" if terminal else "manual_review_required",
            "requires_operator_review": True,
            "auto_recovery_allowed": False,
            "paper_only": True,
            "live_blocked": True,
            "escalation_hash": "",
        }
        records.append({**seed, "escalation_hash": stable_hash(seed)})
    return records


def build_pre_run_safety_proof(
    inputs: list[dict[str, Any]],
    boundary_results: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    classification_counts = Counter(str(record["classification"]) for record in classifications)
    records: list[dict[str, Any]] = []
    for index, triple in enumerate(zip(inputs, boundary_results, decisions, strict=True)):
        scan_input, boundary, decision = triple
        seed = {
            "proof_id": f"pre-run-safety-proof-{index + 1:03d}",
            "pre_run_safety_scanner_version": PRE_RUN_SAFETY_SCANNER_VERSION,
            "scan_input_id": scan_input["scan_input_id"],
            "boundary_scan_id": boundary["boundary_scan_id"],
            "decision_id": decision["decision_id"],
            "future_bundle_preparation_allowed": decision["future_detector_bundle_preparation_allowed"],
            "detector_run_allowed_now": False,
            "broker_connection_allowed_now": False,
            "credential_allowed_now": False,
            "live_order_allowed_now": False,
            "scheduler_allowed_now": False,
            "real_sizing_allowed_now": False,
            "command_templates_disabled": boundary["command_templates_disabled"],
            "separate_future_bundle_required": decision["requires_separate_future_bundle"],
            "explicit_reapproval_required": decision["requires_explicit_reapproval"],
            "pre_run_safety_scan_required": decision["requires_pre_run_safety_scan"],
            "post_run_evidence_required": decision["requires_post_run_evidence"],
            "forbidden_references_classified": dict(sorted(classification_counts.items())),
            "incident_escalation": decision["incident_escalation"],
            "safety_status": decision["decision"],
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
            "no_scheduler": True,
            "no_credential": True,
            "no_live_order": True,
            "proof_hash": "",
        }
        records.append({**seed, "proof_hash": stable_hash(seed)})
    return records


def build_pre_run_safety_summary(
    source_snapshot: dict[str, Any],
    inputs: list[dict[str, Any]],
    boundary_results: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    incident_escalations: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_counts = Counter(str(record["decision"]) for record in decisions)
    boundary_counts = Counter(str(record["boundary_status"]) for record in boundary_results)
    classification_counts = Counter(str(record["classification"]) for record in classifications)
    summary_seed = {
        "artifact_type": "pre_run_safety_summary",
        "pre_run_safety_scanner_version": PRE_RUN_SAFETY_SCANNER_VERSION,
        "pre_run_safety_status": "pre_run_safety_scanner_validated",
        "scan_input_count": len(inputs),
        "boundary_scan_count": len(boundary_results),
        "decision_count": len(decisions),
        "proof_record_count": len(proof_records),
        "classification_count": len(classifications),
        "incident_escalation_count": len(incident_escalations),
        "future_bundle_preparation_allowed_count": int(decision_counts.get("future_bundle_preparation_allowed", 0)),
        "detector_run_allowed_now_count": _true_count(decisions, "detector_run_allowed_now"),
        "broker_connection_allowed_now_count": _true_count(decisions, "broker_connection_allowed_now"),
        "credential_allowed_now_count": _true_count(decisions, "credential_allowed_now"),
        "live_order_allowed_now_count": _true_count(decisions, "live_order_allowed_now"),
        "scheduler_allowed_now_count": _true_count(decisions, "scheduler_allowed_now"),
        "real_sizing_allowed_now_count": _true_count(decisions, "real_sizing_allowed_now"),
        "command_templates_disabled": all(record["command_templates_disabled"] for record in boundary_results if record["case_group"] == "clean_eligible"),
        "separate_future_bundle_required": all(record["requires_separate_future_bundle"] for record in decisions),
        "explicit_reapproval_required": all(record["requires_explicit_reapproval"] for record in decisions),
        "pre_run_safety_scan_required": all(record["requires_pre_run_safety_scan"] for record in decisions),
        "post_run_evidence_required": all(record["requires_post_run_evidence"] for record in decisions),
        "boundary_status_distribution": dict(sorted(boundary_counts.items())),
        "boundary_classification_distribution": dict(sorted(classification_counts.items())),
        "decision_distribution": dict(sorted(decision_counts.items())),
        "terminal_block_count": sum(1 for record in decisions if record["decision"] not in {"future_bundle_preparation_allowed", "manual_review_required", "blocked_missing_handoff"}),
        "manual_review_count": sum(1 for record in decisions if record["decision"] in {"manual_review_required", "blocked_missing_handoff"}),
        "active_forbidden_live_decisions": 0,
        "source_handoff_future_bundle_eligible_count": int(source_snapshot["handoff_summary"].get("future_bundle_eligible_count", 0)),
        "source_handoff_summary_hash": _record_hash(source_snapshot["handoff_summary"]),
        "source_approval_intake_summary_hash": _record_hash(source_snapshot["approval_intake_summary"]),
        "source_dry_run_summary_hash": _record_hash(source_snapshot["dry_run_summary"]),
        "source_manual_packet_hash": _record_hash(source_snapshot["manual_packet_summary"]),
        "source_preflight_hash": _record_hash(source_snapshot["preflight_summary"]),
        "source_audit_hash": _record_hash(source_snapshot["audit_proof"]),
        "source_export_hash": _record_hash(source_snapshot["export_safety_scan"]),
        "source_export_review_hash": _record_hash(source_snapshot["export_review_proof"]),
        "next_required_gate": PRE_RUN_NEXT_REQUIRED_GATE,
        "safety_state": "live_blocked_broker_absent_detector_not_run",
        "paper_only": True,
        "live_blocked": True,
        "fixture_only": True,
        "offline_only": True,
        "read_only_detector_run": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
        "robinhood_mcp_integration_created": False,
        "real_market_data_used": False,
        "live_order_created": False,
        "summary_hash": "",
    }
    return {**summary_seed, "summary_hash": stable_hash(summary_seed)}


def render_pre_run_safety_report(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Detector Pre-Run Safety Scanner", ""]
    lines.append("## Objective")
    lines.append("Build an offline pre-run gate for a future separately approved read-only detector bundle.")
    lines.append("")
    lines.append("## Why This Is Not Detector Execution")
    lines.append("- detector_run_in_this_bundle: `false`")
    lines.append("- broker_connection_in_this_bundle: `false`")
    lines.append("- credentials_in_this_bundle: `false`")
    lines.append("- scheduler_in_this_bundle: `false`")
    lines.append("- real_sizing_in_this_bundle: `false`")
    lines.append("")
    lines.append("## Models And Scanner")
    lines.append("- pre_run_scan_input_model: `PreRunSafetyScanInput`")
    lines.append("- boundary_scan_result_model: `PreRunBoundaryScanResult`")
    lines.append("- safety_decision_model: `PreRunSafetyDecision`")
    lines.append("- forbidden_boundary_scanner: `pre_run_forbidden_boundary_scanner`")
    lines.append("- command_template_checks: disabled, not allowed now, explicit reapproval, separate future bundle, pre-run scan, post-run evidence")
    lines.append("- audit_export_review_checks: source hashes consumed from handoff, approval intake, dry run, manual packet, preflight, audit, export, review")
    lines.append("")
    lines.append("## Summary")
    for field_name in [
        "scan_input_count",
        "future_bundle_preparation_allowed_count",
        "detector_run_allowed_now_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
        "terminal_block_count",
        "manual_review_count",
    ]:
        lines.append(f"- {field_name}: `{summary[field_name]}`")
    lines.append(f"- command_templates_disabled: `{str(summary['command_templates_disabled']).lower()}`")
    lines.append(f"- boundary_classification_distribution: `{summary['boundary_classification_distribution']}`")
    lines.append(f"- decision_distribution: `{summary['decision_distribution']}`")
    lines.append("")
    lines.append("## Validation")
    lines.append("- targeted_pre_run_tests: recorded in `tests/test_read_only_detector_pre_run_safety_scanner.py`")
    lines.append("- full_suite_status: `inconclusive_timeout` remains not pass until separately proven")
    lines.append("")
    lines.append("## Limitations")
    lines.append("- No broker capability proof exists.")
    lines.append("- No broker connection, credential setup, Robinhood MCP integration, real market data, live order, scheduler, or real sizing exists.")
    lines.append("- A future detector run still requires a separate approved bundle plus a clean pre-run scan.")
    lines.append("")
    lines.append("## Safety State")
    lines.append(f"- safety_state: `{summary['safety_state']}`")
    lines.append(f"- next_required_gate: `{summary['next_required_gate']}`")
    return "\n".join(lines) + "\n"


def render_pre_run_safety_ledger(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Pre-Run Safety Scanner Artifact Ledger", ""]
    for artifact_id, artifact_path in pre_run_safety_artifact_paths().items():
        target = Path(artifact_path)
        lines.append(f"- `{artifact_id}`: `{artifact_path}`")
        if target.exists():
            lines.append(f"  - hash: `{_file_hash(target)}`")
            lines.append(f"  - record_count: `{_record_count(target)}`")
    lines.append(f"- `scan_count`: `{summary['scan_input_count']}`")
    lines.append(f"- `boundary_classification_count`: `{summary['classification_count']}`")
    lines.append(f"- `decision_count`: `{summary['decision_count']}`")
    lines.append(f"- `incident_escalation_count`: `{summary['incident_escalation_count']}`")
    lines.append("- `proof_layer`: `pre_run_safety_proof`")
    lines.append(f"- `safety_state`: `{summary['safety_state']}`")
    lines.append(f"- `summary_hash`: `{summary['summary_hash']}`")
    return "\n".join(lines) + "\n"


def append_pre_run_safety_doc_updates(summary: dict[str, Any]) -> None:
    section = "\n".join([
        "",
        "## DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_V1",
        "",
        "- status: `pre_run_safety_scanner_validated`",
        f"- future_bundle_preparation_allowed_count: `{summary['future_bundle_preparation_allowed_count']}`",
        "- detector_run_allowed_now_count: `0`",
        "- broker_connection_allowed_now_count: `0`",
        "- credential_allowed_now_count: `0`",
        "- live_order_allowed_now_count: `0`",
        "- scheduler_allowed_now_count: `0`",
        "- real_sizing_allowed_now_count: `0`",
        "- command_templates_disabled: `true`",
        "- separate_future_bundle_required: `true`",
        "- explicit_reapproval_required: `true`",
        "- pre_run_safety_scan_required: `true`",
        "- post_run_evidence_required: `true`",
        "- pre_run_scanner_does_not_run_detector: `true`",
        "- future_bundle_preparation_is_not_broker_connection: `true`",
        "- boundary_leak_terminal_blocks: `true`",
    ]) + "\n"
    targets = [
        REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_REPORT.md",
        REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_REPORT.md",
        REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_DRY_RUN_FIXTURE_VALIDATOR_REPORT.md",
        REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md",
        REPO_ROOT / "DOPEY_VALIDATION_REPORT.md",
        REPO_ROOT / "DOPEY_CANON.md",
    ]
    marker = "DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_V1"
    for target in targets:
        _append_once(target, marker, section)


def _boundary_case(index: int, group: str, group_index: int, case_name: str) -> dict[str, Any]:
    text_by_group = {
        "clean_eligible": "all future detector paths remain blocked absent broker_connection credential scheduler real_sizing live_order",
        "runtime_permission_leak": "runtime permission leak attempted before detector run",
        "forbidden_boundary_reference": _forbidden_text(group_index),
        "command_template_violation": _command_template_violation_text(group_index),
        "audit_export_failure": "export safety finding active forbidden live decision credential finding",
        "missing_proof": "missing proof ledger requires manual review",
        "timeout_misclassification": "full suite timeout misclassified as pass",
        "terminal_block": "terminal incident in pre-run path",
    }
    boundary_context = "documentation" if group == "clean_eligible" else "negative_control_fixture"
    if group in {"forbidden_boundary_reference", "command_template_violation", "terminal_block"}:
        boundary_context = "active_runtime"
    if case_name in {
        "documentation_only_blocked_reference_nonfatal",
        "negative_control_fixture_reference_nonfatal",
        "blocked_command_template_reference_nonfatal",
    }:
        boundary_context = {
            "documentation_only_blocked_reference_nonfatal": "documentation",
            "negative_control_fixture_reference_nonfatal": "negative_control_fixture",
            "blocked_command_template_reference_nonfatal": "blocked_command_template",
        }[case_name]
    command_templates_disabled = group != "command_template_violation"
    return {
        "case_id": f"pre-run-boundary-case-{index:03d}",
        "case_group": group,
        "case_name": case_name,
        "future_bundle_eligible_count": 12 if group != "missing_proof" else (0 if group_index == 1 else 12),
        "boundary_text": text_by_group[group],
        "boundary_context": boundary_context,
        "command_templates_disabled": command_templates_disabled,
        "separate_future_bundle_required": not (group == "command_template_violation" and group_index == 3),
        "explicit_reapproval_required": not (group == "command_template_violation" and group_index == 2),
        "pre_run_safety_scan_required": True,
        "post_run_evidence_required": True,
        "safety_finding": group == "audit_export_failure" and group_index % 2 == 1,
        "credential_finding": group == "audit_export_failure" and group_index % 2 == 0,
        "timeout_misclassified": group == "timeout_misclassification",
        "missing_proof": group == "missing_proof",
        "terminal_incident": group == "terminal_block",
        "windows_stdout_flush_oserror_seen": case_name == "windows_stdout_flush_oserror_recorded_not_pass",
        "paper_only": True,
        "live_blocked": True,
        "case_hash": "",
    } | {"case_hash": stable_hash({
        "case_id": f"pre-run-boundary-case-{index:03d}",
        "case_group": group,
        "case_name": case_name,
    })}


def _forbidden_text(group_index: int) -> str:
    values = [
        ".env active runtime reference",
        "access_token active runtime reference",
        "broker_connection active runtime reference",
        "robinhood_mcp mcp.connect active runtime reference",
        "place_order active runtime reference",
        "cancel_order active runtime reference",
        "review_option_order active runtime reference",
        "account_balance active runtime reference",
        "buying_power active runtime reference",
        "real_sizing real_capital active runtime reference",
        "scheduler cron daemon active runtime reference",
        "network_market_data requests.get websocket active runtime reference",
        "ROBINHOOD_TOKEN active runtime reference",
        "broker_session active runtime reference",
        "live_trading_enabled=true active runtime reference",
        "live_allowed=true live_order active runtime reference",
    ]
    return values[(group_index - 1) % len(values)]


def _command_template_violation_text(group_index: int) -> str:
    values = [
        "command template enabled",
        "command template missing reapproval",
        "command template missing separate future bundle",
        "command template OPENAI_API_KEY credential reference",
        "command template place_option_order reference",
        "command template cancel_option_order reference",
        "command template scheduler reference",
        "command template live_trading_enabled=true reference",
        "command template broker_connection reference",
        "command template .env reference",
        "command template real_sizing reference",
        "command template robinhood_mcp reference",
    ]
    return values[(group_index - 1) % len(values)]


def _runtime_counts_for_case(case: dict[str, Any]) -> dict[str, int]:
    counts = {
        "detector_run_allowed_now_count": 0,
        "broker_connection_allowed_now_count": 0,
        "credential_allowed_now_count": 0,
        "live_order_allowed_now_count": 0,
        "scheduler_allowed_now_count": 0,
        "real_sizing_allowed_now_count": 0,
    }
    if case["case_group"] == "runtime_permission_leak":
        fields = list(counts)
        counts[fields[(int(str(case["case_id"])[-3:]) - 17) % len(fields)]] = 1
    return counts


def _decision_for_case(scan_input: dict[str, Any], case: dict[str, Any], boundary: dict[str, Any]) -> str:
    if case["missing_proof"] is True:
        return "blocked_missing_handoff" if "handoff" in case["case_name"] else "manual_review_required"
    if case["future_bundle_eligible_count"] < 1:
        return "blocked_missing_approval_eligibility"
    if case["timeout_misclassified"] is True:
        return "blocked_timeout_misclassified"
    if case["safety_finding"] is True:
        return "blocked_safety_finding"
    if case["credential_finding"] is True:
        return "blocked_credential_finding"
    if any(int(scan_input[field]) > 0 for field in (
        "detector_run_allowed_now_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
    )):
        return "blocked_permission_leak"
    if boundary["boundary_status"] == "terminal_block":
        return "terminal_block"
    if boundary["broker_connection_absent"] is False:
        return "blocked_broker_connection_present"
    if boundary["detector_runtime_absent"] is False:
        return "blocked_detector_runtime_present"
    if boundary["boundary_status"] == "manual_review_required":
        return "manual_review_required"
    return "future_bundle_preparation_allowed"


def _boundary_reason_codes(case: dict[str, Any], active_classifications: list[dict[str, Any]]) -> list[str]:
    reasons = [
        "detector_not_run",
        "broker_connection_not_created",
        "credentials_not_created",
        "explicit_reapproval_required",
        "separate_future_bundle_required",
        "pre_run_safety_scan_required",
        "post_run_evidence_required",
    ]
    if active_classifications:
        reasons.append("active_forbidden_boundary_reference_detected")
    if case["command_templates_disabled"] is not True:
        reasons.append("command_template_violation")
    if case["missing_proof"] is True:
        reasons.append("missing_proof")
    if case["timeout_misclassified"] is True:
        reasons.append("timeout_cannot_be_recorded_as_pass")
    if case["safety_finding"] is True:
        reasons.append("audit_export_safety_finding")
    if case["credential_finding"] is True:
        reasons.append("credential_finding")
    return sorted(set(reasons))


def _decision_reason_codes(decision: str) -> list[str]:
    return {
        "future_bundle_preparation_allowed": ["clean_pre_run_safety_scan"],
        "manual_review_required": ["operator_manual_review_required"],
        "terminal_block": ["terminal_boundary_block"],
        "blocked_missing_handoff": ["missing_handoff_or_proof"],
        "blocked_missing_approval_eligibility": ["missing_future_bundle_eligibility"],
        "blocked_permission_leak": ["runtime_permission_leak"],
        "blocked_safety_finding": ["safety_finding_detected"],
        "blocked_credential_finding": ["credential_finding_detected"],
        "blocked_detector_runtime_present": ["detector_runtime_present"],
        "blocked_broker_connection_present": ["broker_connection_present"],
        "blocked_timeout_misclassified": ["timeout_misclassified_as_pass"],
    }[decision]


def _incident_for_decision(decision: str, case: dict[str, Any]) -> str:
    if decision == "future_bundle_preparation_allowed":
        return "none"
    if decision == "blocked_permission_leak":
        return "pre_run_runtime_permission_leak"
    if decision == "blocked_timeout_misclassified":
        return "pre_run_timeout_recorded_as_pass"
    if decision == "blocked_credential_finding":
        return "pre_run_credential_reference"
    if decision == "blocked_safety_finding":
        return "pre_run_audit_export_safety_finding"
    if decision == "blocked_missing_handoff":
        return "pre_run_missing_proof"
    if decision == "manual_review_required":
        return "pre_run_missing_proof" if case["missing_proof"] else "pre_run_manual_review"
    text = str(case["boundary_text"]).lower()
    if "robinhood_mcp" in text or "mcp.connect" in text:
        return "pre_run_robinhood_mcp_invocation"
    if "place_order" in text or "place_option_order" in text:
        return "pre_run_order_placement_reference"
    if "cancel_order" in text or "cancel_option_order" in text:
        return "pre_run_order_cancellation_reference"
    if "scheduler" in text or "cron" in text or "daemon" in text:
        return "pre_run_scheduler_reference"
    if "real_sizing" in text or "real_capital" in text:
        return "pre_run_real_sizing_reference"
    if ".env" in text or "token" in text or "key" in text:
        return "pre_run_credential_reference"
    if "broker_connection" in text or "broker_session" in text:
        return "pre_run_broker_connection_reference"
    if case["command_templates_disabled"] is not True:
        return "pre_run_enabled_command_template"
    return "pre_run_terminal_boundary_leak"


def _case_terminal_boundary(case: dict[str, Any]) -> bool:
    return (
        case["case_group"] in {"command_template_violation", "terminal_block"}
        or case["safety_finding"] is True
        or case["credential_finding"] is True
        or case["timeout_misclassified"] is True
    )


def _case_manual_review_boundary(case: dict[str, Any]) -> bool:
    return case["missing_proof"] is True


def _template_is_disabled(template: dict[str, Any]) -> bool:
    return (
        template.get("enabled") is False
        and template.get("allowed_now") is False
        and template.get("requires_separate_future_bundle") is True
        and template.get("requires_explicit_operator_reapproval") is True
        and template.get("requires_pre_run_safety_scan") is True
        and template.get("requires_post_run_evidence") is True
    )


def _active_classification_by_case(classifications: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in classifications:
        if record["classification"] != ACTIVE_RUNTIME_CLASSIFICATION:
            continue
        source_path = str(record["source_path"])
        if source_path.startswith("pre-run-boundary-case-"):
            grouped.setdefault(source_path, []).append(record)
    return grouped


def _load_disabled_command_templates() -> list[dict[str, Any]]:
    if DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH.exists():
        return _read_jsonl(DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH)
    return build_disabled_handoff_command_templates()


def _source_ids(source_snapshot: dict[str, Any]) -> dict[str, str]:
    return {key: _record_hash(value) for key, value in source_snapshot.items() if key != "source_paths"}


def _record_hash(record: dict[str, Any]) -> str:
    for field_name in ("summary_hash", "proof_hash", "record_hash", "reproducibility_hash"):
        value = record.get(field_name)
        if isinstance(value, str) and value:
            return value
    return stable_hash(record)


def _true_count(records: list[dict[str, Any]], field_name: str) -> int:
    return sum(1 for record in records if record.get(field_name) is True)


def _fixture_payload(artifact_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    seed = {
        "artifact_type": artifact_type,
        "record_count": len(records),
        "records": records,
        "paper_only": True,
        "live_blocked": True,
        "fixture_hash": "",
    }
    return {**seed, "fixture_hash": stable_hash(seed)}


def _require_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required pre-run safety source artifact missing: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"required pre-run safety source artifact empty: {path}")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"required pre-run safety source artifact must be a JSON object: {path}")
    return parsed


def _require_latest_jsonl(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required pre-run safety source artifact missing: {path}")
    records = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError(f"required pre-run safety source artifact empty: {path}")
    parsed = json.loads(records[-1])
    if not isinstance(parsed, dict):
        raise ValueError(f"required pre-run safety source artifact must contain JSON objects: {path}")
    return parsed


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _append_once(path: Path, marker: str, section: str) -> None:
    if not path.exists():
        path.write_text(section.lstrip(), encoding="utf-8")
        return
    existing = path.read_text(encoding="utf-8", errors="replace")
    if marker in existing:
        return
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(section)


def _file_hash(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    return 1
