from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_broker_readiness.audit import audit_broker_readiness_summary
from dopey_broker_readiness.boundary_incidents import broker_boundary_incident_records
from dopey_broker_readiness.broker_readiness_models import (
    BrokerCapabilityFixture,
    BrokerReadinessPreflightCheck,
    BrokerReadinessRunResult,
    ReadOnlyBoundarySimulation,
    boundary_simulation_hash,
    capability_fixture_hash,
    make_capability_fixture,
    make_preflight_check,
    make_run_result,
    preflight_check_hash,
    run_result_hash,
)
from dopey_broker_readiness.run_broker_readiness_preflight import (
    BROKER_CAPABILITY_FIXTURE_PATH,
    BROKER_CAPABILITY_FIXTURES_PATH,
    BROKER_PREFLIGHT_CHECKS_PATH,
    BROKER_PREFLIGHT_FIXTURE_PATH,
    BROKER_READINESS_BOUNDARY_BLOCKS_PATH,
    BROKER_READINESS_MANUAL_GATES_PATH,
    BROKER_READINESS_PROOF_PATH,
    BROKER_READINESS_RUN_RESULT_PATH,
    BROKER_READINESS_SUMMARY_PATH,
    EXPECTED_BOUNDARY_BLOCKS_PATH,
    EXPECTED_BROKER_READINESS_RESULTS_PATH,
    READ_ONLY_BOUNDARY_FIXTURE_PATH,
    READ_ONLY_BOUNDARY_SIMULATIONS_PATH,
    run_broker_readiness_preflight,
)
from dopey_broker_readiness.read_only_boundary_simulator import run_read_only_boundary_simulations
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_export_review.review_models import ExportReviewBundle, ExportReviewDecision
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _broker_readiness_summary
from dopey_validation.full_suite_stabilizer import CommandResult, write_test_shard_plan


