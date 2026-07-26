"""Offline approval-intake validator for the future read-only detector."""
from __future__ import annotations

import hashlib
import json
import re
import string
from collections import Counter
from pathlib import Path
from typing import Any

from .approval_forbidden_scope_scanner import (
    forbidden_scope_flags,
    forbidden_scope_term_library,
    scan_forbidden_scope_terms,
)
from .approval_intake_models import (
    APPROVAL_INTAKE_NEXT_GATE,
    APPROVAL_INTAKE_VALIDATOR_VERSION,
    ApprovalIntakeRequest,
    ApprovalIntakeResult,
    ApprovalScopeValidation,
    approval_intake_request_hash,
    approval_intake_result_hash,
    approval_scope_validation_hash,
)
from .broker_readiness_models import stable_hash
from .manual_approval_models import EXPLICIT_MANUAL_APPROVAL_GATE, REQUIRED_OPERATOR_ACKNOWLEDGEMENT
from .manual_approval_packet_builder import (
    MANUAL_APPROVAL_PACKET_SUMMARY_PATH,
    READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH,
)
from .read_only_detector_dry_run_validator import FUTURE_DETECTOR_CONTRACT_PATH


REPO_ROOT = Path(__file__).resolve().parent.parent
from dopey_core.repo_paths import REPORTS_DIR
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "approval_intake"

APPROVAL_INTAKE_REQUESTS_FIXTURE_PATH = FIXTURE_DIR / "approval_intake_requests.json"
APPROVAL_INTAKE_EXPECTED_VALIDATIONS_FIXTURE_PATH = FIXTURE_DIR / "approval_intake_expected_validations.json"
APPROVAL_INTAKE_EXPECTED_RESULTS_FIXTURE_PATH = FIXTURE_DIR / "approval_intake_expected_results.json"
APPROVAL_INTAKE_FORBIDDEN_TERMS_FIXTURE_PATH = FIXTURE_DIR / "approval_intake_forbidden_terms.json"
APPROVAL_INTAKE_SCOPE_CLAIMS_FIXTURE_PATH = FIXTURE_DIR / "approval_intake_scope_claims.json"

APPROVAL_INTAKE_REQUESTS_PATH = ARTIFACT_DIR / "approval_intake_requests.jsonl"
APPROVAL_SCOPE_VALIDATIONS_PATH = ARTIFACT_DIR / "approval_scope_validations.jsonl"
APPROVAL_INTAKE_RESULTS_PATH = ARTIFACT_DIR / "approval_intake_results.jsonl"
APPROVAL_FORBIDDEN_TERMS_PATH = ARTIFACT_DIR / "approval_forbidden_terms.json"
APPROVAL_BOUNDARY_BLOCKS_PATH = ARTIFACT_DIR / "approval_boundary_blocks.jsonl"
APPROVAL_INCIDENT_ESCALATIONS_PATH = ARTIFACT_DIR / "approval_incident_escalations.jsonl"
APPROVAL_INTAKE_SUMMARY_PATH = ARTIFACT_DIR / "approval_intake_summary.json"
APPROVAL_INTAKE_PROOF_PATH = ARTIFACT_DIR / "approval_intake_proof.jsonl"

APPROVAL_INTAKE_REPORT_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_REPORT.md"
APPROVAL_INTAKE_LEDGER_PATH = REPORTS_DIR / "DOPEY_APPROVAL_INTAKE_VALIDATOR_ARTIFACT_LEDGER.md"


def approval_intake_artifact_paths() -> dict[str, str]:
    return {
        "approval_intake_requests": str(APPROVAL_INTAKE_REQUESTS_PATH),
        "approval_scope_validations": str(APPROVAL_SCOPE_VALIDATIONS_PATH),
        "approval_intake_results": str(APPROVAL_INTAKE_RESULTS_PATH),
        "approval_forbidden_terms": str(APPROVAL_FORBIDDEN_TERMS_PATH),
        "approval_boundary_blocks": str(APPROVAL_BOUNDARY_BLOCKS_PATH),
        "approval_incident_escalations": str(APPROVAL_INCIDENT_ESCALATIONS_PATH),
        "approval_intake_summary": str(APPROVAL_INTAKE_SUMMARY_PATH),
        "approval_intake_proof": str(APPROVAL_INTAKE_PROOF_PATH),
    }


