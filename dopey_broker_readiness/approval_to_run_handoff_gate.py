"""Offline approval-to-run handoff gate for a future read-only detector bundle."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .approval_intake_validator import APPROVAL_INTAKE_SUMMARY_PATH
from .approval_to_run_handoff_models import (
    APPROVAL_TO_RUN_HANDOFF_GATE_VERSION,
    APPROVAL_TO_RUN_NEXT_GATE,
    ApprovalToRunGateDecision,
    ApprovalToRunHandoffInput,
    approval_to_run_gate_decision_hash,
    approval_to_run_handoff_input_hash,
)
from .broker_readiness_models import stable_hash
from .disabled_handoff_command_registry import build_disabled_handoff_command_templates
from .future_detector_run_envelope import build_future_detector_run_envelope
from .manual_approval_packet_builder import MANUAL_APPROVAL_PACKET_SUMMARY_PATH
from .read_only_detector_dry_run_validator import DRY_RUN_SUMMARY_PATH


REPO_ROOT = Path(__file__).resolve().parent.parent
from dopey_core.repo_paths import REPORTS_DIR
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness"
ARTIFACT_DIR = ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff"

BROKER_READINESS_SUMMARY_PATH = ARTIFACT_ROOT / "broker_readiness" / "broker_readiness_summary.json"
INCIDENT_REHEARSAL_SUMMARY_PATH = ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"
LIFECYCLE_SUMMARY_PATH = ARTIFACT_ROOT / "lifecycle" / "lifecycle_summary.json"
AUDIT_PROOF_PATH = ARTIFACT_ROOT / "audit" / "evidence_replay_audit_proof.jsonl"
EXPORT_SAFETY_SCAN_PATH = ARTIFACT_ROOT / "exports" / "export_safety_scan.jsonl"
EXPORT_REVIEW_PROOF_PATH = ARTIFACT_ROOT / "export_reviews" / "export_review_proof.jsonl"

HANDOFF_INPUTS_FIXTURE_PATH = FIXTURE_DIR / "approval_to_run_handoff_inputs.json"
FUTURE_DETECTOR_RUN_ENVELOPES_FIXTURE_PATH = FIXTURE_DIR / "future_detector_run_envelopes.json"
APPROVAL_TO_RUN_GATE_DECISIONS_FIXTURE_PATH = FIXTURE_DIR / "approval_to_run_gate_decisions.json"
DISABLED_HANDOFF_COMMAND_TEMPLATES_FIXTURE_PATH = FIXTURE_DIR / "disabled_handoff_command_templates.json"
EXPECTED_HANDOFF_SUMMARY_FIXTURE_PATH = FIXTURE_DIR / "expected_approval_to_run_handoff_summary.json"

HANDOFF_INPUTS_PATH = ARTIFACT_DIR / "handoff_inputs.jsonl"
FUTURE_DETECTOR_RUN_ENVELOPES_PATH = ARTIFACT_DIR / "future_detector_run_envelopes.jsonl"
APPROVAL_TO_RUN_GATE_DECISIONS_PATH = ARTIFACT_DIR / "approval_to_run_gate_decisions.jsonl"
DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH = ARTIFACT_DIR / "disabled_handoff_command_templates.jsonl"
HANDOFF_BOUNDARY_BLOCKS_PATH = ARTIFACT_DIR / "handoff_boundary_blocks.jsonl"
HANDOFF_INCIDENT_ESCALATIONS_PATH = ARTIFACT_DIR / "handoff_incident_escalations.jsonl"
APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH = ARTIFACT_DIR / "approval_to_run_handoff_summary.json"
APPROVAL_TO_RUN_HANDOFF_PROOF_PATH = ARTIFACT_DIR / "approval_to_run_handoff_proof.jsonl"

APPROVAL_TO_RUN_HANDOFF_REPORT_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_REPORT.md"
APPROVAL_TO_RUN_HANDOFF_LEDGER_PATH = REPORTS_DIR / "DOPEY_APPROVAL_TO_RUN_HANDOFF_GATE_ARTIFACT_LEDGER.md"


def approval_to_run_handoff_artifact_paths() -> dict[str, str]:
    return {
        "handoff_inputs": str(HANDOFF_INPUTS_PATH),
        "future_detector_run_envelopes": str(FUTURE_DETECTOR_RUN_ENVELOPES_PATH),
        "approval_to_run_gate_decisions": str(APPROVAL_TO_RUN_GATE_DECISIONS_PATH),
        "disabled_handoff_command_templates": str(DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH),
        "handoff_boundary_blocks": str(HANDOFF_BOUNDARY_BLOCKS_PATH),
        "handoff_incident_escalations": str(HANDOFF_INCIDENT_ESCALATIONS_PATH),
        "approval_to_run_handoff_summary": str(APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH),
        "approval_to_run_handoff_proof": str(APPROVAL_TO_RUN_HANDOFF_PROOF_PATH),
    }


def validate_read_only_detector_approval_to_run_handoff_gate() -> dict[str, Any]:
    source_snapshot = load_handoff_source_snapshot()
    command_templates = build_disabled_handoff_command_templates()
    inputs = build_approval_to_run_handoff_inputs(source_snapshot)
    envelopes = build_future_detector_run_envelopes(inputs, command_templates)
    decisions = build_approval_to_run_gate_decisions(inputs, envelopes)
    boundary_blocks = build_handoff_boundary_blocks(inputs, decisions)
    incident_escalations = build_handoff_incident_escalations(boundary_blocks)
    proof_records = build_approval_to_run_handoff_proof_records(inputs, envelopes, decisions, source_snapshot)
    summary = build_approval_to_run_handoff_summary(
        source_snapshot,
        inputs,
        envelopes,
        decisions,
        command_templates,
        boundary_blocks,
        incident_escalations,
        proof_records,
    )

    _write_json(HANDOFF_INPUTS_FIXTURE_PATH, _fixture_payload("approval_to_run_handoff_inputs", inputs))
    _write_json(FUTURE_DETECTOR_RUN_ENVELOPES_FIXTURE_PATH, _fixture_payload("future_detector_run_envelopes", envelopes))
    _write_json(APPROVAL_TO_RUN_GATE_DECISIONS_FIXTURE_PATH, _fixture_payload("approval_to_run_gate_decisions", decisions))
    _write_json(DISABLED_HANDOFF_COMMAND_TEMPLATES_FIXTURE_PATH, _fixture_payload("disabled_handoff_command_templates", command_templates))
    _write_json(EXPECTED_HANDOFF_SUMMARY_FIXTURE_PATH, summary)

    _write_jsonl(HANDOFF_INPUTS_PATH, inputs)
    _write_jsonl(FUTURE_DETECTOR_RUN_ENVELOPES_PATH, envelopes)
    _write_jsonl(APPROVAL_TO_RUN_GATE_DECISIONS_PATH, decisions)
    _write_jsonl(DISABLED_HANDOFF_COMMAND_TEMPLATES_PATH, command_templates)
    _write_jsonl(HANDOFF_BOUNDARY_BLOCKS_PATH, boundary_blocks)
    _write_jsonl(HANDOFF_INCIDENT_ESCALATIONS_PATH, incident_escalations)
    _write_json(APPROVAL_TO_RUN_HANDOFF_SUMMARY_PATH, summary)
    _write_jsonl(APPROVAL_TO_RUN_HANDOFF_PROOF_PATH, proof_records)
    _write_text(APPROVAL_TO_RUN_HANDOFF_REPORT_PATH, render_approval_to_run_handoff_report(summary))
    _write_text(APPROVAL_TO_RUN_HANDOFF_LEDGER_PATH, render_approval_to_run_handoff_ledger(summary))
    append_approval_to_run_handoff_doc_updates(summary)

    return {
        "approval_to_run_handoff_gate_status": "ok",
        "approval_to_run_handoff_status": summary["approval_to_run_handoff_status"],
        "input_count": summary["input_count"],
        "envelope_count": summary["envelope_count"],
        "gate_decision_count": summary["gate_decision_count"],
        "gate_status_distribution": summary["gate_status_distribution"],
        "future_bundle_eligible_count": summary["future_bundle_eligible_count"],
        "current_detector_run_allowed_count": summary["current_detector_run_allowed_count"],
        "broker_connection_allowed_now_count": summary["broker_connection_allowed_now_count"],
        "credential_allowed_now_count": summary["credential_allowed_now_count"],
        "live_order_allowed_now_count": summary["live_order_allowed_now_count"],
        "scheduler_allowed_now_count": summary["scheduler_allowed_now_count"],
        "real_sizing_allowed_now_count": summary["real_sizing_allowed_now_count"],
        "artifact_paths": approval_to_run_handoff_artifact_paths(),
        "report_paths": {
            "approval_to_run_handoff_report": str(APPROVAL_TO_RUN_HANDOFF_REPORT_PATH),
            "approval_to_run_handoff_ledger": str(APPROVAL_TO_RUN_HANDOFF_LEDGER_PATH),
        },
        "paper_only": True,
        "live_blocked": True,
        "read_only_detector_run": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "robinhood_mcp_integration_created": False,
    }


def load_handoff_source_snapshot() -> dict[str, Any]:
    return {
        "manual_approval_packet_summary": _require_json(MANUAL_APPROVAL_PACKET_SUMMARY_PATH),
        "read_only_detector_dry_run_summary": _require_json(DRY_RUN_SUMMARY_PATH),
        "approval_intake_summary": _require_json(APPROVAL_INTAKE_SUMMARY_PATH),
        "broker_readiness_summary": _require_json(BROKER_READINESS_SUMMARY_PATH),
        "incident_rehearsal_summary": _require_json(INCIDENT_REHEARSAL_SUMMARY_PATH),
        "lifecycle_summary": _require_json(LIFECYCLE_SUMMARY_PATH),
        "audit_proof": _require_latest_jsonl(AUDIT_PROOF_PATH),
        "export_safety_scan": _require_latest_jsonl(EXPORT_SAFETY_SCAN_PATH),
        "export_review_proof": _require_latest_jsonl(EXPORT_REVIEW_PROOF_PATH),
        "source_paths": {
            "manual_approval_packet_summary": str(MANUAL_APPROVAL_PACKET_SUMMARY_PATH),
            "read_only_detector_dry_run_summary": str(DRY_RUN_SUMMARY_PATH),
            "approval_intake_summary": str(APPROVAL_INTAKE_SUMMARY_PATH),
            "broker_readiness_summary": str(BROKER_READINESS_SUMMARY_PATH),
            "incident_rehearsal_summary": str(INCIDENT_REHEARSAL_SUMMARY_PATH),
            "lifecycle_summary": str(LIFECYCLE_SUMMARY_PATH),
            "audit_proof": str(AUDIT_PROOF_PATH),
            "export_safety_scan": str(EXPORT_SAFETY_SCAN_PATH),
            "export_review_proof": str(EXPORT_REVIEW_PROOF_PATH),
        },
    }


def build_approval_to_run_handoff_inputs(source_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case_group, count in _handoff_case_groups():
        for index in range(count):
            records.append(_handoff_input_record(len(records) + 1, source_snapshot, case_group, index + 1))
    if len(records) != 72:
        raise ValueError(f"approval-to-run handoff fixture must contain 72 cases, got {len(records)}")
    return records


def build_future_detector_run_envelopes(inputs: list[dict[str, Any]], command_templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not command_templates:
        raise ValueError("approval-to-run handoff requires disabled command templates")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(inputs):
        eligible = record["case_group"] == "eligible_future_bundle_only"
        template = command_templates[index % len(command_templates)]
        records.append(build_future_detector_run_envelope(
            f"future-detector-run-envelope-{index + 1:03d}",
            str(record["handoff_input_id"]),
            str(template["template_id"]),
            eligible,
        ))
    return records


def build_approval_to_run_gate_decisions(inputs: list[dict[str, Any]], envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(inputs) != len(envelopes):
        raise ValueError("approval-to-run handoff inputs and envelopes must have matching lengths")
    records: list[dict[str, Any]] = []
    for index, pair in enumerate(zip(inputs, envelopes, strict=True)):
        handoff_input, envelope = pair
        status = _gate_status(handoff_input)
        eligible = status == "eligible_future_bundle_only"
        reasons = _reason_codes(status)
        seed = ApprovalToRunGateDecision(
            gate_decision_id=f"approval-to-run-gate-decision-{index + 1:03d}",
            handoff_input_id=str(handoff_input["handoff_input_id"]),
            envelope_id=str(envelope["envelope_id"]),
            gate_status=status,
            reason_codes=reasons,
            future_bundle_eligible=eligible,
            detector_run_blocked_now=True,
            detector_run_allowed_now=False,
            broker_connection_allowed_now=False,
            credential_allowed_now=False,
            live_order_allowed_now=False,
            scheduler_allowed_now=False,
            real_sizing_allowed_now=False,
            requires_separate_future_bundle=True,
            requires_explicit_operator_reapproval=True,
            requires_pre_run_safety_scan=True,
            requires_post_run_evidence=True,
            incident_escalation=not eligible,
            next_required_gate=APPROVAL_TO_RUN_NEXT_GATE,
            paper_only=True,
            live_blocked=True,
            decision_hash="",
        )
        records.append({**seed.to_dict(), "case_group": handoff_input["case_group"], "case_name": handoff_input["case_name"], "decision_hash": approval_to_run_gate_decision_hash(seed)})
    return records


def build_handoff_boundary_blocks(inputs: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for handoff_input, decision in zip(inputs, decisions, strict=True):
        if decision["gate_status"] == "eligible_future_bundle_only":
            continue
        block_seed = {
            "block_id": f"handoff-boundary-block-{len(records) + 1:03d}",
            "handoff_input_id": handoff_input["handoff_input_id"],
            "gate_decision_id": decision["gate_decision_id"],
            "incident_type": _incident_type_for_status(str(decision["gate_status"])),
            "gate_status": decision["gate_status"],
            "kill_switch_state": "terminal_block" if decision["gate_status"] != "manual_review_required" else "manual_review_required",
            "response_decision": decision["gate_status"],
            "auto_recovery_allowed": False,
            "paper_only": True,
            "live_blocked": True,
            "reason_codes": decision["reason_codes"],
            "block_hash": "",
        }
        records.append({**block_seed, "block_hash": stable_hash(block_seed)})
    return records


def build_handoff_incident_escalations(boundary_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in boundary_blocks:
        escalation_seed = {
            "escalation_id": f"handoff-incident-escalation-{len(records) + 1:03d}",
            "block_id": block["block_id"],
            "incident_type": block["incident_type"],
            "response_decision": block["response_decision"],
            "kill_switch_state": block["kill_switch_state"],
            "requires_operator_review": block["response_decision"] == "manual_review_required",
            "auto_recovery_allowed": False,
            "paper_only": True,
            "live_blocked": True,
            "escalation_hash": "",
        }
        records.append({**escalation_seed, "escalation_hash": stable_hash(escalation_seed)})
    return records


def build_approval_to_run_handoff_proof_records(
    inputs: list[dict[str, Any]],
    envelopes: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    source_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    source_hashes = _source_hashes(source_snapshot)
    for index, triple in enumerate(zip(inputs, envelopes, decisions, strict=True)):
        handoff_input, envelope, decision = triple
        proof_seed = {
            "proof_id": f"approval-to-run-handoff-proof-{index + 1:03d}",
            "handoff_gate_version": APPROVAL_TO_RUN_HANDOFF_GATE_VERSION,
            "handoff_input_id": handoff_input["handoff_input_id"],
            "envelope_id": envelope["envelope_id"],
            "gate_decision_id": decision["gate_decision_id"],
            "case_group": handoff_input["case_group"],
            "gate_status": decision["gate_status"],
            "future_bundle_eligible": decision["future_bundle_eligible"],
            "current_detector_run_allowed": False,
            "broker_connection_allowed_now": False,
            "credential_allowed_now": False,
            "live_order_allowed_now": False,
            "scheduler_allowed_now": False,
            "real_sizing_allowed_now": False,
            "source_hashes": source_hashes,
            "paper_only": True,
            "live_blocked": True,
            "proof_hash": "",
        }
        records.append({**proof_seed, "proof_hash": stable_hash(proof_seed)})
    return records


def build_approval_to_run_handoff_summary(
    source_snapshot: dict[str, Any],
    inputs: list[dict[str, Any]],
    envelopes: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    command_templates: list[dict[str, Any]],
    boundary_blocks: list[dict[str, Any]],
    incident_escalations: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(str(decision["gate_status"]) for decision in decisions)
    summary_seed = {
        "artifact_type": "approval_to_run_handoff_summary",
        "approval_to_run_handoff_gate_version": APPROVAL_TO_RUN_HANDOFF_GATE_VERSION,
        "approval_to_run_handoff_status": "handoff_gate_validated",
        "input_count": len(inputs),
        "envelope_count": len(envelopes),
        "gate_decision_count": len(decisions),
        "gate_status_distribution": dict(sorted(status_counts.items())),
        "future_bundle_eligible_count": int(status_counts.get("eligible_future_bundle_only", 0)),
        "blocked_missing_valid_approval_count": int(status_counts.get("blocked_missing_valid_approval", 0)),
        "blocked_terminal_incident_count": int(status_counts.get("blocked_terminal_incident", 0)),
        "manual_review_required_count": int(status_counts.get("manual_review_required", 0)),
        "blocked_audit_or_export_failure_count": int(status_counts.get("blocked_audit_or_export_failure", 0)),
        "blocked_runtime_permission_leak_count": int(status_counts.get("blocked_runtime_permission_leak", 0)),
        "blocked_scope_expansion_count": int(status_counts.get("blocked_scope_expansion", 0)),
        "blocked_timeout_misclassified_as_pass_count": int(status_counts.get("blocked_timeout_misclassified_as_pass", 0)),
        "current_detector_run_allowed_count": _true_count(decisions, "detector_run_allowed_now"),
        "broker_connection_allowed_now_count": _true_count(decisions, "broker_connection_allowed_now"),
        "credential_allowed_now_count": _true_count(decisions, "credential_allowed_now"),
        "live_order_allowed_now_count": _true_count(decisions, "live_order_allowed_now"),
        "scheduler_allowed_now_count": _true_count(decisions, "scheduler_allowed_now"),
        "real_sizing_allowed_now_count": _true_count(decisions, "real_sizing_allowed_now"),
        "separate_future_bundle_required_count": _true_count(decisions, "requires_separate_future_bundle"),
        "explicit_reapproval_required_count": _true_count(decisions, "requires_explicit_operator_reapproval"),
        "pre_run_safety_scan_required_count": _true_count(decisions, "requires_pre_run_safety_scan"),
        "post_run_evidence_required_count": _true_count(decisions, "requires_post_run_evidence"),
        "disabled_command_template_count": len(command_templates),
        "command_templates_disabled": all(template["enabled"] is False and template["allowed_now"] is False for template in command_templates),
        "boundary_block_count": len(boundary_blocks),
        "incident_escalation_count": len(incident_escalations),
        "proof_record_count": len(proof_records),
        "source_hashes": _source_hashes(source_snapshot),
        "source_paths": source_snapshot["source_paths"],
        "source_approval_intake_future_detector_eligible_count": int(source_snapshot["approval_intake_summary"].get("future_detector_eligible_count", 0)),
        "source_approval_intake_terminal_block_count": int(source_snapshot["approval_intake_summary"].get("terminal_block_count", 0)),
        "source_approval_intake_manual_review_count": int(source_snapshot["approval_intake_summary"].get("manual_review_count", 0)),
        "source_export_active_forbidden_live_decisions": int(source_snapshot["export_safety_scan"].get("active_forbidden_live_decisions", 0)),
        "source_export_credential_findings": int(source_snapshot["export_safety_scan"].get("credential_findings", 0)),
        "source_full_suite_status": str(source_snapshot["approval_intake_summary"].get("full_suite_status", "")),
        "source_full_suite_timeout_recorded_as_pass": bool(source_snapshot["approval_intake_summary"].get("full_suite_timeout_recorded_as_pass", False)),
        "next_required_gate": APPROVAL_TO_RUN_NEXT_GATE,
        "paper_only": True,
        "live_blocked": True,
        "fixture_only": True,
        "offline_only": True,
        "read_only_detector_run": False,
        "detector_run_allowed_now": False,
        "broker_connection_allowed_now": False,
        "credential_allowed_now": False,
        "live_order_allowed_now": False,
        "scheduler_allowed_now": False,
        "real_sizing_allowed_now": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
        "robinhood_mcp_integration_created": False,
        "real_account_balance_logic_created": False,
        "real_buying_power_logic_created": False,
        "operator_reapproval_required_for_future_run": True,
        "pre_run_safety_scan_required_for_future_run": True,
        "post_run_evidence_required_for_future_run": True,
        "summary_hash": "",
    }
    return {**summary_seed, "summary_hash": stable_hash(summary_seed)}


def render_approval_to_run_handoff_report(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Detector Approval-To-Run Handoff Gate", ""]
    lines.append("- offline_only: `true`")
    lines.append("- fixture_only: `true`")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append(f"- approval_to_run_handoff_status: `{summary['approval_to_run_handoff_status']}`")
    lines.append(f"- input_count: `{summary['input_count']}`")
    lines.append(f"- gate_decision_count: `{summary['gate_decision_count']}`")
    lines.append(f"- gate_status_distribution: `{summary['gate_status_distribution']}`")
    lines.append(f"- future_bundle_eligible_count: `{summary['future_bundle_eligible_count']}`")
    lines.append(f"- current_detector_run_allowed_count: `{summary['current_detector_run_allowed_count']}`")
    lines.append(f"- broker_connection_allowed_now_count: `{summary['broker_connection_allowed_now_count']}`")
    lines.append(f"- credential_allowed_now_count: `{summary['credential_allowed_now_count']}`")
    lines.append(f"- live_order_allowed_now_count: `{summary['live_order_allowed_now_count']}`")
    lines.append(f"- scheduler_allowed_now_count: `{summary['scheduler_allowed_now_count']}`")
    lines.append(f"- real_sizing_allowed_now_count: `{summary['real_sizing_allowed_now_count']}`")
    lines.append(f"- separate_future_bundle_required_count: `{summary['separate_future_bundle_required_count']}`")
    lines.append(f"- explicit_reapproval_required_count: `{summary['explicit_reapproval_required_count']}`")
    lines.append(f"- pre_run_safety_scan_required_count: `{summary['pre_run_safety_scan_required_count']}`")
    lines.append(f"- post_run_evidence_required_count: `{summary['post_run_evidence_required_count']}`")
    lines.append(f"- disabled_command_template_count: `{summary['disabled_command_template_count']}`")
    lines.append("- detector_run_in_this_bundle: `false`")
    lines.append("- broker_connection_in_this_bundle: `false`")
    lines.append("- credentials_in_this_bundle: `false`")
    lines.append("- scheduler_in_this_bundle: `false`")
    lines.append("- real_sizing_in_this_bundle: `false`")
    lines.append(f"- next_required_gate: `{summary['next_required_gate']}`")
    return "\n".join(lines) + "\n"


def render_approval_to_run_handoff_ledger(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Approval-To-Run Handoff Gate Artifact Ledger", ""]
    for artifact_id, artifact_path in approval_to_run_handoff_artifact_paths().items():
        lines.append(f"- `{artifact_id}`: `{artifact_path}`")
    lines.append(f"- `summary_hash`: `{summary['summary_hash']}`")
    lines.append(f"- `report_path`: `{APPROVAL_TO_RUN_HANDOFF_REPORT_PATH}`")
    lines.append(f"- `ledger_path`: `{APPROVAL_TO_RUN_HANDOFF_LEDGER_PATH}`")
    return "\n".join(lines) + "\n"


def append_approval_to_run_handoff_doc_updates(summary: dict[str, Any]) -> None:
    section = "\n".join([
        "",
        "## DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_V1",
        "",
        "- status: `handoff_gate_validated`",
        f"- future_bundle_eligible_count: `{summary['future_bundle_eligible_count']}`",
        "- current_detector_run_allowed_count: `0`",
        "- broker_connection_allowed_now_count: `0`",
        "- credential_allowed_now_count: `0`",
        "- live_order_allowed_now_count: `0`",
        "- scheduler_allowed_now_count: `0`",
        "- real_sizing_allowed_now_count: `0`",
        "- separate_future_bundle_required: `true`",
        "- explicit_reapproval_required: `true`",
        "- pre_run_safety_scan_required: `true`",
        "- post_run_evidence_required: `true`",
    ]) + "\n"
    targets = [
        REPO_ROOT / "DOPEY_CANON.md",
        REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md",
        REPO_ROOT / "DOPEY_VALIDATION_REPORT.md",
        REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_REPORT.md",
        REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_DRY_RUN_FIXTURE_VALIDATOR_REPORT.md",
        REPORTS_DIR / "DOPEY_READ_ONLY_BROKER_CAPABILITY_DETECTOR_MANUAL_APPROVAL_PACKET_REPORT.md",
    ]
    marker = "DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_V1"
    for target in targets:
        _append_once(target, marker, section)


def _handoff_case_groups() -> list[tuple[str, int]]:
    return [
        ("eligible_future_bundle_only", 12),
        ("blocked_missing_valid_approval", 12),
        ("blocked_terminal_incident", 12),
        ("manual_review_required", 8),
        ("blocked_audit_or_export_failure", 8),
        ("blocked_runtime_permission_leak", 8),
        ("blocked_scope_expansion", 6),
        ("blocked_timeout_misclassified_as_pass", 6),
    ]


def _handoff_input_record(index: int, source_snapshot: dict[str, Any], case_group: str, group_index: int) -> dict[str, Any]:
    approval_intake = source_snapshot["approval_intake_summary"]
    export_safety = source_snapshot["export_safety_scan"]
    source_hashes = _source_hashes(source_snapshot)
    exact_valid_fixture = case_group != "blocked_missing_valid_approval"
    source_future_detector_eligible_count = int(approval_intake.get("future_detector_eligible_count", 0)) if exact_valid_fixture else 0
    source_manual_review_count = int(approval_intake.get("manual_review_count", 0))
    source_terminal_block_count = int(approval_intake.get("terminal_block_count", 0))
    source_active_forbidden_live_decisions = int(export_safety.get("active_forbidden_live_decisions", 0))
    source_credential_findings = int(export_safety.get("credential_findings", 0))
    source_full_suite_status = str(approval_intake.get("full_suite_status", ""))
    source_full_suite_timeout_recorded_as_pass = bool(approval_intake.get("full_suite_timeout_recorded_as_pass", False))
    terminal_incident_in_handoff_path = False
    runtime_permission_leak_attempted = False
    scope_expansion_detected = False
    if case_group == "blocked_terminal_incident":
        terminal_incident_in_handoff_path = True
        source_terminal_block_count += 1
    if case_group == "manual_review_required":
        source_manual_review_count += 1
    if case_group == "blocked_audit_or_export_failure":
        source_active_forbidden_live_decisions = 1 if group_index % 2 else source_active_forbidden_live_decisions
        source_credential_findings = 1 if group_index % 2 == 0 else source_credential_findings
    if case_group == "blocked_runtime_permission_leak":
        runtime_permission_leak_attempted = True
    if case_group == "blocked_scope_expansion":
        scope_expansion_detected = True
    if case_group == "blocked_timeout_misclassified_as_pass":
        source_full_suite_status = "pass"
        source_full_suite_timeout_recorded_as_pass = True
    seed = ApprovalToRunHandoffInput(
        handoff_input_id=f"approval-to-run-handoff-input-{index:03d}",
        source_manual_approval_packet_summary_hash=source_hashes["manual_approval_packet_summary"],
        source_dry_run_summary_hash=source_hashes["read_only_detector_dry_run_summary"],
        source_approval_intake_summary_hash=source_hashes["approval_intake_summary"],
        source_broker_readiness_summary_hash=source_hashes["broker_readiness_summary"],
        source_incident_summary_hash=source_hashes["incident_rehearsal_summary"],
        source_lifecycle_summary_hash=source_hashes["lifecycle_summary"],
        source_audit_summary_hash=source_hashes["audit_proof"],
        source_export_summary_hash=source_hashes["export_safety_scan"],
        source_review_summary_hash=source_hashes["export_review_proof"],
        exact_valid_fixture_approval_available=exact_valid_fixture,
        source_future_detector_eligible_count=source_future_detector_eligible_count,
        source_manual_review_count=source_manual_review_count,
        source_terminal_block_count=source_terminal_block_count,
        source_active_forbidden_live_decisions=source_active_forbidden_live_decisions,
        source_credential_findings=source_credential_findings,
        source_full_suite_status=source_full_suite_status,
        source_full_suite_timeout_recorded_as_pass=source_full_suite_timeout_recorded_as_pass,
        terminal_incident_in_handoff_path=terminal_incident_in_handoff_path,
        runtime_permission_leak_attempted=runtime_permission_leak_attempted,
        scope_expansion_detected=scope_expansion_detected,
        case_group=case_group,
        case_name=f"{case_group}_{group_index:02d}",
        paper_only=True,
        live_blocked=True,
        input_hash="",
    )
    return {**seed.to_dict(), "input_hash": approval_to_run_handoff_input_hash(seed)}


def _gate_status(handoff_input: dict[str, Any]) -> str:
    if handoff_input["source_full_suite_timeout_recorded_as_pass"] is True:
        return "blocked_timeout_misclassified_as_pass"
    if handoff_input["runtime_permission_leak_attempted"] is True:
        return "blocked_runtime_permission_leak"
    if handoff_input["scope_expansion_detected"] is True:
        return "blocked_scope_expansion"
    if handoff_input["source_active_forbidden_live_decisions"] > 0 or handoff_input["source_credential_findings"] > 0:
        return "blocked_audit_or_export_failure"
    if handoff_input["terminal_incident_in_handoff_path"] is True:
        return "blocked_terminal_incident"
    if str(handoff_input["case_group"]) == "manual_review_required":
        return "manual_review_required"
    if handoff_input["exact_valid_fixture_approval_available"] is not True or handoff_input["source_future_detector_eligible_count"] < 1:
        return "blocked_missing_valid_approval"
    return "eligible_future_bundle_only"


def _reason_codes(gate_status: str) -> list[str]:
    common = [
        "broker_connection_not_created",
        "credential_read_not_allowed",
        "detector_not_run_in_this_bundle",
        "explicit_operator_reapproval_required",
        "post_run_evidence_required",
        "pre_run_safety_scan_required",
        "separate_future_bundle_required",
    ]
    status_reasons = {
        "eligible_future_bundle_only": ["exact_valid_fixture_approval_consumed"],
        "blocked_missing_valid_approval": ["missing_valid_detector_only_approval"],
        "blocked_terminal_incident": ["terminal_incident_in_handoff_path"],
        "manual_review_required": ["manual_review_required_before_handoff"],
        "blocked_audit_or_export_failure": ["audit_or_export_failure_detected"],
        "blocked_runtime_permission_leak": ["runtime_permission_leak_attempted"],
        "blocked_scope_expansion": ["scope_expansion_detected"],
        "blocked_timeout_misclassified_as_pass": ["timeout_cannot_be_recorded_as_pass"],
    }
    return sorted(set(common + status_reasons[gate_status]))


def _incident_type_for_status(gate_status: str) -> str:
    incident_types = {
        "blocked_missing_valid_approval": "handoff_missing_valid_approval",
        "blocked_terminal_incident": "handoff_terminal_incident",
        "manual_review_required": "handoff_manual_review_required",
        "blocked_audit_or_export_failure": "handoff_audit_export_failure",
        "blocked_runtime_permission_leak": "handoff_runtime_permission_leak",
        "blocked_scope_expansion": "handoff_scope_expansion",
        "blocked_timeout_misclassified_as_pass": "handoff_timeout_recorded_as_pass",
    }
    return incident_types[gate_status]


def _source_hashes(source_snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        "manual_approval_packet_summary": _record_hash(source_snapshot["manual_approval_packet_summary"]),
        "read_only_detector_dry_run_summary": _record_hash(source_snapshot["read_only_detector_dry_run_summary"]),
        "approval_intake_summary": _record_hash(source_snapshot["approval_intake_summary"]),
        "broker_readiness_summary": _record_hash(source_snapshot["broker_readiness_summary"]),
        "incident_rehearsal_summary": _record_hash(source_snapshot["incident_rehearsal_summary"]),
        "lifecycle_summary": _record_hash(source_snapshot["lifecycle_summary"]),
        "audit_proof": _record_hash(source_snapshot["audit_proof"]),
        "export_safety_scan": _record_hash(source_snapshot["export_safety_scan"]),
        "export_review_proof": _record_hash(source_snapshot["export_review_proof"]),
    }


def _record_hash(record: dict[str, Any]) -> str:
    for field_name in ("summary_hash", "reproducibility_hash", "proof_hash", "record_hash"):
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
        raise FileNotFoundError(f"required approval-to-run handoff source artifact missing: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"required approval-to-run handoff source artifact empty: {path}")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"required approval-to-run handoff source artifact must be a JSON object: {path}")
    return parsed


def _require_latest_jsonl(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required approval-to-run handoff source artifact missing: {path}")
    records = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError(f"required approval-to-run handoff source artifact empty: {path}")
    parsed = json.loads(records[-1])
    if not isinstance(parsed, dict):
        raise ValueError(f"required approval-to-run handoff source artifact must contain JSON objects: {path}")
    return parsed


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