def _materialize_missing_preflight_evidence() -> list[str]:
    """The preflight OBSERVES other lanes' proof artifacts; it must never
    create its own evidence (that stays true in production). Under the
    isolated test mirror those artifacts only exist if their producing lanes
    ran earlier in the session, which depends on suite order - several
    producers sort alphabetically AFTER this file. Materialize any missing
    evidence through the REAL producing runners (never by faking files) so
    the preflight aggregate is testable order-independently. Existence-gated:
    in full-suite order most artifacts already exist and the runner is
    skipped."""
    from dopey_broker_readiness.preflight_checklist import ARTIFACT_ROOT as PREFLIGHT_ARTIFACT_ROOT

    ran: list[str] = []

    def _missing(*relatives: str) -> bool:
        return any(not (PREFLIGHT_ARTIFACT_ROOT / relative).exists() for relative in relatives)

    if _missing("account_ledger/paper_account_ledger.json", "account_ledger/day_trade_event_log.jsonl",
                "account_ledger/rotation_plan.json", "account_ledger/rotation_planner_proof.jsonl",
                "account_ledger/zero_dte_account_lifecycle_proof.jsonl"):
        from dopey_execution.run_account_ledger_rotation_planner import run_account_ledger_rotation_planner
        run_account_ledger_rotation_planner()
        ran.append("account_ledger_rotation_planner")
    if _missing("lifecycle/lifecycle_summary.json", "lifecycle/lifecycle_proof.jsonl",
                "lifecycle/lifecycle_paperbroker_results.jsonl", "lifecycle/lifecycle_states.jsonl"):
        from dopey_lifecycle.run_active_option_lifecycle_simulator import run_active_option_lifecycle_simulator
        run_active_option_lifecycle_simulator()
        ran.append("lifecycle_simulator")
    if _missing("audit/active_policy_audit.jsonl", "audit/evidence_gap_plan.jsonl",
                "zero_dte_risk/zero_dte_risk_summary.json", "governor/active_policy_order_validation_proof.jsonl"):
        from dopey_audit.active_policy_audit import run_active_policy_audit
        run_active_policy_audit()
        ran.append("active_policy_audit")
    if _missing("audit/evidence_replay_audit_proof.jsonl"):
        from dopey_audit.audit_runner import run_offline_evidence_replay_audit
        run_offline_evidence_replay_audit()
        ran.append("evidence_replay_audit")
    if _missing("allocation/paper_allocation_plan.json", "allocation/allocation_constraint_summary.json"):
        from dopey_allocation.run_proof_weighted_allocator import run_proof_weighted_allocator
        run_proof_weighted_allocator()
        ran.append("proof_weighted_allocator")
    if _missing("portfolio_replay/portfolio_replay_summary.json", "portfolio_replay/portfolio_exposure_snapshots.jsonl",
                "portfolio_replay/portfolio_allocator_feedback.jsonl"):
        from dopey_portfolio.run_portfolio_replay import run_portfolio_replay
        run_portfolio_replay()
        ran.append("portfolio_replay")
    if _missing("portfolio_stress_ladder/stress_ladder_summary.json", "portfolio_stress_ladder/crisis_throttle_results.jsonl",
                "portfolio_stress_ladder/crisis_allocator_feedback.jsonl", "portfolio_stress_ladder/stress_transition_decisions.jsonl"):
        from dopey_portfolio.run_portfolio_stress_ladder import run_portfolio_stress_ladder
        run_portfolio_stress_ladder()
        ran.append("portfolio_stress_ladder")
    if _missing("incident_response/incident_rehearsal_summary.json", "incident_response/incident_response_decisions.jsonl",
                "incident_response/incident_recovery_plans.jsonl"):
        from dopey_incident.run_incident_response_rehearsal import run_incident_response_rehearsal
        run_incident_response_rehearsal()
        ran.append("incident_response_rehearsal")
    if _missing("exports/export_safety_scan.jsonl"):
        from dopey_export.export_verifier import run_default_artifact_compaction_export_verifier
        run_default_artifact_compaction_export_verifier()
        ran.append("export_verifier")
    if _missing("export_reviews/export_review_proof.jsonl"):
        from dopey_export_review.review_runner import run_export_bundle_review_assistant
        run_export_bundle_review_assistant()
        ran.append("export_review_assistant")
    if _missing("validation/full_suite_stabilizer_summary.json"):
        # The stabilizer's real runner executes pytest itself (recursive under
        # a test session), so this one artifact is materialized directly with
        # a self-declaring honest record - timeout stays inconclusive, never a
        # pass.
        target = PREFLIGHT_ARTIFACT_ROOT / "validation" / "full_suite_stabilizer_summary.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "artifact_type": "full_suite_stabilizer_summary",
            "collection": {"status": "not_run_by_this_fixture"},
            "full_suite": {"status": "inconclusive_timeout", "timeout_recorded_as_pass": False},
            "materialized_by": "broker_readiness_preflight_test_fixture_isolated_mirror",
        }, sort_keys=True) + "\n", encoding="utf-8")
        ran.append("stabilizer_summary_placeholder")
    return ran


@pytest.fixture(scope="session")
def broker_result() -> dict[str, Any]:
    _materialize_missing_preflight_evidence()
    return run_broker_readiness_preflight()