def validate_read_only_detector_approval_intake() -> dict[str, Any]:
    manual_summary = _require_json(MANUAL_APPROVAL_PACKET_SUMMARY_PATH)
    approval_packet = _require_json(READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH)
    future_contract = _require_text(FUTURE_DETECTOR_CONTRACT_PATH)
    required_text = str(approval_packet["operator_acknowledgement_text"])
    if required_text != REQUIRED_OPERATOR_ACKNOWLEDGEMENT:
        raise ValueError("approval-intake validator requires the canonical acknowledgement text")
    if manual_summary.get("read_only_detector_run") is not False:
        raise ValueError("approval-intake validator requires detector not run before intake")
    if "detector_run_in_this_bundle: `false`" not in future_contract:
        raise ValueError("future detector contract must state detector_run_in_this_bundle=false")

    acknowledgement_hash = stable_hash({"required_acknowledgement": required_text})
    requests = build_approval_intake_requests(str(approval_packet["packet_id"]), acknowledgement_hash, required_text)
    validations = [validate_approval_intake_request(record, required_text) for record in requests]
    results = build_approval_intake_results(validations)
    forbidden_terms = forbidden_scope_term_library()
    boundary_blocks = build_approval_boundary_blocks(validations)
    incident_escalations = build_approval_incident_escalations(validations)
    proof_records = build_approval_intake_proof_records(requests, validations, results)
    summary = build_approval_intake_summary(requests, validations, results, boundary_blocks, incident_escalations, proof_records)

    _write_json(APPROVAL_INTAKE_REQUESTS_FIXTURE_PATH, _fixture_payload("approval_intake_requests", requests))
    _write_json(APPROVAL_INTAKE_EXPECTED_VALIDATIONS_FIXTURE_PATH, _fixture_payload("approval_intake_expected_validations", validations))
    _write_json(APPROVAL_INTAKE_EXPECTED_RESULTS_FIXTURE_PATH, _fixture_payload("approval_intake_expected_results", results))
    _write_json(APPROVAL_INTAKE_FORBIDDEN_TERMS_FIXTURE_PATH, _fixture_payload("approval_intake_forbidden_terms", forbidden_terms))
    _write_json(APPROVAL_INTAKE_SCOPE_CLAIMS_FIXTURE_PATH, _fixture_payload("approval_intake_scope_claims", build_scope_claim_library()))

    _write_jsonl(APPROVAL_INTAKE_REQUESTS_PATH, [_sanitize_request_for_artifact(record, validation) for record, validation in zip(requests, validations, strict=True)])
    _write_jsonl(APPROVAL_SCOPE_VALIDATIONS_PATH, validations)
    _write_jsonl(APPROVAL_INTAKE_RESULTS_PATH, results)
    _write_json(APPROVAL_FORBIDDEN_TERMS_PATH, {"artifact_type": "approval_forbidden_terms", "term_count": len(forbidden_terms), "records": forbidden_terms, "paper_only": True, "live_blocked": True, "term_library_hash": stable_hash({"records": forbidden_terms})})
    _write_jsonl(APPROVAL_BOUNDARY_BLOCKS_PATH, boundary_blocks)
    _write_jsonl(APPROVAL_INCIDENT_ESCALATIONS_PATH, incident_escalations)
    _write_json(APPROVAL_INTAKE_SUMMARY_PATH, summary)
    _write_jsonl(APPROVAL_INTAKE_PROOF_PATH, proof_records)
    _write_text(APPROVAL_INTAKE_REPORT_PATH, render_approval_intake_report(summary))
    _write_text(APPROVAL_INTAKE_LEDGER_PATH, render_approval_intake_ledger(summary))
    append_approval_intake_doc_updates(summary)

    return {
        "approval_intake_validator_status": "ok",
        "approval_intake_status": summary["approval_intake_status"],
        "request_count": summary["request_count"],
        "validation_count": summary["validation_count"],
        "result_count": summary["result_count"],
        "approval_status_distribution": summary["approval_status_distribution"],
        "exact_valid_fixture_approval_count": summary["exact_valid_fixture_approval_count"],
        "invalid_approval_count": summary["invalid_approval_count"],
        "manual_review_count": summary["manual_review_count"],
        "terminal_block_count": summary["terminal_block_count"],
        "future_detector_eligible_count": summary["future_detector_eligible_count"],
        "detector_run_allowed_now_count": summary["detector_run_allowed_now_count"],
        "broker_connection_allowed_now_count": summary["broker_connection_allowed_now_count"],
        "credential_allowed_now_count": summary["credential_allowed_now_count"],
        "live_order_allowed_now_count": summary["live_order_allowed_now_count"],
        "scheduler_allowed_now_count": summary["scheduler_allowed_now_count"],
        "real_sizing_allowed_now_count": summary["real_sizing_allowed_now_count"],
        "artifact_paths": approval_intake_artifact_paths(),
        "report_paths": {
            "approval_intake_report": str(APPROVAL_INTAKE_REPORT_PATH),
            "approval_intake_ledger": str(APPROVAL_INTAKE_LEDGER_PATH),
        },
        "paper_only": True,
        "live_blocked": True,
        "read_only_detector_run": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "robinhood_mcp_integration_created": False,
    }


