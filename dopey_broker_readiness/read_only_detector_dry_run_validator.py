"""Offline fixture validator for a future read-only broker capability detector."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .broker_readiness_models import stable_hash
from .boundary_incidents import broker_boundary_incident_records
from .dry_run_detector_models import (
    ALLOWED_READ_ONLY_REQUEST_CLASSES,
    DRY_RUN_VALIDATOR_VERSION,
    FORBIDDEN_REQUEST_CLASSES,
    FORBIDDEN_SHAPE_FIELDS,
    ReadOnlyDetectorDryRunInput,
    ReadOnlyDetectorDryRunResult,
    SimulatedBrokerCapabilityResponse,
    dry_run_input_hash,
    dry_run_result_hash,
)
from .dry_run_schema_models import forbidden_shape_library, read_only_shape_library
from .manual_approval_models import EXPLICIT_MANUAL_APPROVAL_GATE
from .manual_approval_packet_builder import MANUAL_APPROVAL_PACKET_SUMMARY_PATH, READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH
from .simulated_broker_response_models import build_base_simulated_capability_responses


REPO_ROOT = Path(__file__).resolve().parent.parent
from dopey_core.repo_paths import REPORTS_DIR
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "dry_run"

DRY_RUN_INPUTS_FIXTURE_PATH = FIXTURE_DIR / "dry_run_detector_inputs.json"
SIMULATED_RESPONSES_FIXTURE_PATH = FIXTURE_DIR / "simulated_broker_capability_responses.json"
SIMULATED_READ_ONLY_SHAPES_FIXTURE_PATH = FIXTURE_DIR / "simulated_read_only_shapes.json"
SIMULATED_FORBIDDEN_SHAPES_FIXTURE_PATH = FIXTURE_DIR / "simulated_forbidden_shapes.json"
EXPECTED_DRY_RUN_RESULTS_FIXTURE_PATH = FIXTURE_DIR / "expected_dry_run_results.json"

DRY_RUN_INPUTS_PATH = ARTIFACT_DIR / "read_only_detector_dry_run_inputs.jsonl"
SIMULATED_RESPONSES_PATH = ARTIFACT_DIR / "simulated_broker_capability_responses.jsonl"
SIMULATED_READ_ONLY_SHAPES_PATH = ARTIFACT_DIR / "simulated_read_only_shapes.json"
SIMULATED_FORBIDDEN_SHAPES_PATH = ARTIFACT_DIR / "simulated_forbidden_shapes.json"
DRY_RUN_RESULTS_PATH = ARTIFACT_DIR / "read_only_detector_dry_run_results.jsonl"
DRY_RUN_BOUNDARY_BLOCKS_PATH = ARTIFACT_DIR / "dry_run_boundary_blocks.jsonl"
FUTURE_DETECTOR_CONTRACT_PATH = ARTIFACT_DIR / "future_detector_contract.md"
DRY_RUN_SUMMARY_PATH = ARTIFACT_DIR / "read_only_detector_dry_run_summary.json"
DRY_RUN_PROOF_PATH = ARTIFACT_DIR / "read_only_detector_dry_run_proof.jsonl"

DRY_RUN_REPORT_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_DRY_RUN_FIXTURE_VALIDATOR_REPORT.md"
DRY_RUN_LEDGER_PATH = REPORTS_DIR / "DOPEY_READ_ONLY_DETECTOR_DRY_RUN_ARTIFACT_LEDGER.md"


def dry_run_artifact_paths() -> dict[str, str]:
    return {
        "read_only_detector_dry_run_inputs": str(DRY_RUN_INPUTS_PATH),
        "simulated_broker_capability_responses": str(SIMULATED_RESPONSES_PATH),
        "simulated_read_only_shapes": str(SIMULATED_READ_ONLY_SHAPES_PATH),
        "simulated_forbidden_shapes": str(SIMULATED_FORBIDDEN_SHAPES_PATH),
        "read_only_detector_dry_run_results": str(DRY_RUN_RESULTS_PATH),
        "dry_run_boundary_blocks": str(DRY_RUN_BOUNDARY_BLOCKS_PATH),
        "future_detector_contract": str(FUTURE_DETECTOR_CONTRACT_PATH),
        "read_only_detector_dry_run_summary": str(DRY_RUN_SUMMARY_PATH),
        "read_only_detector_dry_run_proof": str(DRY_RUN_PROOF_PATH),
    }


def build_dry_run_inputs(source_approval_packet_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    broker_names = ["SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "SIMULATED_GENERIC_OPTIONS_BROKER"]
    groups = [
        ("input_validation", 16),
        ("read_only_response", 16),
        ("options_shape", 16),
        ("write_execute_block", 16),
        ("credential_scheduler_network_block", 8),
        ("approval_missing_detector_not_run", 8),
        ("schema_violation", 8),
        ("incident_escalation", 8),
    ]
    index = 0
    for group_name, count in groups:
        for _ in range(count):
            seed = ReadOnlyDetectorDryRunInput(
                dry_run_id=f"read-only-detector-dry-run-{index + 1:03d}",
                source_approval_packet_id=source_approval_packet_id,
                approval_status="approval_missing",
                detector_approved=False,
                simulated_broker_name=broker_names[index % len(broker_names)],
                simulated_request_classes=list(ALLOWED_READ_ONLY_REQUEST_CLASSES),
                forbidden_request_classes=list(FORBIDDEN_REQUEST_CLASSES),
                manual_gate_required=True,
                paper_only=True,
                live_blocked=True,
                input_hash="",
            )
            records.append({**seed.to_dict(), "case_group": group_name, "input_hash": dry_run_input_hash(seed)})
            index += 1
    return records


def build_simulated_broker_capability_responses() -> list[dict[str, Any]]:
    base = [record.to_dict() for record in build_base_simulated_capability_responses()]
    records: list[dict[str, Any]] = []
    index = 0
    while len(records) < 32:
        source = base[index % len(base)]
        copied = dict(source)
        copied["response_id"] = f"simulated-broker-response-{index + 1:03d}"
        copied["capability_name"] = f"{source['capability_name']}_{index + 1:03d}"
        copied["response_hash"] = stable_hash({**copied, "response_hash": ""})
        records.append(copied)
        index += 1
    return records


def build_dry_run_results(inputs: list[dict[str, Any]], responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, record in enumerate(inputs):
        attempted = _attempt_flags(record["case_group"], index)
        status = _status_for_attempts(attempted, record["case_group"])
        seed = ReadOnlyDetectorDryRunResult(
            dry_run_id=record["dry_run_id"],
            inputs_validated=1,
            schemas_validated=1,
            simulated_responses_validated=len(responses),
            allowed_read_only_shapes=sum(1 for response in responses if response["read_only_shape_available"] is True),
            blocked_write_execute_shapes=sum(1 for response in responses if response["write_or_execute_shape_blocked"] is True),
            credential_blocks=sum(1 for response in responses if "credentials_forbidden" in response["reason_codes"]),
            scheduler_blocks=sum(1 for response in responses if "scheduler_forbidden" in response["reason_codes"]),
            network_blocks=sum(1 for response in responses if "no_real_market_data" in response["reason_codes"] or "quote_shape_no_fetch" in response["reason_codes"]),
            live_execution_blocks=sum(1 for response in responses if "live_execution_forbidden" in response["reason_codes"]),
            approval_required=True,
            approval_present=False,
            detector_run_attempted=attempted["detector_run_attempted"],
            broker_connection_attempted=attempted["broker_connection_attempted"],
            credential_access_attempted=attempted["credential_access_attempted"],
            network_access_attempted=attempted["network_access_attempted"],
            live_order_attempted=attempted["live_order_attempted"],
            dry_run_status=status,
            paper_only=True,
            live_blocked=True,
            result_hash="",
        )
        results.append({**seed.to_dict(), "case_group": record["case_group"], "result_hash": dry_run_result_hash(seed)})
    return results


def build_dry_run_boundary_blocks() -> list[dict[str, Any]]:
    incident_types = {
        "dry_run_detector_run_attempt",
        "dry_run_broker_connection_attempt",
        "dry_run_credential_read_attempt",
        "dry_run_env_access_attempt",
        "dry_run_network_call_attempt",
        "dry_run_order_review_attempt",
        "dry_run_order_placement_attempt",
        "dry_run_order_cancellation_attempt",
        "dry_run_real_sizing_attempt",
        "dry_run_scheduler_creation_attempt",
        "dry_run_command_template_enablement_attempt",
        "dry_run_schema_allowed_forbidden_field",
    }
    source = broker_boundary_incident_records()
    records: list[dict[str, Any]] = []
    for incident_type in sorted(incident_types):
        seed = {
            "block_id": f"dry-run-boundary-block-{len(records) + 1:03d}",
            "incident_type": incident_type,
            "blocked_operation": incident_type,
            "kill_switch_state": "manual_review_required" if incident_type == "dry_run_schema_allowed_forbidden_field" else "terminal_block",
            "response_decision": "manual_review_required" if incident_type == "dry_run_schema_allowed_forbidden_field" else "terminal_block",
            "source_boundary_incident_count": len(source),
            "auto_recovery_allowed": False,
            "reason_codes": ["dry_run_validator_boundary", incident_type],
            "paper_only": True,
            "live_blocked": True,
        }
        records.append({**seed, "block_hash": stable_hash({**seed, "block_hash": ""})})
    return records


def build_dry_run_proof_records(inputs: list[dict[str, Any]], responses: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    response_by_index = responses or []
    records: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        response = response_by_index[index % len(response_by_index)]
        seed = {
            "proof_id": f"dry-run-proof-{index + 1:03d}",
            "dry_run_id": result["dry_run_id"],
            "source_manual_approval_packet_id": inputs[index]["source_approval_packet_id"],
            "approval_present": False,
            "detector_approved": False,
            "detector_run_attempted": result["detector_run_attempted"],
            "broker_connection_attempted": result["broker_connection_attempted"],
            "credential_access_attempted": result["credential_access_attempted"],
            "network_access_attempted": result["network_access_attempted"],
            "live_order_attempted": result["live_order_attempted"],
            "request_class": inputs[index]["simulated_request_classes"][index % len(inputs[index]["simulated_request_classes"])],
            "response_shape_status": "fixture_only_shape_validated" if response["read_only_shape_available"] else "write_execute_shape_blocked",
            "blocked_fields": response["forbidden_fields"],
            "reason_codes": response["reason_codes"],
            "dry_run_status": result["dry_run_status"],
            "safety_status": "paper_only_live_blocked_detector_not_run",
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


def validate_read_only_detector_dry_run() -> dict[str, Any]:
    manual_summary = _require_json(MANUAL_APPROVAL_PACKET_SUMMARY_PATH)
    approval_packet = _require_json(READ_ONLY_DETECTOR_APPROVAL_PACKET_PATH)
    if manual_summary.get("approval_status") != "approval_missing":
        raise ValueError("dry-run validator requires approval_status=approval_missing")
    if manual_summary.get("detector_approved_now") is not False:
        raise ValueError("dry-run validator requires detector_approved_now=false")
    if manual_summary.get("read_only_detector_run") is not False:
        raise ValueError("dry-run validator requires read_only_detector_run=false")

    inputs = build_dry_run_inputs(str(approval_packet["packet_id"]))
    responses = build_simulated_broker_capability_responses()
    read_only_shapes = read_only_shape_library()
    forbidden_shapes = forbidden_shape_library()
    _validate_inputs(inputs)
    _validate_responses(responses)
    results = build_dry_run_results(inputs, responses)
    _validate_results(results)
    boundary_blocks = build_dry_run_boundary_blocks()
    proof_records = build_dry_run_proof_records(inputs, responses, results)
    summary = build_dry_run_summary(inputs, responses, results, boundary_blocks, proof_records)

    _write_json(DRY_RUN_INPUTS_FIXTURE_PATH, _fixture_payload("read_only_detector_dry_run_inputs", inputs))
    _write_json(SIMULATED_RESPONSES_FIXTURE_PATH, _fixture_payload("simulated_broker_capability_responses", responses))
    _write_json(SIMULATED_READ_ONLY_SHAPES_FIXTURE_PATH, _fixture_payload("simulated_read_only_shapes", list(read_only_shapes.values())))
    _write_json(SIMULATED_FORBIDDEN_SHAPES_FIXTURE_PATH, _fixture_payload("simulated_forbidden_shapes", list(forbidden_shapes.values())))
    _write_json(EXPECTED_DRY_RUN_RESULTS_FIXTURE_PATH, _fixture_payload("expected_dry_run_results", results))

    _write_jsonl(DRY_RUN_INPUTS_PATH, inputs)
    _write_jsonl(SIMULATED_RESPONSES_PATH, responses)
    _write_json(SIMULATED_READ_ONLY_SHAPES_PATH, {"artifact_type": "simulated_read_only_shapes", "shape_count": len(read_only_shapes), "shapes": read_only_shapes, "paper_only": True, "live_blocked": True, "shape_hash": stable_hash(read_only_shapes)})
    _write_json(SIMULATED_FORBIDDEN_SHAPES_PATH, {"artifact_type": "simulated_forbidden_shapes", "shape_count": len(forbidden_shapes), "shapes": forbidden_shapes, "paper_only": True, "live_blocked": True, "shape_hash": stable_hash(forbidden_shapes)})
    _write_jsonl(DRY_RUN_RESULTS_PATH, results)
    _write_jsonl(DRY_RUN_BOUNDARY_BLOCKS_PATH, boundary_blocks)
    _write_text(FUTURE_DETECTOR_CONTRACT_PATH, render_future_detector_contract())
    _write_json(DRY_RUN_SUMMARY_PATH, summary)
    _write_jsonl(DRY_RUN_PROOF_PATH, proof_records)
    _write_text(DRY_RUN_REPORT_PATH, render_dry_run_report(summary))
    _write_text(DRY_RUN_LEDGER_PATH, render_dry_run_ledger())
    return {
        "dry_run_validator_status": "ok",
        "dry_run_status": summary["dry_run_status"],
        "approval_status": summary["approval_status"],
        "detector_approved": False,
        "detector_run_attempted": False,
        "broker_connection_attempted": False,
        "credential_access_attempted": False,
        "network_access_attempted": False,
        "live_order_attempted": False,
        "input_count": summary["input_count"],
        "simulated_response_count": summary["simulated_response_count"],
        "result_count": summary["result_count"],
        "boundary_block_count": summary["boundary_block_count"],
        "proof_record_count": summary["proof_record_count"],
        "next_required_gate": summary["next_required_gate"],
        "artifact_paths": dry_run_artifact_paths(),
        "report_paths": {
            "dry_run_report": str(DRY_RUN_REPORT_PATH),
            "dry_run_ledger": str(DRY_RUN_LEDGER_PATH),
        },
        "paper_only": True,
        "live_blocked": True,
    }


def build_dry_run_summary(
    inputs: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    results: list[dict[str, Any]],
    boundary_blocks: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {
        "artifact_type": "read_only_detector_dry_run_summary",
        "dry_run_validator_version": DRY_RUN_VALIDATOR_VERSION,
        "dry_run_status": "dry_run_fixture_validated",
        "approval_status": "approval_missing",
        "approval_present": False,
        "detector_approved": False,
        "detector_run_attempted": False,
        "broker_connection_attempted": False,
        "credential_access_attempted": False,
        "network_access_attempted": False,
        "live_order_attempted": False,
        "order_placement_blocked": True,
        "order_cancellation_blocked": True,
        "scheduler_blocked": True,
        "real_sizing_blocked": True,
        "input_count": len(inputs),
        "simulated_response_count": len(responses),
        "read_only_shape_count": sum(1 for response in responses if response["read_only_shape_available"] is True),
        "blocked_write_execute_shape_count": sum(1 for response in responses if response["write_or_execute_shape_blocked"] is True),
        "forbidden_field_count": len(FORBIDDEN_SHAPE_FIELDS),
        "result_count": len(results),
        "boundary_block_count": len(boundary_blocks),
        "proof_record_count": len(proof_records),
        "future_detector_contract_path": str(FUTURE_DETECTOR_CONTRACT_PATH),
        "next_required_gate": EXPLICIT_MANUAL_APPROVAL_GATE,
        "not_broker_ready": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credential": True,
        "no_live_order": True,
        "robinhood_mcp_integration_created": False,
        "read_only_detector_run": False,
        "full_suite_status": "inconclusive_timeout",
        "full_suite_timeout_recorded_as_pass": False,
    }
    return {**summary, "summary_hash": stable_hash({**summary, "summary_hash": ""})}


def audit_dry_run_detector_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    required_false = [
        "approval_present",
        "detector_approved",
        "detector_run_attempted",
        "broker_connection_attempted",
        "credential_access_attempted",
        "network_access_attempted",
        "live_order_attempted",
        "read_only_detector_run",
        "robinhood_mcp_integration_created",
    ]
    for field_name in required_false:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": f"dry_run_{field_name}_forbidden", "severity": "safety_error"})
    required_true = ["paper_only", "live_blocked", "order_placement_blocked", "order_cancellation_blocked", "scheduler_blocked", "real_sizing_blocked"]
    for field_name in required_true:
        if summary.get(field_name) is not True:
            findings.append({"check_id": f"dry_run_{field_name}_required", "severity": "safety_error"})
    if summary.get("approval_status") != "approval_missing":
        findings.append({"check_id": "dry_run_approval_missing_required", "severity": "safety_error"})
    if summary.get("dry_run_status") != "dry_run_fixture_validated":
        findings.append({"check_id": "dry_run_status_not_validated", "severity": "safety_error"})
    return findings


def render_future_detector_contract() -> str:
    allowed = [
        "read-only broker capability discovery",
        "read-only tool inventory discovery",
        "read-only schema/shape discovery",
        "read-only account metadata shape discovery",
        "read-only option chain shape discovery",
        "read-only option quote shape discovery",
        "read-only position shape discovery",
        "read-only order status shape discovery",
    ]
    forbidden = [
        "credential storage",
        "credential export",
        ".env creation",
        "live order review",
        "live order placement",
        "order cancellation",
        "broker write/execute",
        "real account sizing",
        "buying power use",
        "account balance dependency",
        "scheduler",
        "autonomous live loop",
        "real market-data scraping",
        "live trading enablement",
    ]
    lines = ["# DOPEY Future Read-Only Detector Contract", ""]
    lines.append("The approval packet is not approval. The detector dry-run validator is not the detector.")
    lines.append("Future approval must be exact, explicit, and limited to read-only broker capability detection only.")
    lines.append("Any scope expansion terminal-blocks.")
    lines.append("")
    lines.append("## Allowed Only After Explicit Approval")
    for item in allowed:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Still Forbidden After Approval")
    for item in forbidden:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append("- broker_connection_created: `false`")
    lines.append("- credentials_created: `false`")
    lines.append("- detector_run_in_this_bundle: `false`")
    return "\n".join(lines) + "\n"


def render_dry_run_report(summary: dict[str, Any]) -> str:
    lines = ["# DOPEY Read-Only Detector Dry-Run Fixture Validator Report", ""]
    lines.append("This bundle validates future detector fixture schemas only. It is not detector execution, broker integration, Robinhood MCP integration, credential setup, live trading, scheduling, real sizing, or market-data access.")
    lines.append("")
    lines.append("## Summary")
    for key in ["dry_run_status", "approval_status", "detector_approved", "detector_run_attempted", "input_count", "simulated_response_count", "read_only_shape_count", "blocked_write_execute_shape_count", "boundary_block_count", "proof_record_count", "next_required_gate"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("## Safety State")
    for key in ["paper_only", "live_blocked", "no_real_market_data", "no_broker", "no_real_sizing", "no_scheduler", "no_credential", "no_live_order"]:
        lines.append(f"- {key}: `{str(summary.get(key)).lower()}`")
    lines.append("")
    lines.append("## Limitations")
    lines.append("- No broker capability, live readiness, profitability, predictive power, or market accuracy is claimed.")
    lines.append("- Full suite timeout remains `inconclusive_timeout`, not pass.")
    lines.append("- Future detector approval remains missing.")
    approval_intake_summary = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "approval_intake" / "approval_intake_summary.json"
    if approval_intake_summary.exists():
        lines.append("")
        lines.append("## Approval Intake Validator")
        lines.append("- Approval-intake validator exists as an offline fixture-only text validator.")
        lines.append("- Dry-run remains not detector execution.")
    return "\n".join(lines) + "\n"


def render_dry_run_ledger() -> str:
    lines = ["# DOPEY Read-Only Detector Dry-Run Artifact Ledger", ""]
    for artifact_type, artifact_path in dry_run_artifact_paths().items():
        path = Path(artifact_path)
        lines.append(f"- artifact_type: `{artifact_type}`")
        lines.append(f"  path: `{path}`")
        lines.append(f"  hash: `{_file_hash(path) if path.exists() else ''}`")
        lines.append(f"  record_count: `{_record_count(path) if path.exists() else 0}`")
        lines.append("  safety_state: `paper_only_live_blocked_fixture_only_detector_not_run`")
    return "\n".join(lines) + "\n"


def _attempt_flags(case_group: str, index: int) -> dict[str, bool]:
    return {
        "detector_run_attempted": case_group == "incident_escalation" and index % 5 == 0,
        "broker_connection_attempted": case_group == "incident_escalation" and index % 5 == 1,
        "credential_access_attempted": case_group in {"credential_scheduler_network_block", "incident_escalation"} and index % 5 == 2,
        "network_access_attempted": case_group in {"credential_scheduler_network_block", "incident_escalation"} and index % 5 == 3,
        "live_order_attempted": case_group in {"write_execute_block", "incident_escalation"} and index % 5 == 4,
    }


def _status_for_attempts(attempted: dict[str, bool], case_group: str) -> str:
    if attempted["detector_run_attempted"]:
        return "blocked_detector_run_attempt"
    if attempted["broker_connection_attempted"]:
        return "blocked_broker_connection_attempt"
    if attempted["credential_access_attempted"] or attempted["network_access_attempted"]:
        return "blocked_credential_attempt"
    if attempted["live_order_attempted"]:
        return "blocked_live_execution_attempt"
    if case_group == "schema_violation":
        return "blocked_schema_violation"
    if case_group == "approval_missing_detector_not_run":
        return "approval_missing_detector_not_run"
    return "dry_run_fixture_validated"


def _validate_inputs(records: list[dict[str, Any]]) -> None:
    for record in records:
        ReadOnlyDetectorDryRunInput.from_dict({k: v for k, v in record.items() if k != "case_group"})


def _validate_responses(records: list[dict[str, Any]]) -> None:
    for record in records:
        SimulatedBrokerCapabilityResponse.from_dict(record)


def _validate_results(records: list[dict[str, Any]]) -> None:
    for record in records:
        ReadOnlyDetectorDryRunResult.from_dict({k: v for k, v in record.items() if k != "case_group"})


def _fixture_payload(artifact_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"artifact_type": artifact_type, "case_count": len(records), "records": records, "paper_only": True, "live_blocked": True}
    return {**payload, "fixture_hash": stable_hash(payload)}


def _require_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required dry-run source artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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
        return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    return 1