@pytest.fixture(scope="session")
def broker_bundle(broker_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "result": broker_result,
        "checks": _jsonl(BROKER_PREFLIGHT_CHECKS_PATH),
        "simulations": _jsonl(READ_ONLY_BOUNDARY_SIMULATIONS_PATH),
        "capabilities": _json(BROKER_CAPABILITY_FIXTURES_PATH)["records"],
        "run_result": _json(BROKER_READINESS_RUN_RESULT_PATH),
        "blocks": _jsonl(BROKER_READINESS_BOUNDARY_BLOCKS_PATH),
        "manual_gates": _json(BROKER_READINESS_MANUAL_GATES_PATH),
        "summary": _json(BROKER_READINESS_SUMMARY_PATH),
        "proof": _jsonl(BROKER_READINESS_PROOF_PATH),
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _check(bundle: dict[str, Any], name: str) -> dict[str, Any]:
    return next(record for record in bundle["checks"] if record["check_name"] == name)


def _simulation(bundle: dict[str, Any], request_type: str) -> dict[str, Any]:
    return next(record for record in bundle["simulations"] if record["simulated_request_type"] == request_type)


def _fixture(bundle: dict[str, Any], capability_name: str) -> dict[str, Any]:
    return next(record for record in bundle["capabilities"] if record["capability_name"] == capability_name)


def _sample_check() -> BrokerReadinessPreflightCheck:
    return make_preflight_check("check", "active_policy", "long_call_policy_check", "pass", ["artifact"], [], True)


def _sample_simulation() -> ReadOnlyBoundarySimulation:
    return run_read_only_boundary_simulations()[0]


def _sample_fixture() -> BrokerCapabilityFixture:
    return make_capability_fixture("fixture", "SIMULATED_BROKER_GENERIC_OPTIONS", "orders", "place_option_order", False, False, True, False, True, True, ["blocked"])


def _sample_run_result() -> BrokerReadinessRunResult:
    return make_run_result("run", [_sample_check()], [_sample_simulation()])


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(intent_id="live", symbol="DLP1", structure="long_call", legs=[{"side": "buy", "option_type": "call", "expiry": "2026-07-17", "dte": 5}], max_loss=1.0, live_allowed=True, active_policy_required=True)


def test_broker_readiness_preflight_check_serializes_deterministically() -> None:
    check = _sample_check()
    assert BrokerReadinessPreflightCheck.from_dict(check.to_dict()).to_dict() == check.to_dict()


def test_read_only_boundary_simulation_serializes_deterministically() -> None:
    simulation = _sample_simulation()
    assert ReadOnlyBoundarySimulation.from_dict(simulation.to_dict()).to_dict() == simulation.to_dict()


def test_broker_capability_fixture_serializes_deterministically() -> None:
    fixture = _sample_fixture()
    assert BrokerCapabilityFixture.from_dict(fixture.to_dict()).to_dict() == fixture.to_dict()


def test_broker_readiness_run_result_serializes_deterministically() -> None:
    result = _sample_run_result()
    assert BrokerReadinessRunResult.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_broker_readiness_hashes_are_deterministic() -> None:
    assert preflight_check_hash(BrokerReadinessPreflightCheck.from_dict({**_sample_check().to_dict(), "check_hash": ""})) == _sample_check().check_hash
    assert boundary_simulation_hash(ReadOnlyBoundarySimulation.from_dict({**_sample_simulation().to_dict(), "simulation_hash": ""})) == _sample_simulation().simulation_hash
    assert capability_fixture_hash(BrokerCapabilityFixture.from_dict({**_sample_fixture().to_dict(), "fixture_hash": ""})) == _sample_fixture().fixture_hash
    assert run_result_hash(BrokerReadinessRunResult.from_dict({**_sample_run_result().to_dict(), "run_hash": ""})) == _sample_run_result().run_hash


def test_broker_readiness_requires_paper_only_live_blocked() -> None:
    payload = {**_sample_check().to_dict(), "paper_only": False, "check_hash": ""}
    with pytest.raises(ValueError):
        BrokerReadinessPreflightCheck.from_dict(payload)


def test_broker_capability_fixture_rejects_real_broker_connection() -> None:
    payload = {**_sample_fixture().to_dict(), "broker_name": "ROBINHOOD"}
    with pytest.raises(ValueError):
        BrokerCapabilityFixture.from_dict(payload)


def test_preflight_checklist_loads(broker_bundle: dict[str, Any]) -> None:
    assert len(broker_bundle["checks"]) >= 76


def test_preflight_confirms_long_call_policy(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "long_call_policy_check")["passed"]


def test_preflight_confirms_long_put_policy(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "long_put_policy_check")["passed"]


def test_preflight_confirms_sell_to_open_block(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "sell_to_open_block_check")["passed"]


def test_preflight_confirms_same_day_close_block(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "same_day_normal_close_blocked_check")["passed"]


def test_preflight_confirms_zero_dte_special_lifecycle(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "zero_dte_special_lifecycle_check")["passed"]


def test_preflight_confirms_lifecycle_proof_exists(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "lifecycle_proof_exists_check")["passed"]


def test_preflight_confirms_paperbroker_authority(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "paperbroker_cannot_be_overridden_check")["passed"]


def test_preflight_confirms_account_ledger_authority(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "account_ledger_mismatch_manual_review_check")["passed"]


def test_preflight_confirms_incident_terminal_block(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "terminal_block_works_check")["passed"]


def test_preflight_confirms_export_safety_scan(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "export_safety_scan_check")["passed"]


def test_preflight_confirms_credentials_absent(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "credentials_absent_check")["passed"]


def test_preflight_confirms_scheduler_absent(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "scheduler_absent_check")["passed"]


def test_preflight_confirms_broker_connection_absent(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "broker_connection_absent_check")["passed"]


def test_preflight_confirms_real_sizing_absent(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "real_sizing_absent_check")["passed"]


def test_preflight_requires_manual_approval_for_read_only_detector(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "read_only_detector_not_yet_approved_check")["check_category"] == "manual_approval_boundary"


def test_read_only_boundary_simulator_runs_all_cases(broker_bundle: dict[str, Any]) -> None:
    assert len(broker_bundle["simulations"]) >= 23


def test_simulated_capability_discovery_read_only_allowed(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "discover_broker_capabilities")["allowed_read_only"]


def test_simulated_option_chain_read_only_allowed(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "read_option_chain")["allowed_read_only"]


def test_simulated_quote_read_only_allowed(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "read_option_quote")["allowed_read_only"]


def test_simulated_position_read_only_allowed(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "read_option_position")["allowed_read_only"]


def test_simulated_order_status_read_only_allowed(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "read_order_status")["allowed_read_only"]


def test_simulated_order_review_fixture_only(broker_bundle: dict[str, Any]) -> None:
    record = _simulation(broker_bundle, "review_option_order_simulated")
    assert record["allowed_read_only"] and "fixture_only_not_broker_review" in record["reason_codes"]


def test_place_option_order_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "place_option_order_blocked")["blocked_write_or_execute"]


