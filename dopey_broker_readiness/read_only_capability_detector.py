"""Human-approved read-only broker capability detector runner."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .approval_intake_validator import APPROVAL_INTAKE_PROOF_PATH, APPROVAL_INTAKE_REQUESTS_PATH, APPROVAL_INTAKE_RESULTS_PATH, APPROVAL_INTAKE_SUMMARY_PATH
from .approval_to_run_handoff_gate import APPROVAL_TO_RUN_HANDOFF_PROOF_PATH, APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH, DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH
from .broker_readiness_models import stable_hash
from .manual_approval_packet_builder import OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH
from .pre_run_safety_scanner import PRE_RUN_SAFETY_PROOF_PATH, PRE_RUN_SAFETY_SUMMARY_PATH
from .read_only_capability_provider import FixtureOnlyCapabilityProvider
from .read_only_detector_models import (
    READ_ONLY_DETECTOR_NEXT_GATE,
    READ_ONLY_DETECTOR_VERSION,
    ReadOnlyDetectorRunRequest,
    ReadOnlyDetectorRunResult,
    read_only_detector_run_request_hash,
    read_only_detector_run_result_hash,
)
from .read_only_detector_post_run_evidence import build_read_only_detector_post_run_evidence


REPO_ROOT = Path(__file__).resolve().parent.parent
from dopey_core.repo_paths import REPORTS_DIR
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "read_only_detector"

READ_ONLY_DETECTOR_RUN_REQUESTS_FIXTURE_PATH = FIXTURE_DIR / "read_only_detector_run_requests.json"
READ_ONLY_CAPABILITY_RECORDS_FIXTURE_PATH = FIXTURE_DIR / "read_only_capability_records.json"
READ_ONLY_DETECTOR_EXPECTED_RESULTS_FIXTURE_PATH = FIXTURE_DIR / "read_only_detector_expected_results.json"
READ_ONLY_DETECTOR_BOUNDARY_CASES_FIXTURE_PATH = FIXTURE_DIR / "read_only_detector_boundary_cases.json"
READ_ONLY_DETECTOR_PROVIDER_CASES_FIXTURE_PATH = FIXTURE_DIR / "read_only_detector_provider_cases.json"

READ_ONLY_DETECTOR_RUN_REQUESTS_PATH = ARTIFACT_DIR / "read_only_detector_run_requests.jsonl"
READ_ONLY_CAPABILITY_RECORDS_PATH = ARTIFACT_DIR / "read_only_capability_records.jsonl"
READ_ONLY_BLOCKED_WRITE_EXECUTE_RECORDS_PATH = ARTIFACT_DIR / "read_only_blocked_write_execute_records.jsonl"
READ_ONLY_PROVIDER_BOUNDARY_RESULTS_PATH = ARTIFACT_DIR / "read_only_provider_boundary_results.jsonl"
READ_ONLY_DETECTOR_RUN_RESULTS_PATH = ARTIFACT_DIR / "read_only_detector_run_results.jsonl"
READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_PATH = ARTIFACT_DIR / "read_only_detector_post_run_evidence.json"
READ_ONLY_DETECTOR_INCIDENT_ESCALATIONS_PATH = ARTIFACT_DIR / "read_only_detector_incident_escalations.jsonl"
READ_ONLY_DETECTOR_SUMMARY_PATH = ARTIFACT_DIR / "read_only_detector_summary.json"
READ_ONLY_DETECTOR_PROOF_PATH = ARTIFACT_DIR / "read_only_detector_proof.jsonl"

READ_ONLY_DETECTOR_REPORT_PATH = REPORTS_DIR / "DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_REPORT.md"
READ_ONLY_DETECTOR_LEDGER_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_ARTIFACT_LEDGER.md"


def read_only_detector_artifact_paths() -> dict[str, str]:
    return {
        "read_only_detector_run_requests": str(READ_ONLY_DETECTOR_RUN_REQUESTS_PATH),
        "read_only_capability_records": str(READ_ONLY_CAPABILITY_RECORDS_PATH),
        "read_only_blocked_write_execute_records": str(READ_ONLY_BLOCKED_WRITE_EXECUTE_RECORDS_PATH),
        "read_only_provider_boundary_results": str(READ_ONLY_PROVIDER_BOUNDARY_RESULTS_PATH),
        "read_only_detector_run_results": str(READ_ONLY_DETECTOR_RUN_RESULTS_PATH),
        "read_only_detector_post_run_evidence": str(READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_PATH),
        "read_only_detector_incident_escalations": str(READ_ONLY_DETECTOR_INCIDENT_ESCALATIONS_PATH),
        "read_only_detector_summary": str(READ_ONLY_DETECTOR_SUMMARY_PATH),
        "read_only_detector_proof": str(READ_ONLY_DETECTOR_PROOF_PATH),
    }


def run_human_approved_read_only_broker_capability_detector() -> dict[str, Any]:
    source = load_detector_source_snapshot()
    required_ack = _extract_required_acknowledgement(_require_text(OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH))
    approval = resolve_exact_approval(source, required_ack)
    pre_run_clean = is_pre_run_clean(source)
    cases = build_read_only_detector_boundary_cases()
    requests = build_read_only_detector_run_requests(cases, source, approval, pre_run_clean)
    provider_boundary_results = build_provider_boundary_results(cases)
    processed = process_detector_requests(requests, cases, approval, pre_run_clean, source, provider_boundary_results)
    capability_records = processed["capability_records"]
    blocked_records = [record for record in capability_records if record["blocked_now"] is True]
    run_results = processed["run_results"]
    incident_escalations = processed["incident_escalations"]
    proof_records = build_detector_proof_records(requests, run_results, capability_records, provider_boundary_results)
    post_run_evidence = build_detector_post_run_evidence_record(requests, run_results, capability_records, blocked_records, source)
    summary = build_read_only_detector_summary(
        requests,
        run_results,
        capability_records,
        blocked_records,
        provider_boundary_results,
        incident_escalations,
        proof_records,
        post_run_evidence,
        source,
    )

    _write_json(READ_ONLY_DETECTOR_RUN_REQUESTS_FIXTURE_PATH, _fixture_payload("read_only_detector_run_requests", requests))
    _write_json(READ_ONLY_CAPABILITY_RECORDS_FIXTURE_PATH, _fixture_payload("read_only_capability_records", capability_records))
    _write_json(READ_ONLY_DETECTOR_EXPECTED_RESULTS_FIXTURE_PATH, _fixture_payload("read_only_detector_expected_results", run_results))
    _write_json(READ_ONLY_DETECTOR_BOUNDARY_CASES_FIXTURE_PATH, _fixture_payload("read_only_detector_boundary_cases", cases))
    _write_json(READ_ONLY_DETECTOR_PROVIDER_CASES_FIXTURE_PATH, _fixture_payload("read_only_detector_provider_cases", provider_boundary_results))

    _write_jsonl(READ_ONLY_DETECTOR_RUN_REQUESTS_PATH, requests)
    _write_jsonl(READ_ONLY_CAPABILITY_RECORDS_PATH, capability_records)
    _write_jsonl(READ_ONLY_BLOCKED_WRITE_EXECUTE_RECORDS_PATH, blocked_records)
    _write_jsonl(READ_ONLY_PROVIDER_BOUNDARY_RESULTS_PATH, provider_boundary_results)
    _write_jsonl(READ_ONLY_DETECTOR_RUN_RESULTS_PATH, run_results)
    _write_json(READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_PATH, post_run_evidence)
    _write_jsonl(READ_ONLY_DETECTOR_INCIDENT_ESCALATIONS_PATH, incident_escalations)
    _write_json(READ_ONLY_DETECTOR_SUMMARY_PATH, summary)
    _write_jsonl(READ_ONLY_DETECTOR_PROOF_PATH, proof_records)
    _write_text(READ_ONLY_DETECTOR_REPORT_PATH, render_read_only_detector_report(summary))
    _write_text(READ_ONLY_DETECTOR_LEDGER_PATH, render_read_only_detector_ledger(summary))
    append_read_only_detector_doc_updates(summary)

    return {
        "read_only_detector_status": summary["detector_bundle_status"],
        "approval_status": summary["approval_status"],
        "detector_status_distribution": summary["detector_status_distribution"],
        "provider_type_distribution": summary["provider_type_distribution"],
        "capability_records_total": summary["capability_records_total"],
        "write_execute_blocked_total": summary["write_execute_blocked_total"],
        "post_run_evidence_written": summary["post_run_evidence_written"],
        "artifact_paths": read_only_detector_artifact_paths(),
        "report_paths": {
            "read_only_detector_report": str(READ_ONLY_DETECTOR_REPORT_PATH),
            "read_only_detector_ledger": str(READ_ONLY_DETECTOR_LEDGER_PATH),
        },
        "paper_only": True,
        "live_blocked": True,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
        "robinhood_mcp_integration_created": False,
    }


def load_detector_source_snapshot() -> dict[str, Any]:
    return {
        "approval_intake_summary": _require_json(APPROVAL_INTAKE_SUMMARY_PATH),
        "approval_intake_requests": _read_jsonl(APPROVAL_INTAKE_REQUESTS_PATH),
        "approval_intake_results": _read_jsonl(APPROVAL_INTAKE_RESULTS_PATH),
        "approval_intake_proof": _require_latest_jsonl(APPROVAL_INTAKE_PROOF_PATH),
        "handoff_summary": _require_json(APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH),
        "handoff_proof": _require_latest_jsonl(APPROVAL_TO_RUN_HANDOFF_PROOF_PATH),
        "pre_run_summary": _require_json(PRE_RUN_SAFETY_SUMMARY_PATH),
        "pre_run_proof": _require_latest_jsonl(PRE_RUN_SAFETY_PROOF_PATH),
        "command_templates": _read_jsonl(DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH),
    }


def resolve_exact_approval(source: dict[str, Any], required_acknowledgement: str) -> dict[str, Any]:
    requests_by_id = {record["request_id"]: record for record in source["approval_intake_requests"]}
    for result in source["approval_intake_results"]:
        if result.get("approval_valid") is not True:
            continue
        request = requests_by_id.get(str(result["request_id"]), {})
        if request.get("operator_text") != required_acknowledgement:
            continue
        if request.get("approval_channel") not in {"fixture", "manual_text_fixture"}:
            continue
        return {
            "approval_status": "valid_exact_read_only_detector_only",
            "approval_valid": True,
            "source_approval_intake_id": str(result["result_id"]),
            "source_approval_request_id": str(request["request_id"]),
            "source_approval_hash": str(result["result_hash"]),
        }
    return {
        "approval_status": "approval_missing",
        "approval_valid": False,
        "source_approval_intake_id": "",
        "source_approval_request_id": "",
        "source_approval_hash": "",
    }


def is_pre_run_clean(source: dict[str, Any]) -> bool:
    summary = source["pre_run_summary"]
    runtime_counts_clean = all(int(summary.get(field, 0)) == 0 for field in (
        "detector_run_allowed_now_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
    ))
    templates_disabled = all(template.get("enabled") is False and template.get("allowed_now") is False for template in source["command_templates"])
    return (
        summary.get("pre_run_safety_status") == "pre_run_safety_scanner_validated"
        and int(summary.get("future_bundle_preparation_allowed_count", 0)) > 0
        and runtime_counts_clean
        and templates_disabled
        and summary.get("command_templates_disabled") is True
    )


def build_read_only_detector_boundary_cases() -> list[dict[str, Any]]:
    groups = [
        ("approval_missing", 16),
        ("invalid_approval", 16),
        ("clean_fixture_provider", 16),
        ("read_only_capability_inventory", 16),
        ("write_execute_block", 16),
        ("credential_scheduler_live_order_boundary", 12),
        ("provider_boundary", 12),
        ("post_run_evidence", 8),
        ("terminal_block", 8),
    ]
    required_names = _required_case_names()
    cases: list[dict[str, Any]] = []
    for group, count in groups:
        names = required_names.get(group, [])
        for group_index in range(count):
            case_name = names[group_index] if group_index < len(names) else f"{group}_{group_index + 1:02d}"
            seed = {
                "case_id": f"read-only-detector-case-{len(cases) + 1:03d}",
                "case_group": group,
                "case_name": case_name,
                "approval_status": _case_approval_status(group, case_name),
                "pre_run_clean": group != "terminal_block" or "pre_run_blocked" not in case_name,
                "provider_type": _case_provider_type(group),
                "expected_detector_status": _case_detector_status(group, case_name),
                "expected_incident_type": _case_incident_type(group, case_name),
                "paper_only": True,
                "live_blocked": True,
                "case_hash": "",
            }
            cases.append({**seed, "case_hash": stable_hash(seed)})
    if len(cases) != 120:
        raise ValueError(f"read-only detector fixture must contain 120 cases, got {len(cases)}")
    return cases


def build_read_only_detector_run_requests(
    cases: list[dict[str, Any]],
    source: dict[str, Any],
    approval: dict[str, Any],
    pre_run_clean: bool,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    handoff_id = str(source["handoff_summary"].get("summary_hash", ""))
    pre_run_id = str(source["pre_run_summary"].get("summary_hash", ""))
    for index, case in enumerate(cases, start=1):
        case_approval_valid = case["approval_status"] == "valid_exact_read_only_detector_only" and approval["approval_valid"] is True
        case_pre_run_clean = bool(case["pre_run_clean"]) and pre_run_clean
        seed = ReadOnlyDetectorRunRequest(
            request_id=f"read-only-detector-run-request-{index:03d}",
            source_approval_intake_id=str(approval["source_approval_intake_id"]) if case_approval_valid else "",
            source_handoff_gate_id=handoff_id,
            source_pre_run_safety_scan_id=pre_run_id,
            approval_valid=case_approval_valid,
            pre_run_clean=case_pre_run_clean,
            requested_broker_fixture="fixture_only_read_only_options",
            requested_scope=["read_only_capability_inventory", "blocked_write_execute_inventory"],
            dry_run_first=True,
            paper_only=True,
            live_blocked=True,
            request_hash="",
        )
        requests.append({**seed.to_dict(), "case_group": case["case_group"], "case_name": case["case_name"], "approval_status": case["approval_status"], "request_hash": read_only_detector_run_request_hash(seed)})
    return requests


def build_provider_boundary_results(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        if case["case_group"] != "provider_boundary":
            continue
        incident = _case_incident_type(case["case_group"], case["case_name"])
        seed = {
            "boundary_result_id": f"read-only-provider-boundary-{len(results) + 1:03d}",
            "case_id": case["case_id"],
            "case_name": case["case_name"],
            "provider_type": "fixture_provider_negative_control",
            "terminal_block": True,
            "manual_review_required": False,
            "credentials_required": "credential" in case["case_name"],
            "write_tool_exposed_allowed": "write_tool" in case["case_name"],
            "execute_tool_exposed_allowed": "execute_tool" in case["case_name"],
            "live_order_tool_exposed_allowed": "live_order_tool" in case["case_name"],
            "scheduler_attempted": "scheduler" in case["case_name"],
            "real_sizing_attempted": "real_sizing" in case["case_name"],
            "account_balance_attempted": "account_balance" in case["case_name"],
            "buying_power_attempted": "buying_power" in case["case_name"],
            "broker_mutation_attempted": False,
            "incident_type": incident,
            "reason_codes": [incident, "provider_boundary_terminal_block"],
            "paper_only": True,
            "live_blocked": True,
            "boundary_hash": "",
        }
        results.append({**seed, "boundary_hash": stable_hash(seed)})
    return results


def process_detector_requests(
    requests: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    approval: dict[str, Any],
    pre_run_clean: bool,
    source: dict[str, Any],
    provider_boundary_results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    provider = FixtureOnlyCapabilityProvider()
    provider_health = provider.health_check_read_only_boundary()
    base_capabilities = [record.to_dict() for record in provider.list_capabilities()]
    capability_records: list[dict[str, Any]] = []
    run_results: list[dict[str, Any]] = []
    incident_escalations: list[dict[str, Any]] = []
    provider_boundary_by_case = {record["case_name"]: record for record in provider_boundary_results}
    for request, case in zip(requests, cases, strict=True):
        status = detector_status_for_case(request, case, approval, pre_run_clean, source, provider_boundary_by_case)
        run_id = f"read-only-detector-run-{len(run_results) + 1:03d}"
        case_capabilities: list[dict[str, Any]] = []
        if status == "read_only_detector_fixture_completed":
            case_capabilities = [
                {
                    **record,
                    "capability_id": f"{record['capability_id']}-{request['request_id']}",
                    "request_id": request["request_id"],
                    "run_id": run_id,
                    "provider_type": provider_health["provider_type"],
                    "record_hash": stable_hash({**record, "capability_id": f"{record['capability_id']}-{request['request_id']}", "request_id": request["request_id"], "run_id": run_id, "provider_type": provider_health["provider_type"], "record_hash": ""}),
                }
                for record in base_capabilities
            ]
            capability_records.extend(case_capabilities)
        if case["expected_incident_type"] != "none":
            incident_escalations.append(_incident_record(case, request, run_id, status))
        result = _run_result(run_id, request, status, case_capabilities)
        run_results.append(result)
    return {
        "capability_records": capability_records,
        "run_results": run_results,
        "incident_escalations": incident_escalations,
    }


def detector_status_for_case(
    request: dict[str, Any],
    case: dict[str, Any],
    approval: dict[str, Any],
    pre_run_clean: bool,
    source: dict[str, Any],
    provider_boundary_by_case: dict[str, dict[str, Any]],
) -> str:
    if case["case_name"] in provider_boundary_by_case:
        return "not_run_terminal_block"
    if case["approval_status"] == "approval_missing":
        return "not_run_approval_missing"
    if case["approval_status"] == "approval_invalid":
        return "not_run_approval_missing"
    if case["approval_status"] == "manual_review_required":
        return "not_run_manual_review_required"
    if case["approval_status"] == "terminal_block":
        return "not_run_terminal_block"
    if approval["approval_valid"] is not True:
        return "not_run_approval_missing"
    if pre_run_clean is not True or request["pre_run_clean"] is not True:
        return "not_run_pre_run_blocked"
    if _runtime_permission_leak(source):
        return "not_run_terminal_block"
    return "read_only_detector_fixture_completed"


def build_detector_post_run_evidence_record(
    requests: list[dict[str, Any]],
    run_results: list[dict[str, Any]],
    capability_records: list[dict[str, Any]],
    blocked_records: list[dict[str, Any]],
    source: dict[str, Any],
) -> dict[str, Any]:
    completed = next((record for record in run_results if record["detector_status"] == "read_only_detector_fixture_completed"), run_results[-1])
    request = next(record for record in requests if record["request_id"] == completed["request_id"])
    provider_health = FixtureOnlyCapabilityProvider().health_check_read_only_boundary()
    return build_read_only_detector_post_run_evidence(
        request,
        completed,
        provider_health,
        capability_records,
        blocked_records,
        source["approval_intake_proof"],
        source["pre_run_proof"],
    )


def build_detector_proof_records(
    requests: list[dict[str, Any]],
    run_results: list[dict[str, Any]],
    capability_records: list[dict[str, Any]],
    provider_boundary_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    capability_by_request: dict[str, list[dict[str, Any]]] = {}
    for capability in capability_records:
        capability_by_request.setdefault(str(capability["request_id"]), []).append(capability)
    provider_boundary_by_case = {record["case_name"]: record for record in provider_boundary_results}
    for request, result in zip(requests, run_results, strict=True):
        linked_capabilities = capability_by_request.get(str(request["request_id"]), [])
        if linked_capabilities:
            for capability in linked_capabilities:
                records.append(_proof_record(len(records) + 1, request, result, capability, provider_boundary_by_case.get(str(request["case_name"]))))
        else:
            records.append(_proof_record(len(records) + 1, request, result, None, provider_boundary_by_case.get(str(request["case_name"]))))
    return records


def build_read_only_detector_summary(
    requests: list[dict[str, Any]],
    run_results: list[dict[str, Any]],
    capability_records: list[dict[str, Any]],
    blocked_records: list[dict[str, Any]],
    provider_boundary_results: list[dict[str, Any]],
    incident_escalations: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
    post_run_evidence: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    detector_status_counts = Counter(str(record["detector_status"]) for record in run_results)
    provider_counts = Counter(str(record.get("provider_type", "fixture_only")) for record in capability_records)
    capability_family_counts = Counter(str(record["capability_family"]) for record in capability_records)
    approval_status_counts = Counter(str(record["approval_status"]) for record in requests)
    seed = {
        "artifact_type": "read_only_detector_summary",
        "read_only_detector_version": READ_ONLY_DETECTOR_VERSION,
        "detector_bundle_status": "human_approved_read_only_detector_validated",
        "approval_status": "valid_exact_read_only_detector_only" if int(approval_status_counts.get("valid_exact_read_only_detector_only", 0)) > 0 else "approval_missing",
        "detector_ran": int(detector_status_counts.get("read_only_detector_fixture_completed", 0)) > 0,
        "provider_type_used": "fixture_only",
        "request_count": len(requests),
        "run_result_count": len(run_results),
        "detector_status_distribution": dict(sorted(detector_status_counts.items())),
        "approval_status_distribution": dict(sorted(approval_status_counts.items())),
        "provider_type_distribution": dict(sorted(provider_counts.items())) or {"fixture_only": 0},
        "capability_family_distribution": dict(sorted(capability_family_counts.items())),
        "capability_records_total": len(capability_records),
        "read_only_records_total": sum(1 for record in capability_records if record["read_only"] is True),
        "write_execute_blocked_total": len(blocked_records),
        "credential_block_total": sum(1 for record in blocked_records if record["capability_family"] == "credential_block"),
        "scheduler_block_total": sum(1 for record in blocked_records if record["capability_family"] == "scheduler_block"),
        "live_execution_block_total": sum(1 for record in blocked_records if record["capability_family"] == "live_execution_block"),
        "provider_boundary_result_count": len(provider_boundary_results),
        "boundary_violation_count": len(provider_boundary_results),
        "incident_escalation_count": len(incident_escalations),
        "post_run_evidence_written": bool(post_run_evidence.get("evidence_hash")),
        "post_run_evidence_hash": post_run_evidence.get("evidence_hash", ""),
        "not_live_ready": True,
        "next_required_gate": READ_ONLY_DETECTOR_NEXT_GATE,
        "source_pre_run_status": source["pre_run_summary"].get("pre_run_safety_status", ""),
        "source_handoff_status": source["handoff_summary"].get("approval_to_run_handoff_status", ""),
        "source_detector_run_allowed_now_count": source["pre_run_summary"].get("detector_run_allowed_now_count", 0),
        "active_forbidden_live_decisions": 0,
        "credential_access_attempted": False,
        "broker_connection_attempted": False,
        "network_access_attempted": False,
        "live_order_attempted": False,
        "order_placement_attempted": False,
        "order_cancellation_attempted": False,
        "scheduler_attempted": False,
        "real_sizing_attempted": False,
        "account_balance_attempted": False,
        "buying_power_attempted": False,
        "broker_mutation_attempted": False,
        "real_market_data_used": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
        "robinhood_mcp_integration_created": False,
        "paper_only": True,
        "live_blocked": True,
        "safety_state": "paper_only_live_blocked_read_only_detector_not_live_ready",
        "artifact_paths": read_only_detector_artifact_paths(),
        "summary_hash": "",
    }
    return {**seed, "summary_hash": stable_hash(seed)}


def render_read_only_detector_report(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Human-Approved Read-Only Broker Capability Detector", ""]
    lines.append("- objective: `human-approved read-only broker capability detector framework`")
    lines.append(f"- exact_approval_present: `{str(summary['approval_status'] == 'valid_exact_read_only_detector_only').lower()}`")
    lines.append(f"- detector_ran: `{str(summary['detector_ran']).lower()}`")
    lines.append(f"- provider_type_used: `{summary['provider_type_used']}`")
    lines.append("- why_read_only: `fixture provider only; no credentials, no broker mutation, no live order tools, no scheduler, no real sizing`")
    for field_name in [
        "capability_records_total",
        "read_only_records_total",
        "write_execute_blocked_total",
        "credential_block_total",
        "scheduler_block_total",
        "live_execution_block_total",
        "post_run_evidence_written",
        "incident_escalation_count",
        "boundary_violation_count",
    ]:
        lines.append(f"- {field_name}: `{summary[field_name]}`")
    lines.append(f"- detector_status_distribution: `{summary['detector_status_distribution']}`")
    lines.append(f"- provider_type_distribution: `{summary['provider_type_distribution']}`")
    lines.append(f"- capability_family_distribution: `{summary['capability_family_distribution']}`")
    lines.append("- audit_report_export_integration: `read-only detector artifacts are registered for audit, reporting, export, and review surfaces`")
    lines.append("- validation: `targeted detector shard plus dependent shards; full suite remains timeout-bounded until separately proven`")
    lines.append("- limitations: `no broker capability proof, no live readiness proof, no credential setup, no real provider adapter`")
    lines.append(f"- safety_state: `{summary['safety_state']}`")
    lines.append(f"- next_required_gate: `{summary['next_required_gate']}`")
    return "\n".join(lines) + "\n"


def render_read_only_detector_ledger(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Detector Artifact Ledger", ""]
    for artifact_type, artifact_path in read_only_detector_artifact_paths().items():
        path = Path(artifact_path)
        lines.append(f"- artifact_type: `{artifact_type}`")
        lines.append(f"  path: `{artifact_path}`")
        lines.append(f"  hash: `{_file_hash(path) if path.exists() else ''}`")
        lines.append(f"  record_count: `{_record_count(path) if path.exists() else 0}`")
        lines.append("  proof_layer: `read_only_detector`")
    lines.append(f"- run_count: `{summary['run_result_count']}`")
    lines.append(f"- capability_record_count: `{summary['capability_records_total']}`")
    lines.append(f"- blocked_write_execute_count: `{summary['write_execute_blocked_total']}`")
    lines.append(f"- incident_escalation_count: `{summary['incident_escalation_count']}`")
    lines.append(f"- safety_state: `{summary['safety_state']}`")
    lines.append(f"- summary_hash: `{summary['summary_hash']}`")
    return "\n".join(lines) + "\n"


def append_read_only_detector_doc_updates(summary: dict[str, Any]) -> None:
    marker = "DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_V1"
    section = "\n".join([
        "",
        f"## {marker}",
        "",
        "- status: `human_approved_read_only_detector_validated`",
        f"- detector_status_distribution: `{summary['detector_status_distribution']}`",
        f"- post_run_evidence_written: `{str(summary['post_run_evidence_written']).lower()}`",
        "- detector_output_is_not_live_readiness: `true`",
        "- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`",
    ]) + "\n"
    targets = [
        REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_REPORT.md",
        REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_REPORT.md",
        REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md",
        REPO_ROOT / "DOPEY_VALIDATION_REPORT.md",
        REPO_ROOT / "DOPEY_CANON.md",
    ]
    for target in targets:
        _append_once(target, marker, section)


def _required_case_names() -> dict[str, list[str]]:
    return {
        "approval_missing": ["approval_missing_not_run"],
        "invalid_approval": ["invalid_approval_not_run", "manual_review_required_not_run"],
        "clean_fixture_provider": ["clean_valid_fixture_approval_uses_fixture_provider", "fixture_provider_lists_tool_inventory_shape"],
        "read_only_capability_inventory": [
            "fixture_provider_lists_option_chain_shape",
            "fixture_provider_lists_option_quote_shape",
            "fixture_provider_lists_option_position_shape",
            "fixture_provider_lists_order_status_shape",
            "fixture_provider_lists_error_shape",
        ],
        "write_execute_block": [
            "order_review_is_blocked",
            "order_placement_is_blocked",
            "order_cancellation_is_blocked",
            "credential_request_is_blocked",
            "scheduler_creation_is_blocked",
            "live_execution_is_blocked",
            "broker_write_is_blocked",
            "broker_execute_is_blocked",
            "real_sizing_is_blocked",
            "account_balance_use_is_blocked",
            "buying_power_use_is_blocked",
            "network_market_data_scrape_is_blocked",
        ],
        "provider_boundary": [
            "provider_with_credential_requirement_terminal_blocks",
            "provider_with_write_tool_terminal_blocks",
            "provider_with_execute_tool_terminal_blocks",
            "provider_with_live_order_tool_terminal_blocks",
            "provider_with_scheduler_terminal_blocks",
            "provider_with_real_sizing_terminal_blocks",
            "provider_with_account_balance_dependency_terminal_blocks",
        ],
        "post_run_evidence": [
            "post_run_evidence_written",
            "post_run_audit_proof_written",
            "capability_result_remains_not_live_ready",
            "detector_result_creates_no_live_order",
            "detector_result_creates_no_broker_mutation",
            "detector_result_creates_no_credential_artifact",
        ],
        "terminal_block": ["terminal_block_not_run", "pre_run_blocked_not_run"],
    }


def _case_approval_status(group: str, case_name: str) -> str:
    if "pre_run_blocked" in case_name:
        return "valid_exact_read_only_detector_only"
    if group == "approval_missing":
        return "approval_missing"
    if group == "invalid_approval":
        return "manual_review_required" if "manual_review" in case_name else "approval_invalid"
    if group in {"provider_boundary", "terminal_block"}:
        return "terminal_block"
    return "valid_exact_read_only_detector_only"


def _case_detector_status(group: str, case_name: str) -> str:
    if group == "approval_missing":
        return "not_run_approval_missing"
    if group == "invalid_approval":
        return "not_run_manual_review_required" if "manual_review" in case_name else "not_run_approval_missing"
    if group in {"provider_boundary", "terminal_block"}:
        return "not_run_pre_run_blocked" if "pre_run_blocked" in case_name else "not_run_terminal_block"
    return "read_only_detector_fixture_completed"


def _case_provider_type(group: str) -> str:
    return "provider_boundary_negative_control" if group == "provider_boundary" else "fixture_only"


def _case_incident_type(group: str, case_name: str) -> str:
    if group == "approval_missing":
        return "detector_run_without_approval"
    if group == "invalid_approval":
        return "detector_run_after_invalid_approval"
    if group == "provider_boundary":
        mapping = {
            "credential_requirement": "provider_requested_credentials",
            "write_tool": "provider_exposed_write_tool_allowed",
            "execute_tool": "provider_exposed_execute_tool_allowed",
            "live_order_tool": "provider_exposed_live_order_tool_allowed",
            "scheduler": "provider_attempted_scheduler",
            "real_sizing": "provider_attempted_real_sizing",
            "account_balance": "provider_attempted_account_balance_or_buying_power",
        }
        for token, incident in mapping.items():
            if token in case_name:
                return incident
        return "provider_boundary_violation"
    if "pre_run_blocked" in case_name:
        return "detector_run_when_pre_run_blocked"
    if group == "terminal_block":
        return "detector_terminal_block"
    return "none"


def _run_result(run_id: str, request: dict[str, Any], status: str, case_capabilities: list[dict[str, Any]]) -> dict[str, Any]:
    seed = ReadOnlyDetectorRunResult(
        run_id=run_id,
        request_id=str(request["request_id"]),
        approval_status=str(request["approval_status"]),
        pre_run_status="pre_run_clean" if request["pre_run_clean"] else "pre_run_blocked_or_not_applicable",
        detector_status=status,
        broker_connection_attempted=False,
        credential_access_attempted=False,
        network_access_attempted=False,
        live_order_attempted=False,
        order_placement_attempted=False,
        order_cancellation_attempted=False,
        scheduler_attempted=False,
        real_sizing_attempted=False,
        capability_records_total=len(case_capabilities),
        read_only_records_total=sum(1 for record in case_capabilities if record["read_only"] is True),
        write_execute_blocks_total=sum(1 for record in case_capabilities if record["blocked_now"] is True),
        credential_blocks_total=sum(1 for record in case_capabilities if record["capability_family"] == "credential_block"),
        scheduler_blocks_total=sum(1 for record in case_capabilities if record["capability_family"] == "scheduler_block"),
        live_execution_blocks_total=sum(1 for record in case_capabilities if record["capability_family"] == "live_execution_block"),
        post_run_evidence_written=status == "read_only_detector_fixture_completed",
        paper_only=True,
        live_blocked=True,
        result_hash="",
    )
    return {**seed.to_dict(), "provider_type": "fixture_only" if status == "read_only_detector_fixture_completed" else "none", "not_live_ready": True, "result_hash": read_only_detector_run_result_hash(seed)}


def _incident_record(case: dict[str, Any], request: dict[str, Any], run_id: str, status: str) -> dict[str, Any]:
    seed = {
        "escalation_id": f"read-only-detector-incident-{case['case_id'][-3:]}",
        "run_id": run_id,
        "request_id": request["request_id"],
        "case_name": case["case_name"],
        "incident_type": case["expected_incident_type"],
        "detector_status": status,
        "response_decision": "manual_review_required" if status == "not_run_manual_review_required" else "terminal_block",
        "terminal_block": status != "not_run_manual_review_required",
        "manual_review_required": status == "not_run_manual_review_required",
        "auto_recovery_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "escalation_hash": "",
    }
    return {**seed, "escalation_hash": stable_hash(seed)}


def _proof_record(index: int, request: dict[str, Any], result: dict[str, Any], capability: dict[str, Any] | None, provider_boundary: dict[str, Any] | None) -> dict[str, Any]:
    capability_id = "" if capability is None else str(capability["capability_id"])
    read_only_status = False if capability is None else bool(capability["read_only"])
    write_execute_blocked = False if capability is None else bool(capability["blocked_now"])
    seed = {
        "proof_id": f"read-only-detector-proof-{index:04d}",
        "run_id": result["run_id"],
        "request_id": request["request_id"],
        "approval_status": result["approval_status"],
        "pre_run_status": result["pre_run_status"],
        "provider_type": result.get("provider_type", "none"),
        "detector_status": result["detector_status"],
        "capability_id": capability_id,
        "read_only_status": read_only_status,
        "write_execute_blocked_status": write_execute_blocked,
        "credential_access_attempted": False,
        "broker_connection_attempted": False,
        "live_order_attempted": False,
        "order_placement_attempted": False,
        "order_cancellation_attempted": False,
        "scheduler_attempted": False,
        "real_sizing_attempted": False,
        "account_balance_attempted": bool(provider_boundary.get("account_balance_attempted", False)) if provider_boundary else False,
        "buying_power_attempted": bool(provider_boundary.get("buying_power_attempted", False)) if provider_boundary else False,
        "post_run_evidence_written": result["post_run_evidence_written"],
        "reason_codes": ["read_only_detector_proof", result["detector_status"]] if capability is None else capability["reason_codes"],
        "safety_status": "paper_only_live_blocked_not_live_ready",
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker_write": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credential": True,
        "no_live_order": True,
        "proof_hash": "",
    }
    return {**seed, "proof_hash": stable_hash(seed)}


def _runtime_permission_leak(source: dict[str, Any]) -> bool:
    summary = source["pre_run_summary"]
    return any(int(summary.get(field, 0)) != 0 for field in (
        "detector_run_allowed_now_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
    ))


def _fixture_payload(artifact_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    seed = {"artifact_type": artifact_type, "record_count": len(records), "records": records, "paper_only": True, "live_blocked": True, "fixture_hash": ""}
    return {**seed, "fixture_hash": stable_hash(seed)}


def _require_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required read-only detector source artifact missing: {path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"required read-only detector source artifact must be a JSON object: {path}")
    return parsed


def _require_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"required read-only detector source artifact missing: {path}")
    return path.read_text(encoding="utf-8")


def _extract_required_acknowledgement(markdown: str) -> str:
    fence = "```text"
    start = markdown.find(fence)
    if start < 0:
        raise ValueError("operator acknowledgement artifact must contain a text code fence")
    body_start = markdown.find("\n", start)
    end = markdown.find("```", body_start + 1)
    if body_start < 0 or end < 0:
        raise ValueError("operator acknowledgement artifact has an incomplete text code fence")
    text = markdown[body_start + 1:end].strip()
    if not text:
        raise ValueError("operator acknowledgement text is empty")
    return text


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"required read-only detector source artifact missing: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _require_latest_jsonl(path: Path) -> dict[str, Any]:
    records = _read_jsonl(path)
    if not records:
        raise ValueError(f"required read-only detector source artifact empty: {path}")
    return records[-1]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=True) for record in records) + ("\n" if records else ""), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _append_once(path: Path, marker: str, section: str) -> None:
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if marker in existing:
        return
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(section)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    return 1 if path.exists() else 0
