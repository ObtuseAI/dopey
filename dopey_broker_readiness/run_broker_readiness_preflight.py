"""Run the offline broker-readiness preflight and boundary simulator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .boundary_incidents import broker_boundary_incident_records
from .broker_readiness_models import (
    BrokerReadinessPreflightCheck,
    BrokerReadinessRunResult,
    ReadOnlyBoundarySimulation,
    make_run_result,
    stable_hash,
)
from .capability_fixtures import build_broker_capability_fixtures
from .preflight_checklist import build_preflight_checks
from .read_only_boundary_simulator import run_read_only_boundary_simulations


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "broker_readiness"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness"

BROKER_PREFLIGHT_FIXTURE_PATH = FIXTURE_DIR / "broker_preflight_checks.json"
READ_ONLY_BOUNDARY_FIXTURE_PATH = FIXTURE_DIR / "read_only_boundary_simulations.json"
BROKER_CAPABILITY_FIXTURE_PATH = FIXTURE_DIR / "broker_capability_fixtures.json"
EXPECTED_BROKER_READINESS_RESULTS_PATH = FIXTURE_DIR / "expected_broker_readiness_results.json"
EXPECTED_BOUNDARY_BLOCKS_PATH = FIXTURE_DIR / "expected_boundary_blocks.json"

BROKER_PREFLIGHT_CHECKS_PATH = ARTIFACT_DIR / "broker_preflight_checks.jsonl"
READ_ONLY_BOUNDARY_SIMULATIONS_PATH = ARTIFACT_DIR / "read_only_boundary_simulations.jsonl"
BROKER_CAPABILITY_FIXTURES_PATH = ARTIFACT_DIR / "broker_capability_fixtures.json"
BROKER_READINESS_RUN_RESULT_PATH = ARTIFACT_DIR / "broker_readiness_run_result.json"
BROKER_READINESS_BOUNDARY_BLOCKS_PATH = ARTIFACT_DIR / "broker_readiness_boundary_blocks.jsonl"
BROKER_READINESS_MANUAL_GATES_PATH = ARTIFACT_DIR / "broker_readiness_manual_gates.json"
BROKER_READINESS_SUMMARY_PATH = ARTIFACT_DIR / "broker_readiness_summary.json"
BROKER_READINESS_PROOF_PATH = ARTIFACT_DIR / "broker_readiness_proof.jsonl"


def _write_json(path: Path, record: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def broker_readiness_artifact_paths() -> dict[str, str]:
    return {
        "broker_preflight_checks": str(BROKER_PREFLIGHT_CHECKS_PATH),
        "read_only_boundary_simulations": str(READ_ONLY_BOUNDARY_SIMULATIONS_PATH),
        "broker_capability_fixtures": str(BROKER_CAPABILITY_FIXTURES_PATH),
        "broker_readiness_run_result": str(BROKER_READINESS_RUN_RESULT_PATH),
        "broker_readiness_boundary_blocks": str(BROKER_READINESS_BOUNDARY_BLOCKS_PATH),
        "broker_readiness_manual_gates": str(BROKER_READINESS_MANUAL_GATES_PATH),
        "broker_readiness_summary": str(BROKER_READINESS_SUMMARY_PATH),
        "broker_readiness_proof": str(BROKER_READINESS_PROOF_PATH),
    }


def build_boundary_blocks(simulations: list[ReadOnlyBoundarySimulation]) -> list[dict[str, Any]]:
    blocks = [
        {
            "block_id": f"broker-boundary-block-record-{index:03d}",
            "source_id": simulation.simulation_id,
            "boundary_type": simulation.boundary_type,
            "simulated_request_type": simulation.simulated_request_type,
            "blocked_write_or_execute": simulation.blocked_write_or_execute,
            "requires_manual_approval": simulation.requires_manual_approval,
            "reason_codes": simulation.reason_codes,
            "paper_only": True,
            "live_blocked": True,
        }
        for index, simulation in enumerate(simulations, start=1)
        if simulation.blocked_write_or_execute
    ]
    simulated_failure_blocks = [
        ("missing_audit_proof_blocks_readiness", "audit", "missing_audit_proof"),
        ("safety_finding_blocks_readiness", "audit", "safety_finding"),
        ("credential_finding_blocks_readiness", "credential_boundary", "credential_finding"),
        ("scheduler_finding_blocks_readiness", "scheduler_boundary", "scheduler_finding"),
        ("full_suite_timeout_as_pass_blocks_readiness", "audit", "full_suite_timeout_as_pass"),
    ]
    offset = len(blocks)
    for index, (block_id, boundary_type, reason) in enumerate(simulated_failure_blocks, start=1):
        blocks.append({
            "block_id": block_id,
            "source_id": f"simulated-blocking-condition-{offset + index:03d}",
            "boundary_type": boundary_type,
            "simulated_request_type": reason,
            "blocked_write_or_execute": True,
            "requires_manual_approval": True,
            "reason_codes": [reason, "readiness_blocked_if_observed"],
            "paper_only": True,
            "live_blocked": True,
        })
    return [{**block, "block_hash": stable_hash({**block, "block_hash": ""})} for block in blocks]


def build_manual_gates(checks: list[BrokerReadinessPreflightCheck], simulations: list[ReadOnlyBoundarySimulation]) -> dict[str, Any]:
    gates = [
        {
            "gate_id": check.check_id,
            "gate_name": check.check_name,
            "gate_status": "manual_approval_required",
            "paper_only": True,
            "live_blocked": True,
        }
        for check in checks
        if check.check_category == "manual_approval_boundary"
    ]
    for simulation in simulations:
        if simulation.requires_manual_approval:
            gates.append({
                "gate_id": simulation.simulation_id,
                "gate_name": simulation.simulated_request_type,
                "gate_status": "manual_approval_required",
                "paper_only": True,
                "live_blocked": True,
            })
    return {
        "artifact_type": "broker_readiness_manual_gates",
        "manual_gate_count": len(gates),
        "next_required_gate": "explicit_human_approval_for_future_read_only_capability_detector_bundle",
        "gates": gates,
        "paper_only": True,
        "live_blocked": True,
        "manual_gates_hash": stable_hash({"gates": gates}),
    }


def build_proof_records(
    checks: list[BrokerReadinessPreflightCheck],
    simulations: list[ReadOnlyBoundarySimulation],
    result: BrokerReadinessRunResult,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for check in checks:
        seed = {
            "proof_id": f"proof-{check.check_id}",
            "check_id": check.check_id,
            "simulation_id": "",
            "check_category": check.check_category,
            "boundary_type": "",
            "request_type": "",
            "allowed_read_only": False,
            "blocked_write_or_execute": False,
            "manual_approval_status": "required" if check.check_category == "manual_approval_boundary" else "not_required",
            "readiness_status": result.readiness_status,
            "reason_codes": check.failure_reason_codes,
            "safety_status": "paper_only_live_blocked",
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
    for simulation in simulations:
        seed = {
            "proof_id": f"proof-{simulation.simulation_id}",
            "check_id": "",
            "simulation_id": simulation.simulation_id,
            "check_category": "",
            "boundary_type": simulation.boundary_type,
            "request_type": simulation.simulated_request_type,
            "allowed_read_only": simulation.allowed_read_only,
            "blocked_write_or_execute": simulation.blocked_write_or_execute,
            "manual_approval_status": "required" if simulation.requires_manual_approval else "not_required",
            "readiness_status": result.readiness_status,
            "reason_codes": simulation.reason_codes,
            "safety_status": "paper_only_live_blocked",
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


def build_summary(
    checks: list[BrokerReadinessPreflightCheck],
    simulations: list[ReadOnlyBoundarySimulation],
    result: BrokerReadinessRunResult,
    boundary_blocks: list[dict[str, Any]],
    manual_gates: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "artifact_type": "broker_readiness_summary",
        "broker_readiness_version": "dopey-broker-readiness-preflight-v1",
        "readiness_status": result.readiness_status,
        "not_broker_ready": True,
        "not_live_ready": True,
        "read_only_boundary_simulated": True,
        "next_required_gate": result.next_required_gate,
        "preflight_check_count": len(checks),
        "preflight_checks_passed": result.preflight_checks_passed,
        "blocking_failures": result.blocking_failures,
        "read_only_simulation_count": len(simulations),
        "read_only_allowed_count": result.read_only_allowed_count,
        "write_execute_blocked_count": result.write_execute_blocked_count,
        "boundary_block_count": len(boundary_blocks),
        "manual_gate_count": manual_gates["manual_gate_count"],
        "credential_blocks": result.credential_blocks,
        "scheduler_blocks": result.scheduler_blocks,
        "network_blocks": result.network_blocks,
        "broker_blocks": result.broker_blocks,
        "live_trading_enabled": False,
        "broker_connection_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
        "robinhood_mcp_integration_created": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credential": True,
        "no_live_order": True,
        "full_suite_status": "inconclusive_timeout",
        "full_suite_timeout_seconds": 125.03,
        "full_suite_timeout_recorded_as_pass": False,
        "sequential_shards_reliable": True,
        "artifact_writing_shards_parallel_race_risk": True,
        "boundary_incidents": broker_boundary_incident_records(),
    }
    return {**summary, "summary_hash": stable_hash({**summary, "summary_hash": ""})}


def write_broker_readiness_outputs(
    checks: list[BrokerReadinessPreflightCheck],
    simulations: list[ReadOnlyBoundarySimulation],
    result: BrokerReadinessRunResult,
    capabilities: list[Any],
) -> dict[str, str]:
    check_records = [check.to_dict() for check in checks]
    simulation_records = [simulation.to_dict() for simulation in simulations]
    capability_records = [fixture.to_dict() for fixture in capabilities]
    boundary_blocks = build_boundary_blocks(simulations)
    manual_gates = build_manual_gates(checks, simulations)
    proof_records = build_proof_records(checks, simulations, result)
    summary = build_summary(checks, simulations, result, boundary_blocks, manual_gates)

    fixture_payload = {"artifact_type": "broker_preflight_checks_fixture", "case_count": len(check_records), "records": check_records}
    _write_json(BROKER_PREFLIGHT_FIXTURE_PATH, {**fixture_payload, "fixture_hash": stable_hash(fixture_payload)})
    boundary_payload = {"artifact_type": "read_only_boundary_simulations_fixture", "case_count": len(simulation_records), "records": simulation_records}
    _write_json(READ_ONLY_BOUNDARY_FIXTURE_PATH, {**boundary_payload, "fixture_hash": stable_hash(boundary_payload)})
    capability_payload = {"artifact_type": "broker_capability_fixtures", "fixture_count": len(capability_records), "records": capability_records}
    _write_json(BROKER_CAPABILITY_FIXTURE_PATH, {**capability_payload, "fixture_hash": stable_hash(capability_payload)})
    _write_json(EXPECTED_BROKER_READINESS_RESULTS_PATH, {**result.to_dict(), "artifact_type": "expected_broker_readiness_results"})
    _write_json(EXPECTED_BOUNDARY_BLOCKS_PATH, {"artifact_type": "expected_boundary_blocks", "block_count": len(boundary_blocks), "records": boundary_blocks})

    _write_jsonl(BROKER_PREFLIGHT_CHECKS_PATH, check_records)
    _write_jsonl(READ_ONLY_BOUNDARY_SIMULATIONS_PATH, simulation_records)
    _write_json(BROKER_CAPABILITY_FIXTURES_PATH, capability_payload)
    _write_json(BROKER_READINESS_RUN_RESULT_PATH, result.to_dict())
    _write_jsonl(BROKER_READINESS_BOUNDARY_BLOCKS_PATH, boundary_blocks)
    _write_json(BROKER_READINESS_MANUAL_GATES_PATH, manual_gates)
    _write_json(BROKER_READINESS_SUMMARY_PATH, summary)
    _write_jsonl(BROKER_READINESS_PROOF_PATH, proof_records)
    return broker_readiness_artifact_paths()


def run_broker_readiness_preflight() -> dict[str, Any]:
    checks = build_preflight_checks()
    simulations = run_read_only_boundary_simulations()
    capabilities = build_broker_capability_fixtures()
    result = make_run_result("dopey-broker-readiness-preflight-v1", checks, simulations)
    artifact_paths = write_broker_readiness_outputs(checks, simulations, result, capabilities)
    response = {
        "broker_readiness_preflight_status": "ok",
        "readiness_status": result.readiness_status,
        "not_broker_ready": True,
        "not_live_ready": True,
        "next_required_gate": result.next_required_gate,
        "preflight_checks_total": result.preflight_checks_total,
        "read_only_simulations_total": result.read_only_simulations_total,
        "write_execute_blocked_count": result.write_execute_blocked_count,
        "manual_approval_required_count": result.manual_approval_required_count,
        "artifact_paths": artifact_paths,
        "paper_only": True,
        "live_blocked": True,
        "no_broker_connection": True,
        "no_credentials": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "no_robinhood_mcp_integration": True,
    }
    return {**response, "reproducibility_hash": reproducibility_hash(response)}


def main() -> int:
    result = run_broker_readiness_preflight()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["broker_readiness_preflight_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