def test_cancel_order_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "cancel_order_blocked")["blocked_write_or_execute"]


def test_credential_request_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "request_credentials_blocked")["blocked_write_or_execute"]


def test_env_read_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "read_env_blocked")["blocked_write_or_execute"]


def test_scheduler_creation_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "create_scheduler_blocked")["blocked_write_or_execute"]


def test_network_market_data_request_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "network_market_data_blocked")["blocked_write_or_execute"]


def test_live_execution_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "live_execution_blocked")["blocked_write_or_execute"]


def test_robinhood_path_before_approval_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "robinhood_path_before_approval_blocked")["requires_manual_approval"]


def test_broker_integration_before_approval_blocked(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "broker_integration_before_approval_blocked")["requires_manual_approval"]


def test_broker_preflight_checks_fixture_loads(broker_bundle: dict[str, Any]) -> None:
    assert _json(BROKER_PREFLIGHT_FIXTURE_PATH)["case_count"] == len(broker_bundle["checks"])


def test_read_only_boundary_simulations_fixture_loads(broker_bundle: dict[str, Any]) -> None:
    assert _json(READ_ONLY_BOUNDARY_FIXTURE_PATH)["case_count"] == len(broker_bundle["simulations"])


def test_broker_capability_fixtures_load(broker_bundle: dict[str, Any]) -> None:
    assert _json(BROKER_CAPABILITY_FIXTURE_PATH)["fixture_count"] == len(broker_bundle["capabilities"])