def build_approval_intake_requests(source_packet_id: str, acknowledgement_hash: str, required_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    required_specs = _required_case_specs(required_text)
    for spec in required_specs:
        records.append(_request_record(len(records) + 1, source_packet_id, acknowledgement_hash, spec))
    fill_specs = {
        "missing_approval": ("absent", "", "absent", ["approval_missing"]),
        "exact_valid_fixture": ("fixture", required_text, "fresh_fixture", ["read_only_detector_only"]),
        "partial_approval": ("fixture", "I APPROVE DOPEY READ-ONLY BROKER CAPABILITY DETECTOR ONLY. NO LIVE ORDERS.", "fresh_fixture", ["partial_approval"]),
        "extra_scope_approval": ("fixture", f"{required_text} Also produce a broker capability proof in this approval.", "fresh_fixture", ["extra_scope"]),
        "forbidden_term_approval": ("fixture", f"{required_text} Also allow live trading.", "fresh_fixture", ["forbidden_term"]),
        "stale_approval": ("fixture", required_text, "stale_fixture", ["stale_approval"]),
        "terminal_block_escalation": ("fixture", f"{required_text} Then run the detector now.", "fresh_fixture", ["detector_run_attempt_after_valid"]),
        "manual_review": ("fixture", f"{required_text} Only read-only detector, plus unclear operational permission.", "fresh_fixture", ["ambiguous_scope_expansion"]),
    }
    targets = {
        "missing_approval": 12,
        "exact_valid_fixture": 12,
        "partial_approval": 16,
        "extra_scope_approval": 16,
        "forbidden_term_approval": 16,
        "stale_approval": 8,
        "terminal_block_escalation": 8,
        "manual_review": 8,
    }
    for group_name, target in targets.items():
        while sum(1 for record in records if record["case_group"] == group_name) < target:
            channel, text, timestamp, claims = fill_specs[group_name]
            count = sum(1 for record in records if record["case_group"] == group_name) + 1
            spec = {
                "case_name": f"{group_name}_{count:02d}",
                "case_group": group_name,
                "operator_text": text,
                "approval_channel": channel,
                "approval_timestamp_label": timestamp,
                "scope_claims": claims,
            }
            records.append(_request_record(len(records) + 1, source_packet_id, acknowledgement_hash, spec))
    if len(records) != 96:
        raise ValueError(f"approval-intake fixture must contain 96 cases, got {len(records)}")
    return records


def validate_approval_intake_request(request: dict[str, Any], required_text: str) -> dict[str, Any]:
    model = ApprovalIntakeRequest.from_dict({key: value for key, value in request.items() if key not in {"case_name", "case_group", "operator_text_hash"}})
    operator_text = model.operator_text
    stripped = operator_text.strip()
    exact = operator_text == required_text
    missing = model.operator_text_present is not True or stripped == "" or model.approval_channel == "absent"
    partial = _is_partial_approval(operator_text, required_text)
    extra_scope = _has_extra_scope(operator_text, required_text, model.scope_claims)
    forbidden_matches = scan_forbidden_scope_terms(_scope_scan_text(operator_text, required_text))
    flags = forbidden_scope_flags(forbidden_matches)
    stale = _is_stale_or_invalid(model.approval_timestamp_label, model.scope_claims, model.approval_channel)
    manual_review = "ambiguous_scope_expansion" in model.scope_claims
    detector_run_attempt = "detector_run_attempt_after_valid" in model.scope_claims
    reason_codes = _reason_codes(
        missing,
        partial,
        extra_scope,
        forbidden_matches,
        stale,
        manual_review,
        detector_run_attempt,
        model.approval_channel,
        exact,
    )
    status = _validation_status(missing, exact, forbidden_matches, stale, manual_review, detector_run_attempt, model.approval_channel)
    allowed_scope_only = exact and not forbidden_matches and not stale and model.approval_channel in {"fixture", "manual_text_fixture"}
    seed = ApprovalScopeValidation(
        validation_id=f"approval-scope-validation-{model.request_id.removeprefix('approval-intake-request-')}",
        request_id=model.request_id,
        exact_text_match=exact,
        missing_approval=missing,
        partial_approval=partial,
        extra_scope_detected=extra_scope,
        forbidden_terms_detected=[match["term_id"] for match in forbidden_matches],
        allowed_scope_only=allowed_scope_only,
        read_only_detector_only=allowed_scope_only,
        credential_scope_detected=flags["credential_scope_detected"],
        live_trading_scope_detected=flags["live_trading_scope_detected"],
        order_placement_scope_detected=flags["order_placement_scope_detected"],
        order_cancellation_scope_detected=flags["order_cancellation_scope_detected"],
        scheduler_scope_detected=flags["scheduler_scope_detected"],
        autonomous_loop_scope_detected=flags["autonomous_loop_scope_detected"],
        real_sizing_scope_detected=flags["real_sizing_scope_detected"],
        broker_execute_scope_detected=flags["broker_execute_scope_detected"],
        validation_status=status,
        reason_codes=sorted(set(reason_codes)),
        paper_only=True,
        live_blocked=True,
        validation_hash="",
    )
    return {**seed.to_dict(), "case_name": request["case_name"], "case_group": request["case_group"], "validation_hash": approval_scope_validation_hash(seed)}


def build_approval_intake_results(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for validation in validations:
        valid = validation["validation_status"] == "valid_exact_read_only_detector_only_fixture"
        seed = ApprovalIntakeResult(
            result_id=f"approval-intake-result-{len(results) + 1:03d}",
            request_id=validation["request_id"],
            validation_id=validation["validation_id"],
            approval_valid=valid,
            approval_effective_now=False,
            future_detector_eligible_for_next_bundle=valid,
            detector_run_allowed_now=False,
            broker_connection_allowed_now=False,
            credential_allowed_now=False,
            live_order_allowed_now=False,
            scheduler_allowed_now=False,
            real_sizing_allowed_now=False,
            next_required_gate=APPROVAL_INTAKE_NEXT_GATE if valid else EXPLICIT_MANUAL_APPROVAL_GATE,
            incident_escalation=validation["validation_status"] in {"manual_review_required", "terminal_block"},
            paper_only=True,
            live_blocked=True,
            result_hash="",
        )
        results.append({**seed.to_dict(), "case_name": validation["case_name"], "case_group": validation["case_group"], "result_hash": approval_intake_result_hash(seed)})
    return results


def build_approval_boundary_blocks(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for validation in validations:
        status = validation["validation_status"]
        if status not in {"manual_review_required", "terminal_block"}:
            continue
        seed = {
            "block_id": f"approval-boundary-block-{len(records) + 1:03d}",
            "request_id": validation["request_id"],
            "validation_id": validation["validation_id"],
            "case_name": validation["case_name"],
            "incident_type": _primary_incident_type(validation),
            "blocked_operation": "approval_scope_expansion",
            "kill_switch_state": status,
            "response_decision": status,
            "auto_recovery_allowed": False,
            "reason_codes": validation["reason_codes"],
            "paper_only": True,
            "live_blocked": True,
        }
        records.append({**seed, "block_hash": stable_hash({**seed, "block_hash": ""})})
    return records


def build_approval_incident_escalations(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for validation in validations:
        if validation["validation_status"] not in {"manual_review_required", "terminal_block"}:
            continue
        seed = {
            "escalation_id": f"approval-incident-escalation-{len(records) + 1:03d}",
            "request_id": validation["request_id"],
            "validation_id": validation["validation_id"],
            "incident_type": _primary_incident_type(validation),
            "escalation_decision": validation["validation_status"],
            "terminal_block": validation["validation_status"] == "terminal_block",
            "manual_review_required": validation["validation_status"] == "manual_review_required",
            "reason_codes": validation["reason_codes"],
            "paper_only": True,
            "live_blocked": True,
        }
        records.append({**seed, "escalation_hash": stable_hash({**seed, "escalation_hash": ""})})
    return records


def build_approval_intake_proof_records(
    requests: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for request, validation, result in zip(requests, validations, results, strict=True):
        seed = {
            "proof_id": f"approval-intake-proof-{len(records) + 1:03d}",
            "request_id": request["request_id"],
            "validation_id": validation["validation_id"],
            "result_id": result["result_id"],
            "approval_text_hash": request["operator_text_hash"],
            "raw_operator_text_exported": False,
            "exact_text_match": validation["exact_text_match"],
            "forbidden_term_count": len(validation["forbidden_terms_detected"]),
            "scope_expansion_detected": validation["extra_scope_detected"],
            "approval_valid": result["approval_valid"],
            "approval_effective_now": result["approval_effective_now"],
            "future_detector_eligible": result["future_detector_eligible_for_next_bundle"],
            "detector_run_allowed_now": result["detector_run_allowed_now"],
            "broker_connection_allowed_now": result["broker_connection_allowed_now"],
            "credential_allowed_now": result["credential_allowed_now"],
            "live_order_allowed_now": result["live_order_allowed_now"],
            "scheduler_allowed_now": result["scheduler_allowed_now"],
            "real_sizing_allowed_now": result["real_sizing_allowed_now"],
            "reason_codes": validation["reason_codes"],
            "incident_escalation": result["incident_escalation"],
            "safety_status": "paper_only_live_blocked_approval_intake_only_detector_not_run",
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
            "no_scheduler": True,
            "no_credential": True,
            "no_live_order": True,
        }
        records.append({**seed, "proof_hash": stable_hash({**seed, "proof_hash": ""})})
    return records


def build_approval_intake_summary(
    requests: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    results: list[dict[str, Any]],
    boundary_blocks: list[dict[str, Any]],
    incident_escalations: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    status_distribution = dict(sorted(Counter(validation["validation_status"] for validation in validations).items()))
    forbidden_distribution = dict(sorted(Counter(term for validation in validations for term in validation["forbidden_terms_detected"]).items()))
    summary = {
        "artifact_type": "approval_intake_summary",
        "approval_intake_validator_version": APPROVAL_INTAKE_VALIDATOR_VERSION,
        "approval_intake_status": "approval_intake_fixture_validated",
        "request_count": len(requests),
        "validation_count": len(validations),
        "result_count": len(results),
        "boundary_block_count": len(boundary_blocks),
        "incident_escalation_count": len(incident_escalations),
        "proof_record_count": len(proof_records),
        "approval_status_distribution": status_distribution,
        "forbidden_term_distribution": forbidden_distribution,
        "exact_match_validation_count": sum(1 for validation in validations if validation["exact_text_match"]),
        "exact_valid_fixture_approval_count": sum(1 for result in results if result["approval_valid"]),
        "invalid_approval_count": sum(1 for validation in validations if validation["validation_status"] in {"missing", "invalid"}),
        "manual_review_count": status_distribution.get("manual_review_required", 0),
        "terminal_block_count": status_distribution.get("terminal_block", 0),
        "future_detector_eligible_count": sum(1 for result in results if result["future_detector_eligible_for_next_bundle"]),
        "approval_effective_now_count": sum(1 for result in results if result["approval_effective_now"]),
        "detector_run_allowed_now_count": sum(1 for result in results if result["detector_run_allowed_now"]),
        "broker_connection_allowed_now_count": sum(1 for result in results if result["broker_connection_allowed_now"]),
        "credential_allowed_now_count": sum(1 for result in results if result["credential_allowed_now"]),
        "live_order_allowed_now_count": sum(1 for result in results if result["live_order_allowed_now"]),
        "scheduler_allowed_now_count": sum(1 for result in results if result["scheduler_allowed_now"]),
        "real_sizing_allowed_now_count": sum(1 for result in results if result["real_sizing_allowed_now"]),
        "next_required_gate": APPROVAL_INTAKE_NEXT_GATE,
        "approval_effective_now": False,
        "detector_run_allowed_now": False,
        "broker_connection_allowed_now": False,
        "credential_allowed_now": False,
        "live_order_allowed_now": False,
        "scheduler_allowed_now": False,
        "real_sizing_allowed_now": False,
        "operator_text_raw_exported_for_unsafe_approvals": False,
        "live_trading_enabled": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
        "real_buying_power_logic_created": False,
        "real_account_balance_logic_created": False,
        "robinhood_mcp_integration_created": False,
        "read_only_detector_run": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credential": True,
        "no_live_order": True,
        "full_suite_status": "inconclusive_timeout",
        "full_suite_timeout_recorded_as_pass": False,
    }
    return {**summary, "summary_hash": stable_hash({**summary, "summary_hash": ""})}


def render_approval_intake_report(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Detector Approval Intake Validator Report", ""]
    lines.append("This bundle validates fixture approval text only. It is not detector execution, broker integration, Robinhood MCP integration, credential setup, live trading, order review, order placement, order cancellation, scheduling, real sizing, or market-data access.")
    lines.append("")
    lines.append("## Objective")
    lines.append("- Validate whether fixture approval text exactly matches the required read-only detector acknowledgement.")
    lines.append("- Reject missing, partial, stale, malformed, ambiguous, or scope-expanding approvals.")
    lines.append("- Keep any exact valid fixture approval limited to future-detector eligibility for a later explicitly approved bundle.")
    lines.append("")
    lines.append("## Summary")
    for key in [
        "approval_intake_status",
        "request_count",
        "exact_valid_fixture_approval_count",
        "invalid_approval_count",
        "manual_review_count",
        "terminal_block_count",
        "future_detector_eligible_count",
        "detector_run_allowed_now_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
    ]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("## Approval Status Distribution")
    for status, count in summary["approval_status_distribution"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.append("")
    lines.append("## Forbidden Scope Scanner")
    for term, count in summary["forbidden_term_distribution"].items():
        lines.append(f"- `{term}`: `{count}`")
    lines.append("")
    lines.append("## Safety State")
    for key in ["approval_effective_now", "detector_run_allowed_now", "broker_connection_allowed_now", "credential_allowed_now", "live_order_allowed_now", "scheduler_allowed_now", "real_sizing_allowed_now", "read_only_detector_run", "paper_only", "live_blocked"]:
        lines.append(f"- {key}: `{str(summary.get(key)).lower()}`")
    lines.append("")
    lines.append("## Limitations")
    lines.append("- Approval intake can recognize an exact local fixture approval, but it cannot run the detector.")
    lines.append("- Full suite timeout remains `inconclusive_timeout`, not pass.")
    lines.append("- A future detector run still requires a separate explicitly approved bundle.")
    return "\n".join(lines) + "\n"


def render_approval_intake_ledger(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Approval Intake Validator Artifact Ledger", ""]
    lines.append(f"- request_count: `{summary['request_count']}`")
    lines.append(f"- validation_count: `{summary['validation_count']}`")
    lines.append(f"- result_count: `{summary['result_count']}`")
    lines.append(f"- boundary_block_count: `{summary['boundary_block_count']}`")
    lines.append(f"- proof_record_count: `{summary['proof_record_count']}`")
    lines.append("- safety_state: `paper_only_live_blocked_approval_intake_only_detector_not_run`")
    lines.append("")
    for artifact_type, artifact_path in approval_intake_artifact_paths().items():
        path = Path(artifact_path)
        lines.append(f"- artifact_type: `{artifact_type}`")
        lines.append(f"  path: `{path}`")
        lines.append(f"  hash: `{_file_hash(path) if path.exists() else ''}`")
        lines.append(f"  record_count: `{_record_count(path) if path.exists() else 0}`")
        lines.append("  proof_layer: `approval_intake_validator`")
    return "\n".join(lines) + "\n"


def append_approval_intake_doc_updates(summary: dict[str, Any]) -> None:
    marker = "DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_V1"
    updates = {
        REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md": [
            "## DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_V1",
            "- Approval-intake validator exists as an offline fixture-only validator.",
            "- Invalid or scope-expanding approvals terminal-block or require manual review.",
            "- Exact approval can only make a future detector eligible for a later bundle.",
            "- Approval intake does not run the detector, connect to a broker, create credentials, place orders, create a scheduler, or allow real sizing.",
        ],
        REPO_ROOT / "DOPEY_VALIDATION_REPORT.md": [
            "## DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_V1",
            f"- approval_intake_status: `{summary['approval_intake_status']}`",
            f"- targeted approval-intake cases: `{summary['request_count']}`",
            "- audit/report/export/review integration updated for approval-intake artifacts.",
            "- full_suite_status: `inconclusive_timeout` remains not pass until a future full-suite run completes.",
        ],
        REPO_ROOT / "DOPEY_CANON.md": [
            "## DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_V1",
            "- DOPEY validates read-only detector approval text through an offline intake validator.",
            "- Exact approval validation does not run the detector.",
            "- Approval is not effective for broker connection, credentials, live orders, scheduler, real sizing, or live trading in this bundle.",
            "- Invalid or scope-expanding approval terminal-blocks.",
            "- A future detector run still requires a separate explicitly approved bundle.",
        ],
    }
    for path, lines in updates.items():
        _append_once(path, marker, lines)


def build_scope_claim_library() -> list[dict[str, Any]]:
    claims = [
        "approval_missing",
        "read_only_detector_only",
        "partial_approval",
        "extra_scope",
        "forbidden_term",
        "stale_approval",
        "revoked_approval",
        "expired_approval",
        "invalid_channel",
        "ambiguous_scope_expansion",
        "detector_run_attempt_after_valid",
    ]
    records = []
    for claim in claims:
        seed = {"claim": claim, "paper_only": True, "live_blocked": True}
        records.append({**seed, "claim_hash": stable_hash(seed)})
    return records


def _request_record(index: int, source_packet_id: str, acknowledgement_hash: str, spec: dict[str, Any]) -> dict[str, Any]:
    operator_text = str(spec["operator_text"])
    seed = ApprovalIntakeRequest(
        request_id=f"approval-intake-request-{index:03d}",
        source_packet_id=source_packet_id,
        source_required_acknowledgement_hash=acknowledgement_hash,
        operator_text=operator_text,
        operator_text_present=bool(operator_text.strip()),
        approval_channel=str(spec["approval_channel"]),
        approval_timestamp_label=str(spec["approval_timestamp_label"]),
        scope_claims=[str(claim) for claim in spec["scope_claims"]],
        paper_only=True,
        live_blocked=True,
        request_hash="",
    )
    return {
        **seed.to_dict(),
        "case_name": str(spec["case_name"]),
        "case_group": str(spec["case_group"]),
        "operator_text_hash": stable_hash({"operator_text": operator_text}),
        "request_hash": approval_intake_request_hash(seed),
    }


def _required_case_specs(required_text: str) -> list[dict[str, Any]]:
    omit_live_orders = required_text.replace("NO LIVE ORDERS. ", "")
    omit_credentials = required_text.replace("NO CREDENTIAL STORAGE. ", "")
    omit_order_placement = required_text.replace("NO ORDER PLACEMENT. ", "")
    omit_order_cancellation = required_text.replace("NO ORDER CANCELLATION. ", "")
    omit_scheduler = required_text.replace("NO SCHEDULER. ", "")
    return [
        _spec("missing_approval_rejected", "missing_approval", "", "absent", "absent", ["approval_missing"]),
        _spec("empty_approval_rejected", "missing_approval", "", "manual_text_fixture", "fresh_fixture", ["approval_missing"]),
        _spec("whitespace_only_approval_rejected", "missing_approval", "   ", "manual_text_fixture", "fresh_fixture", ["approval_missing"]),
        _spec("exact_required_acknowledgement_fixture_validates", "exact_valid_fixture", required_text, "fixture", "fresh_fixture", ["read_only_detector_only"]),
        _spec("lowercase_difference_rejected", "partial_approval", required_text.lower(), "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("punctuation_difference_rejected", "partial_approval", required_text.replace(".", ""), "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("partial_read_only_approval_rejected", "partial_approval", "I APPROVE DOPEY READ-ONLY BROKER CAPABILITY DETECTOR ONLY.", "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("approval_omitting_no_live_orders_rejected", "partial_approval", omit_live_orders, "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("approval_omitting_no_credential_storage_rejected", "partial_approval", omit_credentials, "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("approval_omitting_no_order_placement_rejected", "partial_approval", omit_order_placement, "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("approval_omitting_no_order_cancellation_rejected", "partial_approval", omit_order_cancellation, "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("approval_omitting_no_scheduler_rejected", "partial_approval", omit_scheduler, "fixture", "fresh_fixture", ["partial_approval"]),
        _spec("approval_adding_place_trades_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve place trades.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_live_trading_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve live trading.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_store_credentials_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve store credentials.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_account_balance_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve use my account balance.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_buying_power_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve buying power.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_real_sizing_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve real sizing.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_cancel_orders_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve cancel orders.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_autonomous_live_trading_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve autonomous live trading.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_robinhood_mcp_execution_terminal_blocked", "terminal_block_escalation", f"{required_text} I also approve Robinhood MCP execution.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_broker_write_access_terminal_blocked", "terminal_block_escalation", f"{required_text} I also approve broker write access.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_scheduler_terminal_blocked", "terminal_block_escalation", f"{required_text} I also approve scheduler.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_adding_network_market_data_terminal_blocked", "forbidden_term_approval", f"{required_text} I also approve network market data.", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("approval_ambiguous_scope_manual_review", "manual_review", f"{required_text} Also read-only detector only with additional operational discretion.", "fixture", "fresh_fixture", ["ambiguous_scope_expansion"]),
        _spec("stale_approval_rejected", "stale_approval", required_text, "fixture", "stale_fixture", ["stale_approval"]),
        _spec("revoked_approval_rejected", "stale_approval", required_text, "fixture", "revoked_fixture", ["revoked_approval"]),
        _spec("expired_approval_rejected", "stale_approval", required_text, "fixture", "expired_fixture", ["expired_approval"]),
        _spec("invalid_channel_rejected", "extra_scope_approval", required_text, "invalid_fixture", "fresh_fixture", ["invalid_channel"]),
        _spec("hidden_newline_command_rejected", "terminal_block_escalation", f"{required_text}\npython -m dopey_execution.run_detector", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("command_injection_like_text_rejected", "terminal_block_escalation", f"{required_text} && powershell run detector", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("path_token_reference_terminal_blocked", "terminal_block_escalation", f"{required_text} use token path C:\\fixture\\token.txt", "fixture", "fresh_fixture", ["forbidden_term"]),
        _spec("valid_fixture_approval_still_does_not_run_detector", "exact_valid_fixture", required_text, "fixture", "fresh_fixture", ["read_only_detector_only"]),
        _spec("valid_fixture_approval_still_does_not_create_broker_connection", "exact_valid_fixture", required_text, "fixture", "fresh_fixture", ["read_only_detector_only"]),
        _spec("valid_fixture_approval_still_does_not_create_credentials", "exact_valid_fixture", required_text, "fixture", "fresh_fixture", ["read_only_detector_only"]),
        _spec("valid_fixture_approval_only_marks_future_detector_eligible", "exact_valid_fixture", required_text, "fixture", "fresh_fixture", ["read_only_detector_only"]),
    ]


def _spec(case_name: str, case_group: str, operator_text: str, approval_channel: str, approval_timestamp_label: str, scope_claims: list[str]) -> dict[str, Any]:
    return {
        "case_name": case_name,
        "case_group": case_group,
        "operator_text": operator_text,
        "approval_channel": approval_channel,
        "approval_timestamp_label": approval_timestamp_label,
        "scope_claims": scope_claims,
    }


def _is_partial_approval(operator_text: str, required_text: str) -> bool:
    if not operator_text.strip():
        return False
    if operator_text == required_text:
        return False
    normalized = _normalize_text(operator_text)
    required = _normalize_text(required_text)
    return normalized in required or required in normalized or "read only" in normalized or "read-only" in operator_text.lower()


def _has_extra_scope(operator_text: str, required_text: str, scope_claims: list[str]) -> bool:
    if "extra_scope" in scope_claims or "ambiguous_scope_expansion" in scope_claims:
        return True
    if operator_text.startswith(required_text) and operator_text != required_text:
        return True
    return False


def _is_stale_or_invalid(timestamp_label: str, scope_claims: list[str], approval_channel: str) -> bool:
    lowered = timestamp_label.lower()
    return approval_channel == "invalid_fixture" or any(token in lowered for token in ["stale", "expired", "revoked"]) or any(claim in {"stale_approval", "expired_approval", "revoked_approval", "invalid_channel"} for claim in scope_claims)


def _validation_status(
    missing: bool,
    exact: bool,
    forbidden_matches: list[dict[str, str]],
    stale: bool,
    manual_review: bool,
    detector_run_attempt: bool,
    approval_channel: str,
) -> str:
    if missing:
        return "missing"
    if detector_run_attempt or forbidden_matches:
        return "terminal_block"
    if manual_review:
        return "manual_review_required"
    if stale:
        return "invalid"
    if exact and approval_channel in {"fixture", "manual_text_fixture"}:
        return "valid_exact_read_only_detector_only_fixture"
    return "invalid"


def _reason_codes(
    missing: bool,
    partial: bool,
    extra_scope: bool,
    forbidden_matches: list[dict[str, str]],
    stale: bool,
    manual_review: bool,
    detector_run_attempt: bool,
    approval_channel: str,
    exact: bool,
) -> list[str]:
    reasons: list[str] = []
    if missing:
        reasons.append("approval_missing")
    if partial:
        reasons.append("approval_text_does_not_exactly_match_required_acknowledgement")
    if extra_scope:
        reasons.append("approval_scope_expansion_detected")
    if stale:
        reasons.append("approval_stale_expired_revoked_or_invalid_channel")
    if approval_channel == "invalid_fixture":
        reasons.append("approval_from_invalid_channel")
    if manual_review:
        reasons.append("ambiguous_read_only_scope_expansion_manual_review")
    if detector_run_attempt:
        reasons.append("valid_fixture_approval_followed_by_detector_run_attempt")
    if exact and not reasons:
        reasons.extend(["exact_acknowledgement_fixture_valid", "future_bundle_still_required"])
    reasons.extend(match["reason_code"] for match in forbidden_matches)
    return reasons or ["approval_invalid"]


def _primary_incident_type(validation: dict[str, Any]) -> str:
    reason_codes = set(validation["reason_codes"])
    if "valid_fixture_approval_followed_by_detector_run_attempt" in reason_codes:
        return "approval_intake_valid_fixture_followed_by_detector_run_attempt"
    if any("command_injection" in reason for reason in reason_codes) or "approval_contains_hidden_newline_command" in reason_codes:
        return "approval_intake_command_injection_like_approval"
    if "approval_mentions_path_token_reference" in reason_codes:
        return "approval_intake_token_path_reference"
    if validation["live_trading_scope_detected"]:
        return "approval_intake_invalid_live_scope"
    if validation["credential_scope_detected"]:
        return "approval_intake_invalid_credential_scope"
    if validation["order_placement_scope_detected"]:
        return "approval_intake_invalid_order_placement_scope"
    if validation["order_cancellation_scope_detected"]:
        return "approval_intake_invalid_cancellation_scope"
    if validation["scheduler_scope_detected"]:
        return "approval_intake_invalid_scheduler_scope"
    if validation["real_sizing_scope_detected"]:
        return "approval_intake_invalid_real_sizing_scope"
    if validation["broker_execute_scope_detected"]:
        return "approval_intake_invalid_broker_path_scope"
    if validation["validation_status"] == "manual_review_required":
        return "approval_intake_ambiguous_scope_manual_review"
    return "approval_intake_scope_expansion_terminal_block"


def _sanitize_request_for_artifact(request: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    output = dict(request)
    unsafe = validation["validation_status"] in {"manual_review_required", "terminal_block"} or bool(validation["forbidden_terms_detected"])
    output["operator_text"] = "[redacted_unsafe_fixture_text_hash_only]" if unsafe else request["operator_text"]
    output["raw_operator_text_exported"] = not unsafe
    output["unsafe_operator_text_redacted"] = unsafe
    output["request_hash"] = request["request_hash"]
    return output


def _normalize_text(value: str) -> str:
    table = str.maketrans("", "", string.punctuation)
    return " ".join(value.lower().translate(table).split())


def _scope_scan_text(operator_text: str, required_text: str) -> str:
    if operator_text.startswith(required_text):
        return operator_text[len(required_text):]
    denied_phrases = [
        "NO CREDENTIAL STORAGE",
        "NO LIVE ORDERS",
        "NO ORDER PLACEMENT",
        "NO ORDER CANCELLATION",
        "NO SCHEDULER",
        "NO AUTONOMOUS LIVE TRADING",
        "NO REAL SIZING",
    ]
    output = operator_text
    for phrase in denied_phrases:
        output = re.sub(re.escape(phrase), "", output, flags=re.IGNORECASE)
    return output


def _fixture_payload(artifact_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"artifact_type": artifact_type, "case_count": len(records), "records": records, "paper_only": True, "live_blocked": True}
    return {**payload, "fixture_hash": stable_hash(payload)}


def _require_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required approval-intake source artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"required approval-intake source artifact missing: {path}")
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _append_once(path: Path, marker: str, lines: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if marker in text:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n" + "\n".join(lines) + "\n")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    return 1
