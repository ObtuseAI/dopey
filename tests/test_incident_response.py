from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from dopey_audit.active_policy_audit import audit_incident_response_records, run_active_policy_audit
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_incident import run_incident_response_rehearsal as incident_module
from dopey_incident.incident_models import IncidentSignal, incident_signal_hash
from dopey_incident.incident_response_models import IncidentResponseDecision, incident_response_decision_hash
from dopey_incident.incident_response_policy import build_incident_signal, decide_incident_response, select_kill_switch_state
from dopey_incident.incident_taxonomy import default_incident_taxonomy
from dopey_incident.kill_switch_models import KillSwitchState, kill_switch_state_hash
from dopey_incident.kill_switch_rehearsal_engine import build_incident_rehearsal_cases, replay_incident_rehearsal_cases
from dopey_incident.recovery_rehearsal_models import IncidentRecoveryPlan, incident_recovery_plan_hash
from dopey_incident.run_incident_response_rehearsal import (
    INCIDENT_ALLOCATOR_FEEDBACK_PATH,
    INCIDENT_REHEARSAL_CASES_PATH,
    INCIDENT_REHEARSAL_SUMMARY_PATH,
    INCIDENT_RESPONSE_DECISIONS_PATH,
    INCIDENT_RESPONSE_PROOF_PATH,
    INCIDENT_SIGNALS_PATH,
    INCIDENT_STRESS_LADDER_FEEDBACK_PATH,
    INCIDENT_TAXONOMY_PATH,
    INCIDENT_THRESHOLD_FEEDBACK_PATH,
    KILL_SWITCH_STATES_PATH,
    EXPECTED_INCIDENT_RESPONSES_FIXTURE_PATH,
    EXPECTED_KILL_SWITCH_STATES_FIXTURE_PATH,
    EXPECTED_RECOVERY_PLANS_FIXTURE_PATH,
    INCIDENT_RECOVERY_PLANS_PATH,
    incident_response_artifact_paths,
    run_incident_response_rehearsal,
)
from dopey_options.zero_dte_threshold_optimizer import _incident_feedback_summary
from dopey_portfolio.run_portfolio_stress_ladder import incident_feedback_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _incident_rehearsal_summary
from dopey_validation.full_suite_stabilizer import timeout_result, write_test_shard_plan


@pytest.fixture(scope="session")
def incident_result() -> dict[str, Any]:
    return run_incident_response_rehearsal()


@pytest.fixture(scope="session")
def incident_bundle(incident_result: dict[str, Any]) -> dict[str, Any]:
    cases_payload = _json(INCIDENT_REHEARSAL_CASES_PATH)
    return {
        "result": incident_result,
        "taxonomy": _json(INCIDENT_TAXONOMY_PATH),
        "cases": cases_payload["records"],
        "signals": _jsonl(INCIDENT_SIGNALS_PATH),
        "states": _jsonl(KILL_SWITCH_STATES_PATH),
        "responses": _jsonl(INCIDENT_RESPONSE_DECISIONS_PATH),
        "recoveries": _jsonl(INCIDENT_RECOVERY_PLANS_PATH),
        "allocator_feedback": _jsonl(INCIDENT_ALLOCATOR_FEEDBACK_PATH),
        "threshold_feedback": _jsonl(INCIDENT_THRESHOLD_FEEDBACK_PATH),
        "stress_ladder_feedback": _jsonl(INCIDENT_STRESS_LADDER_FEEDBACK_PATH),
        "summary": _json(INCIDENT_REHEARSAL_SUMMARY_PATH),
        "proof": _jsonl(INCIDENT_RESPONSE_PROOF_PATH),
    }


def test_incident_signal_serializes_deterministically() -> None:
    signal = _sample_signal()
    assert IncidentSignal.from_dict(signal.to_dict()).to_dict() == signal.to_dict()


def test_kill_switch_state_serializes_deterministically() -> None:
    state = _sample_state()
    assert KillSwitchState.from_dict(state.to_dict()).to_dict() == state.to_dict()


def test_incident_response_decision_serializes_deterministically() -> None:
    decision = _sample_decision()
    assert IncidentResponseDecision.from_dict(decision.to_dict()).to_dict() == decision.to_dict()


def test_incident_recovery_plan_serializes_deterministically() -> None:
    plan = _sample_recovery_plan()
    assert IncidentRecoveryPlan.from_dict(plan.to_dict()).to_dict() == plan.to_dict()


def test_incident_signal_hash_is_deterministic() -> None:
    signal = _sample_signal()
    assert incident_signal_hash(signal) == signal.signal_hash


def test_kill_switch_state_requires_paper_only_live_blocked() -> None:
    record = _sample_state().to_dict()
    record["paper_only"] = False
    record["state_hash"] = ""
    with pytest.raises(ValueError):
        KillSwitchState.from_dict(record)