def test_expected_broker_readiness_results_load() -> None:
    assert _json(EXPECTED_BROKER_READINESS_RESULTS_PATH)["readiness_status"] == "read_only_boundary_simulated"


def test_expected_boundary_blocks_load() -> None:
    assert _json(EXPECTED_BOUNDARY_BLOCKS_PATH)["block_count"] >= 21


def test_broker_readiness_has_at_least_96_cases(broker_bundle: dict[str, Any]) -> None:
    assert len(broker_bundle["checks"]) + len(broker_bundle["simulations"]) + len(broker_bundle["capabilities"]) >= 96


def test_broker_readiness_covers_active_policy_checks(broker_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in broker_bundle["checks"] if record["check_category"] == "active_policy") >= 16


def test_broker_readiness_covers_lifecycle_checks(broker_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in broker_bundle["checks"] if record["check_category"] in {"lifecycle", "account_ledger", "paperbroker", "no_day_trade"}) >= 16


def test_broker_readiness_covers_portfolio_stress_incident_checks(broker_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in broker_bundle["checks"] if record["check_category"] in {"allocation", "portfolio", "stress_ladder", "incident_response"}) >= 16


def test_broker_readiness_covers_read_only_simulations(broker_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in broker_bundle["simulations"] if record["allowed_read_only"]) >= 7


def test_broker_readiness_covers_write_execute_blocks(broker_bundle: dict[str, Any]) -> None:
    assert sum(1 for record in broker_bundle["simulations"] if record["blocked_write_or_execute"]) >= 16


def test_broker_readiness_covers_credential_scheduler_network_blocks(broker_bundle: dict[str, Any]) -> None:
    blocks = [record for record in broker_bundle["simulations"] if record["boundary_type"] in {"credential_request_blocked", "scheduler_request_blocked", "network_request_blocked"}]
    assert len(blocks) >= 8


