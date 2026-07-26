"""Build the offline manual-approval packet for future read-only detection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .boundary_incidents import broker_boundary_incident_records
from .broker_readiness_models import stable_hash
from .future_detector_command_templates import (
    build_future_detector_command_templates,
    forbidden_command_template_cases,
)
from .manual_approval_models import (
    EXPLICIT_MANUAL_APPROVAL_GATE,
    MANUAL_APPROVAL_PACKET_VERSION,
    REQUIRED_OPERATOR_ACKNOWLEDGEMENT,
    ReadOnlyDetectorApprovalPacket,
    make_manual_approval_gate,
    make_read_only_detector_approval_packet,
    make_read_only_detector_scope,
)
from .manual_gate_validator import build_expected_manual_gate_results, validate_manual_approval_text


REPO_ROOT = Path(__file__).resolve().parent.parent
from dopey_core.repo_paths import REPORTS_DIR
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "manual_approval"

MANUAL_APPROVAL_SCOPE_FIXTURE_PATH = FIXTURE_DIR / "manual_approval_scope.json"
MANUAL_APPROVAL_GATES_FIXTURE_PATH = FIXTURE_DIR / "manual_approval_gates.json"
MANUAL_APPROVAL_PACKET_CASES_FIXTURE_PATH = FIXTURE_DIR / "manual_approval_packet_cases.json"
FUTURE_DETECTOR_COMMAND_TEMPLATES_FIXTURE_PATH = FIXTURE_DIR / "future_detector_command_templates.json"
EXPECTED_MANUAL_GATE_RESULTS_PATH = FIXTURE_DIR / "expected_manual_gate_results.json"
EXPECTED_APPROVAL_PACKET_SUMMARY_PATH = FIXTURE_DIR / "expected_approval_packet_summary.json"

READ_ONLY_DETECTOR_SCOPE_PATH = ARTIFACT_DIR / "read_only_detector_scope.json"
MANUAL_APPROVAL_GATE_PATH = ARTIFACT_DIR / "manual_approval_gate.json"
READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH = ARTIFACT_DIR / "read_only_detector_approval_packet.json"
OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH = ARTIFACT_DIR / "operator_acknowledgement_required.md"
FUTURE_DETECTOR_COMMAND_TEMPLATES_PATH = ARTIFACT_DIR / "future_detector_command_templates.jsonl"
MANUAL_GATE_VALIDATION_RESULTS_PATH = ARTIFACT_DIR / "manual_gate_validation_results.jsonl"
MANUAL_APPROVAL_BOUNDARY_BLOCKS_PATH = ARTIFACT_DIR / "manual_approval_boundary_blocks.jsonl"
MANUAL_APPROVAL_PACKET_SUMMARY_PATH = ARTIFACT_DIR / "manual_approval_packet_summary.json"
MANUAL_APPROVAL_PACKET_PROOF_PATH = ARTIFACT_DIR / "manual_approval_packet_proof.jsonl"

MANUAL_APPROVAL_REPORT_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_BROKER_CAPABILITY_DETECTOR_MANUAL_APPROVAL_PACKET_REPORT.md"
MANUAL_APPROVAL_LEDGER_PATH = REPORTS_DIR / "DOPEY_MANUAL_APPROVAL_PACKET_ARTIFACT_LEDGER.md"

SOURCE_EVIDENCE_PATHS: dict[str, Path] = {
    "broker_readiness_run_result": REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "broker_readiness_run_result.json",
    "read_only_boundary_simulations": REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "read_only_boundary_simulations.jsonl",
    "incident_response_proof": REPO_ROOT / "artifacts" / "dopey" / "incident_response" / "incident_response_proof.jsonl",
    "lifecycle_proof": REPO_ROOT / "artifacts" / "dopey" / "lifecycle" / "lifecycle_proof.jsonl",
    "portfolio_replay_summary": REPO_ROOT / "artifacts" / "dopey" / "portfolio_replay" / "portfolio_replay_summary.json",
    "stress_ladder_summary": REPO_ROOT / "artifacts" / "dopey" / "portfolio_stress_ladder" / "stress_ladder_summary.json",
    "allocation_proof": REPO_ROOT / "artifacts" / "dopey" / "allocation" / "allocation_proof.jsonl",
    "audit_safety": REPO_ROOT / "artifacts" / "dopey" / "audit" / "safety_audit.jsonl",
    "export_safety_scan": REPO_ROOT / "artifacts" / "dopey" / "exports" / "export_safety_scan.jsonl",
    "export_review_proof": REPO_ROOT / "artifacts" / "dopey" / "export_reviews" / "export_review_proof.jsonl",
}


def manual_approval_artifact_paths() -> dict[str, str]:
    return {
        "read_only_detector_scope": str(READ_ONLY_DETECTOR_SCOPE_PATH),
        "manual_approval_gate": str(MANUAL_APPROVAL_GATE_PATH),
        "read_only_detector_approval_packet": str(READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH),
        "operator_acknowledgement_required": str(OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH),
        "future_detector_command_templates": str(FUTURE_DETECTOR_COMMAND_TEMPLATES_PATH),
        "manual_gate_validation_results": str(MANUAL_GATE_VALIDATION_RESULTS_PATH),
        "manual_approval_boundary_blocks": str(MANUAL_APPROVAL_BOUNDARY_BLOCKS_PATH),
        "manual_approval_packet_summary": str(MANUAL_APPROVAL_PACKET_SUMMARY_PATH),
        "manual_approval_packet_proof": str(MANUAL_APPROVAL_PACKET_PROOF_PATH),
    }


def build_manual_approval_packet_cases() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    groups: list[tuple[str, int]] = [
        ("valid_read_only_scope_definition", 12),
        ("missing_or_invalid_approval", 12),
        ("scope_expansion_rejection", 12),
        ("forbidden_command_template", 12),
        ("terminal_block_escalation", 8),
        ("manual_review", 8),
        ("benign_packet_ready", 8),
    ]
    required_names = [
        "packet_ready_with_approval_missing",
        "exact_acknowledgement_future_fixture_valid",
        "partial_acknowledgement_rejected",
        "approval_mentions_live_trading_rejected",
        "approval_mentions_credential_storage_rejected",
        "approval_mentions_order_placement_rejected",
        "approval_mentions_order_cancellation_rejected",
        "approval_mentions_scheduler_rejected",
        "approval_mentions_autonomous_live_trading_rejected",
        "approval_mentions_real_sizing_rejected",
        "approval_expands_to_write_access_rejected",
        "approval_expands_to_broker_execution_rejected",
        "command_template_disabled_by_default",
        "command_template_requires_manual_approval",
        "command_template_with_token_path_rejected",
        "command_template_with_env_file_rejected",
        "command_template_with_order_placement_rejected",
        "command_template_with_cancellation_rejected",
        "command_template_with_scheduler_rejected",
        "detector_run_without_approval_terminal_blocked",
        "detector_scope_expansion_terminal_blocked",
        "template_enabled_without_approval_terminal_blocked",
        "network_call_attempt_terminal_blocked",
        "broker_connection_attempt_terminal_blocked",
        "credential_request_terminal_blocked",
        "live_order_review_attempt_terminal_blocked",
        "live_order_placement_attempt_terminal_blocked",
        "real_buying_power_read_terminal_blocked",
        "real_account_balance_read_terminal_blocked",
        "real_sizing_logic_terminal_blocked",
        "packet_requires_source_preflight_evidence",
        "packet_requires_incident_response_evidence",
        "packet_requires_lifecycle_evidence",
        "packet_requires_audit_export_evidence",
        "packet_next_gate_remains_manual_approval",
        "packet_does_not_approve_detector_by_itself",
    ]
    index = 0
    for group_name, count in groups:
        for group_index in range(1, count + 1):
            case_name = required_names[index] if index < len(required_names) else f"{group_name}_{group_index:02d}"
            expected = _expected_case_status(group_name, case_name)
            seed = {
                "case_id": f"manual-approval-case-{index + 1:03d}",
                "case_name": case_name,
                "case_group": group_name,
                "expected_status": expected["status"],
                "terminal_block": expected["terminal_block"],
                "manual_review": expected["manual_review"],
                "detector_approved_now": False,
                "allowed_now": False,
                "requires_manual_approval": True,
                "reason_codes": expected["reason_codes"],
                "paper_only": True,
                "live_blocked": True,
            }
            records.append({**seed, "case_hash": stable_hash({**seed, "case_hash": ""})})
            index += 1
    return records


def build_manual_approval_boundary_blocks() -> list[dict[str, Any]]:
    terminal_incidents = {
        "read_only_detector_run_attempt_without_approval",
        "detector_scope_expansion_attempt",
        "command_template_enabled_without_approval",
        "detector_network_call_attempt_in_packet_bundle",
        "detector_broker_connection_attempt_in_packet_bundle",
        "credential_request",
        "broker_order_review_attempt",
        "broker_order_placement_attempt",
        "buying_power_read",
        "real_account_balance_read",
        "real_sizing_logic",
    }
    records: list[dict[str, Any]] = []
    for incident in broker_boundary_incident_records():
        if incident["incident_type"] not in terminal_incidents:
            continue
        seed = {
            "block_id": f"manual-approval-boundary-{len(records) + 1:03d}",
            "incident_type": incident["incident_type"],
            "blocked_operation": incident["incident_type"],
            "kill_switch_state": "terminal_block",
            "response_decision": "terminal_block",
            "approval_bypass": True,
            "auto_recovery_allowed": False,
            "reason_codes": ["manual_approval_bypass_terminal_block", incident["incident_type"]],
            "paper_only": True,
            "live_blocked": True,
        }
        records.append({**seed, "block_hash": stable_hash({**seed, "block_hash": ""})})
    return records


def build_manual_approval_summary(
    packet: ReadOnlyDetectorApprovalPacket,
    cases: list[dict[str, Any]],
    command_templates: list[dict[str, Any]],
    validation_results: list[dict[str, Any]],
    boundary_blocks: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {
        "artifact_type": "manual_approval_packet_summary",
        "manual_approval_packet_version": MANUAL_APPROVAL_PACKET_VERSION,
        "packet_id": packet.packet_id,
        "readiness_status": "approval_packet_ready",
        "approval_status": "approval_missing",
        "approval_present": False,
        "approval_valid": False,
        "detector_approved_now": False,
        "detector_run_now": False,
        "future_detector_scope": "read_only_broker_capability_detector_only",
        "operator_acknowledgement_required": REQUIRED_OPERATOR_ACKNOWLEDGEMENT,
        "exact_acknowledgement_required": True,
        "command_template_count": len(command_templates),
        "command_templates_disabled": all(template["enabled"] is False for template in command_templates),
        "command_templates_require_manual_approval": all(template["requires_manual_approval"] is True for template in command_templates),
        "command_templates_allowed_now": False,
        "case_count": len(cases),
        "validation_result_count": len(validation_results),
        "boundary_block_count": len(boundary_blocks),
        "proof_record_count": len(proof_records),
        "next_required_gate": EXPLICIT_MANUAL_APPROVAL_GATE,
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
        "sequential_shards_reliable": True,
        "artifact_writing_shards_parallel_race_risk": True,
    }
    return {**summary, "summary_hash": stable_hash({**summary, "summary_hash": ""})}


def build_manual_approval_packet_outputs() -> dict[str, Any]:
    preflight_run = _require_json(SOURCE_EVIDENCE_PATHS["broker_readiness_run_result"])
    _require_jsonl(SOURCE_EVIDENCE_PATHS["read_only_boundary_simulations"])
    source_evidence = _load_source_evidence_status()
    scope = make_read_only_detector_scope()
    gate = make_manual_approval_gate()
    packet = make_read_only_detector_approval_packet(str(preflight_run["run_id"]), scope, gate)
    command_templates = [template.to_dict() for template in build_future_detector_command_templates()]
    validation_results = build_expected_manual_gate_results()
    cases = build_manual_approval_packet_cases()
    boundary_blocks = build_manual_approval_boundary_blocks()
    proof_records = build_manual_approval_proof_records(packet, cases, command_templates, validation_results, boundary_blocks)
    summary = build_manual_approval_summary(packet, cases, command_templates, validation_results, boundary_blocks, proof_records)

    _write_json(MANUAL_APPROVAL_SCOPE_FIXTURE_PATH, _fixture_payload("manual_approval_scope", [scope.to_dict()]))
    _write_json(MANUAL_APPROVAL_GATES_FIXTURE_PATH, _fixture_payload("manual_approval_gates", [gate.to_dict()]))
    _write_json(MANUAL_APPROVAL_PACKET_CASES_FIXTURE_PATH, _fixture_payload("manual_approval_packet_cases", cases))
    _write_json(FUTURE_DETECTOR_COMMAND_TEMPLATES_FIXTURE_PATH, _fixture_payload("future_detector_command_templates", command_templates))
    _write_json(EXPECTED_MANUAL_GATE_RESULTS_PATH, _fixture_payload("expected_manual_gate_results", validation_results))
    _write_json(EXPECTED_APPROVAL_PACKET_SUMMARY_PATH, summary)

    _write_json(READ_ONLY_DETECTOR_SCOPE_PATH, scope.to_dict())
    _write_json(MANUAL_APPROVAL_GATE_PATH, gate.to_dict())
    _write_json(READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH, packet.to_dict())
    _write_text(OPERATOR_ACKNOWLEDGEMENT_REQUIRED_PATH, _operator_acknowledgement_markdown())
    _write_jsonl(FUTURE_DETECTOR_COMMAND_TEMPLATES_PATH, command_templates)
    _write_jsonl(MANUAL_GATE_VALIDATION_RESULTS_PATH, validation_results)
    _write_jsonl(MANUAL_APPROVAL_BOUNDARY_BLOCKS_PATH, boundary_blocks)
    _write_json(MANUAL_APPROVAL_PACKET_SUMMARY_PATH, summary)
    _write_jsonl(MANUAL_APPROVAL_PACKET_PROOF_PATH, proof_records)
    _write_text(MANUAL_APPROVAL_REPORT_PATH, _render_report(summary, packet.to_dict(), source_evidence))
    _write_text(MANUAL_APPROVAL_LEDGER_PATH, _render_ledger())

    response = {
        "manual_approval_packet_status": "ok",
        "readiness_status": summary["readiness_status"],
        "approval_status": summary["approval_status"],
        "detector_approved_now": False,
        "detector_run_now": False,
        "next_required_gate": summary["next_required_gate"],
        "case_count": summary["case_count"],
        "command_template_count": summary["command_template_count"],
        "boundary_block_count": summary["boundary_block_count"],
        "proof_record_count": summary["proof_record_count"],
        "artifact_paths": manual_approval_artifact_paths(),
        "report_paths": {
            "manual_approval_report": str(MANUAL_APPROVAL_REPORT_PATH),
            "manual_approval_ledger": str(MANUAL_APPROVAL_LEDGER_PATH),
        },
        "paper_only": True,
        "live_blocked": True,
        "no_broker_connection": True,
        "no_credentials": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "no_robinhood_mcp_integration": True,
    }
    return {**response, "reproducibility_hash": stable_hash(response)}


def build_manual_approval_proof_records(
    packet: ReadOnlyDetectorApprovalPacket,
    cases: list[dict[str, Any]],
    command_templates: list[dict[str, Any]],
    validation_results: list[dict[str, Any]],
    boundary_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in cases:
        records.append(_proof_record(packet, f"proof-{case['case_id']}", "", case.get("case_name", ""), case["reason_codes"]))
    for template in command_templates:
        records.append(_proof_record(packet, f"proof-{template['template_id']}", template["template_id"], "", template["reason_codes"]))
    for result in validation_results:
        records.append(_proof_record(packet, f"proof-{result['validation_id']}", "", "", result["reason_codes"]))
    for block in boundary_blocks:
        records.append(_proof_record(packet, f"proof-{block['block_id']}", "", block["blocked_operation"], block["reason_codes"]))
    return records


def _proof_record(packet: ReadOnlyDetectorApprovalPacket, proof_id: str, command_template_id: str, blocked_operation: str, reason_codes: list[str]) -> dict[str, Any]:
    seed = {
        "proof_id": proof_id,
        "packet_id": packet.packet_id,
        "scope_id": packet.scope_id,
        "gate_id": packet.manual_gate_id,
        "approval_present": False,
        "approval_valid": False,
        "detector_approved_now": False,
        "allowed_now": False,
        "command_template_id": command_template_id,
        "blocked_operation": blocked_operation,
        "reason_codes": reason_codes,
        "safety_status": "paper_only_live_blocked_detector_not_approved",
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credential": True,
        "no_live_order": True,
    }
    return {**seed, "proof_hash": stable_hash({**seed, "proof_hash": ""})}


def audit_manual_approval_packet_artifacts() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not MANUAL_APPROVAL_PACKET_SUMMARY_PATH.exists():
        return [{"check_id": "manual_approval_summary_missing", "severity": "safety_error"}]
    summary = json.loads(MANUAL_APPROVAL_PACKET_SUMMARY_PATH.read_text(encoding="utf-8"))
    if summary.get("approval_present") is not False:
        findings.append({"check_id": "manual_approval_not_present", "severity": "safety_error"})
    if summary.get("detector_approved_now") is not False:
        findings.append({"check_id": "manual_approval_detector_not_approved", "severity": "safety_error"})
    if summary.get("next_required_gate") != EXPLICIT_MANUAL_APPROVAL_GATE:
        findings.append({"check_id": "manual_approval_next_gate", "severity": "safety_error"})
    for template in _read_jsonl_if_exists(FUTURE_DETECTOR_COMMAND_TEMPLATES_PATH):
        if template.get("enabled") is not False:
            findings.append({"check_id": "manual_approval_template_disabled", "severity": "safety_error"})
        if template.get("requires_manual_approval") is not True:
            findings.append({"check_id": "manual_approval_template_requires_approval", "severity": "safety_error"})
    return findings


def audit_command_template_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    command = str(record.get("command_template", "")).lower()
    checks = [
        ("credential", "template_contains_credentials"),
        ("api_key", "template_contains_credentials"),
        ("token_path", "template_contains_token_path"),
        (".env", "template_contains_env"),
        ("place-order", "template_contains_order_placement"),
        ("place_order", "template_contains_order_placement"),
        ("cancel-order", "template_contains_order_cancellation"),
        ("cancel_order", "template_contains_order_cancellation"),
        ("scheduler", "template_contains_scheduler"),
        ("broker-connect", "template_contains_broker_connection"),
        ("enable-live", "template_contains_live_trading"),
        ("live-execution", "template_contains_live_trading"),
    ]
    return [
        {"check_id": check_id, "severity": "safety_error"}
        for token, check_id in checks
        if token in command
    ]


def _expected_case_status(group_name: str, case_name: str) -> dict[str, Any]:
    if group_name == "terminal_block_escalation" or "terminal_blocked" in case_name:
        return {"status": "terminal_block", "terminal_block": True, "manual_review": False, "reason_codes": ["terminal_block_required", case_name]}
    if group_name == "manual_review":
        return {"status": "manual_review_required", "terminal_block": False, "manual_review": True, "reason_codes": ["manual_review_required", case_name]}
    if group_name in {"missing_or_invalid_approval", "scope_expansion_rejection", "forbidden_command_template"}:
        return {"status": "rejected", "terminal_block": False, "manual_review": False, "reason_codes": ["approval_or_template_rejected", case_name]}
    return {"status": "packet_ready", "terminal_block": False, "manual_review": False, "reason_codes": ["packet_ready_not_approved", case_name]}


def _fixture_payload(artifact_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"artifact_type": artifact_type, "case_count": len(records), "records": records, "paper_only": True, "live_blocked": True}
    return {**payload, "fixture_hash": stable_hash(payload)}


def _load_source_evidence_status() -> dict[str, Any]:
    return {
        name: {"path": str(path), "exists": path.exists(), "record_count": len(_read_jsonl_if_exists(path)) if path.suffix == ".jsonl" else (1 if path.exists() else 0)}
        for name, path in SOURCE_EVIDENCE_PATHS.items()
    }


def _operator_acknowledgement_markdown() -> str:
    return "\n".join([
        "# DOPEY Read-Only Detector Operator Acknowledgement Required",
        "",
        "This text is required for a future bundle only. This packet does not approve or run the detector.",
        "",
        "```text",
        REQUIRED_OPERATOR_ACKNOWLEDGEMENT,
        "```",
        "",
        "- exact_match_required: `true`",
        "- approval_present_in_this_bundle: `false`",
        "- detector_approved_now: `false`",
        "- detector_run_now: `false`",
        "- paper_only: `true`",
        "- live_blocked: `true`",
    ]) + "\n"


def _render_report(summary: dict[str, Any], packet: dict[str, Any], source_evidence: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Broker Capability Detector Manual Approval Packet Report", ""]
    lines.append("This bundle creates an offline manual-approval packet only. It is not detector execution, broker integration, Robinhood MCP integration, credential setup, live trading, scheduling, real sizing, or market-data access.")
    lines.append("")
    lines.append("## Summary")
    for key in ["readiness_status", "approval_status", "detector_approved_now", "detector_run_now", "next_required_gate", "case_count", "command_template_count", "boundary_block_count", "proof_record_count"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("## Exact Acknowledgement")
    lines.append(f"- required_text: `{REQUIRED_OPERATOR_ACKNOWLEDGEMENT}`")
    lines.append("- approval_present_in_this_bundle: `false`")
    lines.append("")
    lines.append("## Forbidden Operations")
    for operation in packet["blocking_conditions"]:
        lines.append(f"- `{operation}`")
    lines.append("")
    lines.append("## Source Evidence")
    for name, evidence in source_evidence.items():
        lines.append(f"- `{name}`: exists=`{str(evidence['exists']).lower()}` records=`{evidence['record_count']}`")
    lines.append("")
    lines.append("## Limitations")
    lines.append("- The future detector remains disabled and unapproved.")
    lines.append("- Full suite timeout remains `inconclusive_timeout`, not pass.")
    lines.append("- Any bypass into credentials, broker execution, scheduler, network market data, real sizing, order review, order placement, or cancellation terminal-blocks.")
    approval_intake_summary = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "approval_intake" / "approval_intake_summary.json"
    if approval_intake_summary.exists():
        lines.append("")
        lines.append("## Approval Intake Validator")
        lines.append("- Approval-intake validator exists and can recognize exact valid fixture approval text.")
        lines.append("- Detector still does not run in this bundle.")
    return "\n".join(lines) + "\n"


def _render_ledger() -> str:
    lines = ["# DOPEY Manual Approval Packet Artifact Ledger", ""]
    for artifact_type, artifact_path in manual_approval_artifact_paths().items():
        path = Path(artifact_path)
        lines.append(f"- artifact_type: `{artifact_type}`")
        lines.append(f"  path: `{path}`")
        lines.append(f"  hash: `{_file_hash(path) if path.exists() else ''}`")
        lines.append(f"  record_count: `{_record_count(path) if path.exists() else 0}`")
        lines.append("  safety_state: `paper_only_live_blocked_detector_not_approved`")
    return "\n".join(lines) + "\n"


def _require_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required manual approval source artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"required manual approval source artifact missing: {path}")
    return _read_jsonl_if_exists(path)


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return len(_read_jsonl_if_exists(path))
    return 1