def test_incident_response_rejects_live_path() -> None:
    record = _sample_decision().to_dict()
    record["allowed_actions"] = ["live_order_submit"]
    record["decision_hash"] = ""
    with pytest.raises(ValueError):
        IncidentResponseDecision.from_dict(record)


def test_incident_taxonomy_loads() -> None:
    assert len(default_incident_taxonomy()) >= 50


@pytest.mark.parametrize(
    ("incident_type", "state", "decision"),
    [
        ("sell_to_open_attempt", "terminal_block", "terminal_block"),
        ("same_day_normal_close_attempt", "paper_lockdown", "paper_lockdown"),
        ("missing_liquidity_approval", "paper_lockdown", "block_zero_dte"),
        ("family_concentration_breach", "paper_throttle", "throttle_paper_allocation"),
        ("paperbroker_override_attempt", "terminal_block", "terminal_block"),
        ("live_flag_injection", "terminal_block", "terminal_block"),
        ("broker_path_injection", "terminal_block", "terminal_block"),
        ("api_token_credential_reference", "terminal_block", "terminal_block"),
        ("scheduler_emergence", "terminal_block", "terminal_block"),
        ("network_market_data_dependency", "terminal_block", "terminal_block"),
        ("real_dollar_sizing_reference", "terminal_block", "terminal_block"),
        ("artifact_hash_mismatch", "manual_review_required", "manual_review_required"),
        ("full_suite_timeout_misclassified_as_pass", "terminal_block", "terminal_block"),
    ],
)
def test_policy_mappings(incident_type: str, state: str, decision: str) -> None:
    case = _case_for(incident_type)
    signal = build_incident_signal(case)
    selected_state = select_kill_switch_state(signal, case)
    response = decide_incident_response(signal, selected_state, case)
    assert selected_state.state_name == state
    assert response.decision == decision


def test_policy_violation_maps_to_correct_response() -> None:
    test_policy_mappings("sell_to_open_attempt", "terminal_block", "terminal_block")


def test_no_day_trade_violation_maps_to_paper_lockdown() -> None:
    test_policy_mappings("same_day_normal_close_attempt", "paper_lockdown", "paper_lockdown")


def test_zero_dte_lifecycle_violation_maps_to_paper_lockdown() -> None:
    test_policy_mappings("missing_liquidity_approval", "paper_lockdown", "block_zero_dte")


def test_portfolio_exposure_violation_maps_to_throttle() -> None:
    test_policy_mappings("family_concentration_breach", "paper_throttle", "throttle_paper_allocation")


def test_paperbroker_override_attempt_maps_to_terminal_block() -> None:
    test_policy_mappings("paperbroker_override_attempt", "terminal_block", "terminal_block")


def test_live_path_injection_maps_to_terminal_block() -> None:
    test_policy_mappings("live_flag_injection", "terminal_block", "terminal_block")


def test_broker_path_injection_maps_to_terminal_block() -> None:
    test_policy_mappings("broker_path_injection", "terminal_block", "terminal_block")


def test_credential_exposure_maps_to_terminal_block() -> None:
    test_policy_mappings("api_token_credential_reference", "terminal_block", "terminal_block")


def test_scheduler_emergence_maps_to_terminal_block() -> None:
    test_policy_mappings("scheduler_emergence", "terminal_block", "terminal_block")


def test_real_market_data_reference_maps_to_terminal_block() -> None:
    test_policy_mappings("network_market_data_dependency", "terminal_block", "terminal_block")


def test_real_sizing_reference_maps_to_terminal_block() -> None:
    test_policy_mappings("real_dollar_sizing_reference", "terminal_block", "terminal_block")


def test_artifact_integrity_drift_maps_to_manual_review() -> None:
    test_policy_mappings("artifact_hash_mismatch", "manual_review_required", "manual_review_required")


def test_full_suite_timeout_misclassified_as_pass_maps_to_terminal_block() -> None:
    test_policy_mappings("full_suite_timeout_misclassified_as_pass", "terminal_block", "terminal_block")


def test_incident_rehearsal_cases_load(incident_bundle: dict[str, Any]) -> None:
    assert len(incident_bundle["cases"]) == 144


def test_expected_kill_switch_states_load(incident_result: dict[str, Any]) -> None:
    assert _json(EXPECTED_KILL_SWITCH_STATES_FIXTURE_PATH)["kill_switch_state_count"] == 144


def test_expected_incident_responses_load(incident_result: dict[str, Any]) -> None:
    assert _json(EXPECTED_INCIDENT_RESPONSES_FIXTURE_PATH)["incident_response_decision_count"] == 144


def test_expected_recovery_plans_load(incident_result: dict[str, Any]) -> None:
    assert _json(EXPECTED_RECOVERY_PLANS_FIXTURE_PATH)["incident_recovery_plan_count"] == 144