def test_broker_readiness_covers_manual_approval_gates(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["manual_gates"]["manual_gate_count"] >= 8


def _incident(incident_type: str) -> dict[str, Any]:
    return next(record for record in broker_boundary_incident_records() if record["incident_type"] == incident_type)


def test_broker_capability_detector_attempt_before_approval_terminal_blocks() -> None:
    assert _incident("broker_capability_detector_attempt_before_approval")["kill_switch_state"] == "terminal_block"


def test_robinhood_integration_attempt_terminal_blocks() -> None:
    assert _incident("robinhood_integration_attempt")["response_decision"] == "terminal_block"


def test_credential_request_terminal_blocks() -> None:
    assert _incident("credential_request")["kill_switch_state"] == "terminal_block"


def test_env_access_terminal_blocks() -> None:
    assert _incident("env_access")["auto_recovery_allowed"] is False


def test_scheduler_creation_terminal_blocks() -> None:
    assert _incident("scheduler_creation")["kill_switch_state"] == "terminal_block"


def test_network_market_data_dependency_terminal_blocks() -> None:
    assert _incident("network_market_data_dependency")["response_decision"] == "terminal_block"


def test_live_order_review_against_broker_terminal_blocks() -> None:
    assert _incident("broker_order_review_attempt")["kill_switch_state"] == "terminal_block"


def test_live_order_placement_terminal_blocks() -> None:
    assert _incident("broker_order_placement_attempt")["response_decision"] == "terminal_block"


def test_real_account_balance_read_terminal_blocks() -> None:
    assert _incident("real_account_balance_read")["kill_switch_state"] == "terminal_block"


def test_buying_power_read_terminal_blocks() -> None:
    assert _incident("buying_power_read")["response_decision"] == "terminal_block"


def test_real_sizing_logic_terminal_blocks() -> None:
    assert _incident("real_sizing_logic")["auto_recovery_allowed"] is False


def test_broker_readiness_run_result_written(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["run_result"]["run_id"] == "dopey-broker-readiness-preflight-v1"


def test_broker_readiness_status_not_live_ready(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["not_live_ready"] is True


def test_broker_readiness_status_read_only_boundary_simulated(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["run_result"]["readiness_status"] == "read_only_boundary_simulated"


def test_broker_readiness_next_gate_is_manual_approval(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["run_result"]["next_required_gate"] == "explicit_human_approval_for_future_read_only_capability_detector_bundle"


def test_broker_readiness_blocks_write_execute(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["run_result"]["write_execute_blocked_count"] >= 16


def test_broker_readiness_blocks_credentials(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["run_result"]["credential_blocks"] >= 3


def test_broker_readiness_blocks_scheduler(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["run_result"]["scheduler_blocks"] >= 2


def test_broker_readiness_blocks_network(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["run_result"]["network_blocks"] >= 2


def test_broker_readiness_blocks_live_execution(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "live_execution_blocked")["blocked_write_or_execute"]


def test_broker_preflight_checks_artifact_written() -> None:
    assert BROKER_PREFLIGHT_CHECKS_PATH.exists()


def test_read_only_boundary_simulations_artifact_written() -> None:
    assert READ_ONLY_BOUNDARY_SIMULATIONS_PATH.exists()


def test_broker_capability_fixtures_artifact_written() -> None:
    assert BROKER_CAPABILITY_FIXTURES_PATH.exists()


def test_broker_readiness_run_result_artifact_written() -> None:
    assert BROKER_READINESS_RUN_RESULT_PATH.exists()


def test_broker_readiness_boundary_blocks_artifact_written() -> None:
    assert BROKER_READINESS_BOUNDARY_BLOCKS_PATH.exists()


def test_broker_readiness_manual_gates_artifact_written() -> None:
    assert BROKER_READINESS_MANUAL_GATES_PATH.exists()


def test_broker_readiness_summary_artifact_written() -> None:
    assert BROKER_READINESS_SUMMARY_PATH.exists()


def test_broker_readiness_proof_artifact_written() -> None:
    assert BROKER_READINESS_PROOF_PATH.exists()


def test_audit_recognizes_broker_readiness_artifacts() -> None:
    artifact_types = {record[0] for record in ARTIFACT_SPECS}
    assert "broker_readiness_preflight_checks" in artifact_types
    assert "broker_readiness_proof" in artifact_types


def test_audit_flags_broker_readiness_real_dollars(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "real_dollars": True})


def test_audit_flags_broker_readiness_buying_power(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "buying_power": True})


def test_audit_flags_broker_readiness_account_balance(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "account_balance": True})


def test_audit_flags_broker_readiness_broker_connection(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "broker_connection": True})


def test_audit_flags_broker_readiness_credentials(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "credentials": True})


def test_audit_flags_broker_readiness_scheduler(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "scheduler": True})


def test_audit_flags_broker_readiness_network_market_data(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "network_market_data": True})


def test_audit_flags_broker_readiness_live_order_review(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "live_order_review": True})


def test_audit_flags_broker_readiness_order_placement(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary({**broker_bundle["summary"], "order_placement": True})


def test_audit_confirms_read_only_detector_not_approved(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["next_required_gate"] == "explicit_human_approval_for_future_read_only_capability_detector_bundle"


def test_audit_confirms_broker_readiness_not_live_ready(broker_bundle: dict[str, Any]) -> None:
    assert audit_broker_readiness_summary(broker_bundle["summary"]) == []


def test_audit_confirms_no_active_forbidden_live_decisions_after_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["full_suite_timeout_recorded_as_pass"] is False


def test_reporting_includes_broker_readiness_summary(broker_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _broker_readiness_summary(evidence)["readiness_status"] == "read_only_boundary_simulated"


def test_reporting_includes_read_only_boundary_summary(broker_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _broker_readiness_summary(evidence)["read_only_boundary_simulated"] is True


def test_reporting_includes_manual_approval_gates(broker_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _broker_readiness_summary(evidence)["manual_gate_count"] >= 8


def test_export_verifier_selects_broker_readiness_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "broker_readiness_summary" in ids
    assert "broker_readiness_proof" in ids


def test_export_review_includes_broker_readiness_summary(broker_bundle: dict[str, Any]) -> None:
    ctx = SimpleNamespace(
        reporting_summary={"broker_readiness_summary": broker_bundle["summary"]},
        shared_export_path="shared",
        safety_state={},
        export_safety_scan={},
    )
    bundle = ExportReviewBundle("review", "bundle", "source", "manifest", "copy", 1, 1, "pass", "verified", "pass", "pass", 0, [], [], [], "read-only broker capability detector manual-approval packet", True, True, "hash")
    decision = ExportReviewDecision("decision", "bundle", "approve_for_offline_review", "offline_review_only", [], [], "read-only broker capability detector manual-approval packet", True, True, "hash")
    text = render_executive_summary(ctx, bundle, [], decision)
    assert "Broker-Readiness Preflight" in text


def test_broker_readiness_artifact_ledger_written(broker_bundle: dict[str, Any]) -> None:
    assert Path("docs/reports/DOPEY_BROKER_READINESS_ARTIFACT_LEDGER.md").exists()


def test_shard_plan_includes_broker_readiness_tests() -> None:
    summary = {"collection": {"status": "ok", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    file_result = CommandResult(["python", "-m", "pytest", "tests/test_broker_readiness_preflight.py", "-q"], "ok", 0, 1.0, False, False, "ok", "")
    plan = write_test_shard_plan(["tests/test_broker_readiness_preflight.py"], [file_result], summary)
    assert plan["broker_readiness_test_files"] == ["tests/test_broker_readiness_preflight.py"]


def test_shard_plan_marks_broker_readiness_artifact_tests_sequential() -> None:
    summary = {"collection": {"status": "ok", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    file_result = CommandResult(["python", "-m", "pytest", "tests/test_broker_readiness_preflight.py", "-q"], "ok", 0, 1.0, False, False, "ok", "")
    plan = write_test_shard_plan(["tests/test_broker_readiness_preflight.py"], [file_result], summary)
    assert "tests/test_broker_readiness_preflight.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    summary = {"collection": {"status": "ok", "stdout_tail": "collected"}, "full_suite": {"status": "inconclusive_timeout"}}
    file_result = CommandResult(["python", "-m", "pytest", "tests/test_broker_readiness_preflight.py", "-q"], "ok", 0, 1.0, False, False, "ok", "")
    plan = write_test_shard_plan(["tests/test_broker_readiness_preflight.py"], [file_result], summary)
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["live_trading_enabled"] is False


def test_robinhood_stub_still_blocks_live_after_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["credentials_created"] is False


def test_no_scheduler_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["scheduler_created"] is False


def test_no_network_market_data_dependency_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["no_real_market_data"] is True


def test_no_same_day_churn_loophole_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert _check(broker_bundle, "same_day_normal_close_blocked_check")["passed"]


def test_no_real_capital_allocator_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["real_sizing_created"] is False


def test_no_real_buying_power_logic_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert _simulation(broker_bundle, "buying_power_read_blocked")["blocked_write_or_execute"]


def test_no_robinhood_mcp_integration_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["robinhood_mcp_integration_created"] is False


def test_no_broker_connection_created_by_broker_readiness(broker_bundle: dict[str, Any]) -> None:
    assert broker_bundle["summary"]["broker_connection_created"] is False


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    findings = audit_blunder_integrity()
    assert not [finding for finding in findings if finding.severity == "safety_error"]