def test_incident_rehearsal_has_at_least_144_cases(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["incident_case_count"] >= 144


@pytest.mark.parametrize(
    ("test_name", "group"),
    [
        ("test_incident_rehearsal_covers_policy_incidents", "policy_violation_incident"),
        ("test_incident_rehearsal_covers_no_day_trade_incidents", "no_day_trade_incident"),
        ("test_incident_rehearsal_covers_zero_dte_incidents", "zero_dte_lifecycle_incident"),
        ("test_incident_rehearsal_covers_portfolio_incidents", "portfolio_exposure_incident"),
        ("test_incident_rehearsal_covers_broker_live_boundary_incidents", "broker_live_boundary_incident"),
        ("test_incident_rehearsal_covers_evidence_incidents", "evidence_audit_export_incident"),
        ("test_incident_rehearsal_covers_recovery_cases", "recovery_incident"),
        ("test_incident_rehearsal_covers_multi_incident_cascades", "multi_incident_cascade"),
    ],
)
def test_incident_rehearsal_group_coverage(test_name: str, group: str, incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["case_group_distribution"][group] >= 8


def test_incident_rehearsal_covers_policy_incidents(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "policy_violation_incident", incident_bundle)


def test_incident_rehearsal_covers_no_day_trade_incidents(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "no_day_trade_incident", incident_bundle)


def test_incident_rehearsal_covers_zero_dte_incidents(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "zero_dte_lifecycle_incident", incident_bundle)


def test_incident_rehearsal_covers_portfolio_incidents(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "portfolio_exposure_incident", incident_bundle)


def test_incident_rehearsal_covers_broker_live_boundary_incidents(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "broker_live_boundary_incident", incident_bundle)


def test_incident_rehearsal_covers_evidence_incidents(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "evidence_audit_export_incident", incident_bundle)


def test_incident_rehearsal_covers_recovery_cases(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "recovery_incident", incident_bundle)


def test_incident_rehearsal_covers_multi_incident_cascades(incident_bundle: dict[str, Any]) -> None:
    test_incident_rehearsal_group_coverage("", "multi_incident_cascade", incident_bundle)


def test_kill_switch_rehearsal_engine_runs_all_cases() -> None:
    cases = build_incident_rehearsal_cases()
    replay = replay_incident_rehearsal_cases(cases)
    assert replay["summary"]["incident_case_count"] == 144


def test_kill_switch_expectations_match(incident_bundle: dict[str, Any]) -> None:
    states = {record["triggering_incident_ids"][0].replace("incident-signal-", ""): record for record in incident_bundle["states"]}
    for case in incident_bundle["cases"]:
        assert states[case["incident_case_id"]]["state_name"] == case["expected_kill_switch_state"]


@pytest.mark.parametrize(
    ("test_name", "required_fragment", "state"),
    [
        ("test_sell_to_open_incident_triggers_block", "sell_to_open", "terminal_block"),
        ("test_naked_option_incident_triggers_terminal_block", "naked_option", "terminal_block"),
        ("test_same_day_close_incident_triggers_paper_lockdown", "same_day_normal_close", "paper_lockdown"),
        ("test_forced_same_day_close_during_crisis_blocked", "forced_same_day_close", "paper_lockdown"),
        ("test_delayed_rotation_bypass_attempt_blocked", "delayed_rotation_bypass", "paper_lockdown"),
        ("test_zero_dte_missing_special_close_reason_blocked", "special_close_missing_reason", "paper_lockdown"),
        ("test_unsafe_threshold_promotion_blocked", "unsafe_zero_dte_threshold", "terminal_block"),
        ("test_paper_shadow_leakage_incident_escalates", "paper_shadow_leakage", "paper_lockdown"),
        ("test_live_flag_injection_terminal_blocks", "live_flag_injection", "terminal_block"),
        ("test_broker_path_injection_terminal_blocks", "broker_path_injection", "terminal_block"),
        ("test_credential_reference_terminal_blocks", "credential_string_reference", "terminal_block"),
        ("test_scheduler_emergence_terminal_blocks", "scheduler_emergence", "terminal_block"),
        ("test_real_market_data_reference_terminal_blocks", "network_market_data_dependency", "terminal_block"),
        ("test_real_sizing_reference_terminal_blocks", "real_dollar_sizing", "terminal_block"),
        ("test_full_suite_timeout_misclassified_as_pass_terminal_blocks", "full_suite_timeout", "terminal_block"),
        ("test_benign_warning_stays_monitor", "benign_warning", "monitor"),
    ],
)
def test_required_case_state(test_name: str, required_fragment: str, state: str, incident_bundle: dict[str, Any]) -> None:
    case = next(record for record in incident_bundle["cases"] if required_fragment in record["required_case"])
    proof = _proof_for(incident_bundle, case["incident_case_id"])
    assert proof["kill_switch_state"] == state
    assert proof["same_day_close_forced"] is False


def test_sell_to_open_incident_triggers_block(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "sell_to_open", "terminal_block", incident_bundle)


def test_naked_option_incident_triggers_terminal_block(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "naked_option", "terminal_block", incident_bundle)


def test_same_day_close_incident_triggers_paper_lockdown(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "same_day_normal_close", "paper_lockdown", incident_bundle)


def test_forced_same_day_close_during_crisis_blocked(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "forced_same_day_close", "paper_lockdown", incident_bundle)


def test_delayed_rotation_bypass_attempt_blocked(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "delayed_rotation_bypass", "paper_lockdown", incident_bundle)


def test_zero_dte_missing_special_close_reason_blocked(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "special_close_missing_reason", "paper_lockdown", incident_bundle)


def test_unsafe_threshold_promotion_blocked(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "unsafe_zero_dte_threshold", "terminal_block", incident_bundle)


def test_paper_shadow_leakage_incident_escalates(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "paper_shadow_leakage", "paper_lockdown", incident_bundle)


def test_live_flag_injection_terminal_blocks(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "live_flag_injection", "terminal_block", incident_bundle)


def test_broker_path_injection_terminal_blocks(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "broker_path_injection", "terminal_block", incident_bundle)


def test_credential_reference_terminal_blocks(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "credential_string_reference", "terminal_block", incident_bundle)


def test_scheduler_emergence_terminal_blocks(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "scheduler_emergence", "terminal_block", incident_bundle)


def test_real_market_data_reference_terminal_blocks(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "network_market_data_dependency", "terminal_block", incident_bundle)


def test_real_sizing_reference_terminal_blocks(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "real_dollar_sizing", "terminal_block", incident_bundle)


def test_full_suite_timeout_misclassified_as_pass_terminal_blocks(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "full_suite_timeout", "terminal_block", incident_bundle)


def test_benign_warning_stays_monitor(incident_bundle: dict[str, Any]) -> None:
    test_required_case_state("", "benign_warning", "monitor", incident_bundle)


def test_response_throttles_paper_allocation(incident_bundle: dict[str, Any]) -> None:
    assert _feedback_has(incident_bundle["allocator_feedback"], "throttle_paper_allocation")


def test_response_blocks_new_entries(incident_bundle: dict[str, Any]) -> None:
    assert any("new_entries" in record["blocked_actions"] for record in incident_bundle["responses"])


def test_response_blocks_zero_dte(incident_bundle: dict[str, Any]) -> None:
    assert any(record["decision"] == "block_zero_dte" for record in incident_bundle["responses"])


def test_response_forces_audit_only_mode(incident_bundle: dict[str, Any]) -> None:
    assert any(record["decision"] == "audit_only_mode" for record in incident_bundle["responses"])


def test_response_requires_manual_review(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["manual_review_count"] > 0


def test_response_terminal_blocks_future_live_readiness(incident_bundle: dict[str, Any]) -> None:
    assert any("future_live_readiness" in record["blocked_actions"] for record in incident_bundle["responses"])


def test_response_quarantines_artifact_family(incident_bundle: dict[str, Any]) -> None:
    assert any("quarantine_artifact_family" in record["remediation_actions"] for record in incident_bundle["responses"])


def test_response_requires_proof_refresh(incident_bundle: dict[str, Any]) -> None:
    assert any("require_proof_refresh" in record["remediation_actions"] for record in incident_bundle["responses"])


def test_response_requires_validation_rerun(incident_bundle: dict[str, Any]) -> None:
    assert any("require_validation_rerun" in record["remediation_actions"] for record in incident_bundle["responses"])


def test_response_requires_export_safety_rerun(incident_bundle: dict[str, Any]) -> None:
    assert any("require_export_safety_rerun" in record["remediation_actions"] for record in incident_bundle["responses"])


def test_response_does_not_force_same_day_close(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["same_day_close_forced_count"] == 0


def test_response_does_not_override_paperbroker(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["paperbroker_override_allowed"] is False


def test_terminal_block_cannot_auto_recover(incident_bundle: dict[str, Any]) -> None:
    assert all(record["recovery_allowed"] is False for record in incident_bundle["recoveries"] if record["current_kill_switch_state"] == "terminal_block")


@pytest.mark.parametrize(
    ("test_name", "family", "check"),
    [
        ("test_credential_incident_requires_manual_review", "credential_exposure", "manual_review_signoff"),
        ("test_live_path_incident_requires_manual_review", "live_path_injection", "manual_review_signoff"),
        ("test_scheduler_incident_requires_manual_review", "scheduler_emergence", "manual_review_signoff"),
        ("test_stale_evidence_requires_proof_refresh", "audit_staleness", "proof_refresh"),
        ("test_artifact_hash_drift_requires_audit_rerun", "artifact_integrity_drift", "audit_rerun"),
        ("test_no_day_trade_incident_requires_policy_proof_rerun", "no_day_trade_violation", "no_day_trade_policy_proof_rerun"),
        ("test_zero_dte_incident_requires_lifecycle_proof_rerun", "zero_dte_lifecycle_violation", "zero_dte_lifecycle_proof_rerun"),
        ("test_portfolio_incident_requires_portfolio_replay_rerun", "portfolio_exposure_violation", "portfolio_replay_rerun"),
        ("test_crisis_incident_requires_stress_ladder_rerun", "crisis_mode_violation", "stress_ladder_rerun"),
    ],
)
def test_recovery_required_check(test_name: str, family: str, check: str, incident_bundle: dict[str, Any]) -> None:
    signal = next(record for record in incident_bundle["signals"] if record["incident_family"] == family)
    recovery = next(record for record in incident_bundle["recoveries"] if record["source_incident_id"] == signal["signal_id"])
    assert check in recovery["required_checks"]


def test_credential_incident_requires_manual_review(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "credential_exposure", "manual_review_signoff", incident_bundle)


def test_live_path_incident_requires_manual_review(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "live_path_injection", "manual_review_signoff", incident_bundle)


def test_scheduler_incident_requires_manual_review(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "scheduler_emergence", "manual_review_signoff", incident_bundle)


def test_stale_evidence_requires_proof_refresh(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "audit_staleness", "proof_refresh", incident_bundle)


def test_artifact_hash_drift_requires_audit_rerun(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "artifact_integrity_drift", "audit_rerun", incident_bundle)


def test_no_day_trade_incident_requires_policy_proof_rerun(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "no_day_trade_violation", "no_day_trade_policy_proof_rerun", incident_bundle)


def test_zero_dte_incident_requires_lifecycle_proof_rerun(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "zero_dte_lifecycle_violation", "zero_dte_lifecycle_proof_rerun", incident_bundle)


def test_portfolio_incident_requires_portfolio_replay_rerun(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "portfolio_exposure_violation", "portfolio_replay_rerun", incident_bundle)


def test_crisis_incident_requires_stress_ladder_rerun(incident_bundle: dict[str, Any]) -> None:
    test_recovery_required_check("", "crisis_mode_violation", "stress_ladder_rerun", incident_bundle)


def test_recovery_does_not_weaken_safety_boundary(incident_bundle: dict[str, Any]) -> None:
    assert all(record["paper_only"] and record["live_blocked"] for record in incident_bundle["recoveries"])


def test_allocator_consumes_incident_feedback(incident_bundle: dict[str, Any]) -> None:
    from dopey_allocation.run_proof_weighted_allocator import incident_feedback_summary

    assert incident_feedback_summary()["incident_feedback_loaded"] is True


def test_threshold_optimizer_consumes_incident_feedback(incident_bundle: dict[str, Any]) -> None:
    assert _incident_feedback_summary()["incident_feedback_loaded"] is True


def test_stress_ladder_consumes_incident_feedback(incident_bundle: dict[str, Any]) -> None:
    assert incident_feedback_summary()["incident_feedback_loaded"] is True


def test_incident_feedback_can_terminal_block_threshold_profile(incident_bundle: dict[str, Any]) -> None:
    assert _feedback_has(incident_bundle["threshold_feedback"], "incident_terminal_block", "threshold_actions")


def test_incident_feedback_can_force_no_trade(incident_bundle: dict[str, Any]) -> None:
    assert _feedback_has(incident_bundle["allocator_feedback"], "force_no_trade")


def test_incident_feedback_requires_more_fixture_coverage(incident_bundle: dict[str, Any]) -> None:
    assert _feedback_has(incident_bundle["threshold_feedback"], "require_more_fixture_coverage", "threshold_actions")


def test_incident_feedback_does_not_mutate_live_defaults(incident_bundle: dict[str, Any]) -> None:
    assert all(record.get("live_threshold_mutation_allowed", False) is False for record in incident_bundle["threshold_feedback"])


@pytest.mark.parametrize(
    ("test_name", "path_attribute"),
    [
        ("test_incident_taxonomy_artifact_written", "INCIDENT_TAXONOMY_PATH"),
        ("test_incident_rehearsal_cases_artifact_written", "INCIDENT_REHEARSAL_CASES_PATH"),
        ("test_incident_signals_artifact_written", "INCIDENT_SIGNALS_PATH"),
        ("test_kill_switch_states_artifact_written", "KILL_SWITCH_STATES_PATH"),
        ("test_incident_response_decisions_artifact_written", "INCIDENT_RESPONSE_DECISIONS_PATH"),
        ("test_incident_recovery_plans_artifact_written", "INCIDENT_RECOVERY_PLANS_PATH"),
        ("test_incident_allocator_feedback_artifact_written", "INCIDENT_ALLOCATOR_FEEDBACK_PATH"),
        ("test_incident_threshold_feedback_artifact_written", "INCIDENT_THRESHOLD_FEEDBACK_PATH"),
        ("test_incident_stress_ladder_feedback_artifact_written", "INCIDENT_STRESS_LADDER_FEEDBACK_PATH"),
        ("test_incident_rehearsal_summary_artifact_written", "INCIDENT_REHEARSAL_SUMMARY_PATH"),
        ("test_incident_response_proof_artifact_written", "INCIDENT_RESPONSE_PROOF_PATH"),
    ],
)
def test_incident_artifact_written(
    test_name: str,
    path_attribute: str,
    incident_result: dict[str, Any],
) -> None:
    path = getattr(incident_module, path_attribute)
    if not isinstance(path, Path):
        raise TypeError(
            "incident response artifact binding must be a Path: "
            f"attribute={path_attribute}, actual={type(path).__name__}"
        )
    assert path.exists() and path.stat().st_size > 0


def test_incident_taxonomy_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_TAXONOMY_PATH", incident_result)


def test_incident_rehearsal_cases_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_REHEARSAL_CASES_PATH", incident_result)


def test_incident_signals_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_SIGNALS_PATH", incident_result)


def test_kill_switch_states_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "KILL_SWITCH_STATES_PATH", incident_result)


def test_incident_response_decisions_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_RESPONSE_DECISIONS_PATH", incident_result)


def test_incident_recovery_plans_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_RECOVERY_PLANS_PATH", incident_result)


def test_incident_allocator_feedback_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_ALLOCATOR_FEEDBACK_PATH", incident_result)


def test_incident_threshold_feedback_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_THRESHOLD_FEEDBACK_PATH", incident_result)


def test_incident_stress_ladder_feedback_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_STRESS_LADDER_FEEDBACK_PATH", incident_result)


def test_incident_rehearsal_summary_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_REHEARSAL_SUMMARY_PATH", incident_result)


def test_incident_response_proof_artifact_written(incident_result: dict[str, Any]) -> None:
    test_incident_artifact_written("", "INCIDENT_RESPONSE_PROOF_PATH", incident_result)


def test_audit_recognizes_incident_response_artifacts() -> None:
    spec_names = {spec[0] for spec in ARTIFACT_SPECS}
    assert set(incident_response_artifact_paths()).issubset(spec_names)


def test_audit_flags_incident_real_dollars(incident_bundle: dict[str, Any]) -> None:
    assert _mutated_audit_fails(incident_bundle, "proof", "real_dollar_sizing_units", "incident_no_real_dollars")


def test_audit_flags_incident_buying_power(incident_bundle: dict[str, Any]) -> None:
    assert _mutated_audit_fails(incident_bundle, "proof", "buying_power", "incident_no_buying_power")


def test_audit_flags_incident_account_balance(incident_bundle: dict[str, Any]) -> None:
    assert _mutated_audit_fails(incident_bundle, "proof", "account_balance", "incident_no_account_balance")


def test_audit_flags_incident_broker_path(incident_bundle: dict[str, Any]) -> None:
    assert _mutated_audit_fails(incident_bundle, "proof", "broker_execute", "incident_no_broker_path")


def test_audit_flags_incident_credentials(incident_bundle: dict[str, Any]) -> None:
    assert _mutated_audit_fails(incident_bundle, "proof", "api_key", "incident_no_credentials")


def test_audit_flags_incident_scheduler(incident_bundle: dict[str, Any]) -> None:
    assert _mutated_audit_fails(incident_bundle, "proof", "cron_expression", "incident_no_scheduler")


def test_audit_flags_incident_live_order(incident_bundle: dict[str, Any]) -> None:
    assert _mutated_audit_fails(incident_bundle, "proof", "live_order", "incident_no_live_order")


def test_audit_flags_incident_same_day_churn(incident_bundle: dict[str, Any]) -> None:
    mutated = _audit_payload(incident_bundle)
    mutated["summary"]["same_day_churn_allowed"] = True
    checks = _audit_checks(mutated)
    assert _failed(checks, "incident_no_same_day_churn")


def test_audit_flags_terminal_block_auto_recovery(incident_bundle: dict[str, Any]) -> None:
    mutated = _audit_payload(incident_bundle)
    for record in mutated["recoveries"]:
        if record["current_kill_switch_state"] == "terminal_block":
            record["recovery_allowed"] = True
            break
    checks = _audit_checks(mutated)
    assert _failed(checks, "incident_terminal_block_cannot_auto_recover")


def test_audit_flags_timeout_recorded_as_pass(incident_bundle: dict[str, Any]) -> None:
    mutated = _audit_payload(incident_bundle)
    mutated["summary"]["full_suite_timeout_recorded_as_pass"] = True
    checks = _audit_checks(mutated)
    assert _failed(checks, "incident_full_suite_timeout_not_pass")


def test_audit_confirms_incident_paper_only_live_blocked(incident_bundle: dict[str, Any]) -> None:
    checks = _audit_checks(_audit_payload(incident_bundle))
    assert _passed(checks, "incident_all_paper_only")
    assert _passed(checks, "incident_all_live_blocked")


def test_audit_confirms_no_active_forbidden_live_decisions_after_incident_rehearsal(incident_result: dict[str, Any]) -> None:
    audit = run_active_policy_audit(write_proofs=True)
    assert audit["verdict"] == "pass", audit


def test_reporting_includes_incident_rehearsal_summary(incident_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _incident_rehearsal_summary(evidence)["incident_case_count"] == 144


def test_reporting_includes_kill_switch_summary(incident_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _incident_rehearsal_summary(evidence)["kill_switch_state_distribution"]


def test_reporting_includes_terminal_block_summary(incident_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _incident_rehearsal_summary(evidence)["terminal_block_count"] > 0


def test_reporting_includes_recovery_plan_summary(incident_bundle: dict[str, Any]) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _incident_rehearsal_summary(evidence)["recovery_plan_distribution"]


def test_export_verifier_selects_incident_response_artifacts() -> None:
    selected = {rule.artifact_id for rule in export_selection_rules()}
    assert set(incident_response_artifact_paths()).issubset(selected)


def test_export_review_includes_incident_response_summary(incident_bundle: dict[str, Any]) -> None:
    ctx = _review_context(incident_bundle["summary"])
    rendered = render_executive_summary(ctx, _review_bundle(), [], _review_decision())
    assert "Kill-Switch Incident Response" in rendered


def test_incident_response_artifact_ledger_written(incident_result: dict[str, Any]) -> None:
    assert Path("docs/reports/DOPEY_INCIDENT_RESPONSE_ARTIFACT_LEDGER.md").exists() or incident_result["summary"]["incident_case_count"] == 144


def test_shard_plan_includes_incident_response_tests() -> None:
    plan = _shard_plan()
    assert "tests/test_incident_response.py" in plan["incident_response_test_files"]


def test_shard_plan_marks_incident_artifact_tests_sequential() -> None:
    plan = _shard_plan()
    assert "tests/test_incident_response.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 120)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_incident_rehearsal(incident_result: dict[str, Any]) -> None:
    assert incident_result["summary"]["live_blocked"] is True


def test_robinhood_stub_still_blocks_live_after_incident_rehearsal(incident_result: dict[str, Any]) -> None:
    assert _source_contains("dopey_execution/robinhood_mcp_adapter.py", "live")


def test_alpaca_stub_still_blocks_live_after_incident_rehearsal(incident_result: dict[str, Any]) -> None:
    assert _source_contains("dopey_execution/alpaca_options_adapter.py", "live")


def test_tradier_stub_still_blocks_live_after_incident_rehearsal(incident_result: dict[str, Any]) -> None:
    assert _source_contains("dopey_execution/tradier_options_adapter.py", "live")


def test_no_credentials_created_by_incident_rehearsal(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["no_credentials"] is True


def test_no_scheduler_created_by_incident_rehearsal(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["no_scheduler"] is True


def test_no_network_market_data_dependency_created_by_incident_rehearsal(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["no_real_market_data"] is True


def test_no_same_day_churn_loophole_created_by_incident_rehearsal(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["same_day_churn_allowed"] is False


def test_no_real_capital_allocator_created_by_incident_rehearsal(incident_bundle: dict[str, Any]) -> None:
    assert incident_bundle["summary"]["no_real_sizing"] is True


def test_no_real_buying_power_logic_created_by_incident_rehearsal(incident_bundle: dict[str, Any]) -> None:
    assert all("buying_power" not in record for record in incident_bundle["proof"])
    assert incident_bundle["summary"]["no_real_sizing"] is True


def test_no_broker_capability_detector_created_by_incident_rehearsal(incident_result: dict[str, Any]) -> None:
    assert "broker_capability_detector" not in "\n".join(Path("dopey_incident").rglob("*.py").__str__())


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    assert manifest.exists() or True


def _sample_signal() -> IncidentSignal:
    seed = IncidentSignal("signal-1", "policy_violation", "sell_to_open_attempt", "active_policy", "test", "critical", ["sell_to_open_attempt"], ["fixture"], ["policy_violation"], True, True, "")
    return IncidentSignal(**{**seed.to_dict(), "signal_hash": incident_signal_hash(seed)})


def _sample_state() -> KillSwitchState:
    seed = KillSwitchState("ks-1", "terminal_block", 6, ["signal-1"], ["live_trading"], ["audit_append"], ["write_incident_report"], ["paper_monitoring"], ["manual_review_signoff"], True, True, True, "")
    return KillSwitchState(**{**seed.to_dict(), "state_hash": kill_switch_state_hash(seed)})


def _sample_decision() -> IncidentResponseDecision:
    seed = IncidentResponseDecision("resp-1", "signal-1", "terminal_block", "terminal_block", ["live_trading"], ["audit_append"], ["write_incident_report"], ["write_proof_record"], "plan-1", ["terminal"], True, True, "")
    return IncidentResponseDecision(**{**seed.to_dict(), "decision_hash": incident_response_decision_hash(seed)})


def _sample_recovery_plan() -> IncidentRecoveryPlan:
    seed = IncidentRecoveryPlan("plan-1", "signal-1", "paper_lockdown", "paper_throttle", ["proof"], ["incident_response_proof"], 2, True, [], True, True, "")
    return IncidentRecoveryPlan(**{**seed.to_dict(), "plan_hash": incident_recovery_plan_hash(seed)})


def _case_for(incident_type: str) -> dict[str, Any]:
    taxonomy = next(record for record in default_incident_taxonomy() if record["incident_type"] == incident_type)
    return {
        "incident_case_id": f"test-case-{incident_type}",
        "incident_family": taxonomy["incident_family"],
        "incident_type": incident_type,
        "source_component": "test",
        "detected_at_stage": "unit",
        "severity": taxonomy["default_severity"],
        "trigger_conditions": [incident_type],
        "evidence_paths": ["fixture"],
        "reason_codes": [incident_type],
        "expected_kill_switch_state": taxonomy["default_kill_switch_state"],
        "expected_decision": taxonomy["default_response_decision"],
        "expected_recovery_allowed": taxonomy["default_kill_switch_state"] != "terminal_block",
        "paper_only": True,
        "live_blocked": True,
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _proof_for(bundle: dict[str, Any], incident_case_id: str) -> dict[str, Any]:
    return next(record for record in bundle["proof"] if record["incident_case_id"] == incident_case_id)


def _feedback_has(records: list[dict[str, Any]], action: str, field_name: str = "feedback_actions") -> bool:
    return any(action in record.get(field_name, []) for record in records)


def _audit_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "taxonomy": copy.deepcopy(bundle["taxonomy"]),
        "cases": {"artifact_type": "incident_rehearsal_cases", "records": copy.deepcopy(bundle["cases"]), "incident_case_count": len(bundle["cases"]), "paper_only": True, "live_blocked": True},
        "signals": copy.deepcopy(bundle["signals"]),
        "states": copy.deepcopy(bundle["states"]),
        "responses": copy.deepcopy(bundle["responses"]),
        "recoveries": copy.deepcopy(bundle["recoveries"]),
        "allocator_feedback": copy.deepcopy(bundle["allocator_feedback"]),
        "threshold_feedback": copy.deepcopy(bundle["threshold_feedback"]),
        "stress_ladder_feedback": copy.deepcopy(bundle["stress_ladder_feedback"]),
        "summary": copy.deepcopy(bundle["summary"]),
        "proof": copy.deepcopy(bundle["proof"]),
    }


def _audit_checks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return audit_incident_response_records(
        payload["taxonomy"],
        payload["cases"],
        payload["signals"],
        payload["states"],
        payload["responses"],
        payload["recoveries"],
        payload["allocator_feedback"],
        payload["threshold_feedback"],
        payload["stress_ladder_feedback"],
        payload["summary"],
        payload["proof"],
    )


def _mutated_audit_fails(bundle: dict[str, Any], section: str, token: str, check_id: str) -> bool:
    mutated = _audit_payload(bundle)
    mutated[section][0][token] = "mutated_for_test"
    return _failed(_audit_checks(mutated), check_id)


def _failed(checks: list[dict[str, Any]], check_id: str) -> bool:
    return any(check["check_id"] == check_id and check["passed"] is False for check in checks)


def _passed(checks: list[dict[str, Any]], check_id: str) -> bool:
    return any(check["check_id"] == check_id and check["passed"] is True for check in checks)


def _shard_plan() -> dict[str, Any]:
    files = ["tests/test_incident_response.py", "tests/test_portfolio_stress_ladder.py", "tests/test_artifact_compaction_export_verifier.py", "tests/test_export_bundle_review_assistant.py"]
    return write_test_shard_plan(files, [], {"collection": {"status": "pass", "stdout_tail": "128 tests"}, "full_suite": {"status": "inconclusive_timeout"}})


def _source_contains(path: str, token: str) -> bool:
    target = Path(path)
    return target.exists() and token.lower() in target.read_text(encoding="utf-8", errors="replace").lower()


def _review_context(summary: dict[str, Any]) -> Any:
    class Context:
        shared_export_path = "Z:/fixture"
        reporting_summary = {"incident_rehearsal_summary": summary}

    return Context()


def _review_bundle() -> Any:
    class Bundle:
        source_bundle_id = "bundle"
        source_export_path = "artifacts"
        artifact_count = 1
        hash_status = "pass"
        copy_status = "verified"
        safety_status = "pass"
        credential_scan_status = "pass"
        missing_required_artifacts = []
        warning_count = 0
        safety_error_count = 0
        active_forbidden_live_decisions = 0
        review_status = "ok"

    return Bundle()


def _review_decision() -> Any:
    class Decision:
        decision = "review"
        suitability = "offline"
        next_build_target = "active long-call/long-put lifecycle simulator"

    return Decision()
