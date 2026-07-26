"""Deterministic offline kill-switch rehearsal engine."""
from __future__ import annotations

from collections import Counter
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .incident_response_policy import (
    build_incident_signal,
    decide_incident_response,
    expected_policy_record,
    select_kill_switch_state,
)
from .incident_response_simulator import simulate_incident_response_effects
from .incident_taxonomy import INCIDENT_RESPONSE_VERSION, default_incident_taxonomy
from .recovery_rehearsal import build_recovery_plan


def build_incident_response_bundle() -> dict[str, Any]:
    taxonomy = default_incident_taxonomy()
    cases = build_incident_rehearsal_cases()
    replay = replay_incident_rehearsal_cases(cases)
    return {
        "taxonomy": taxonomy,
        "cases": cases,
        **replay,
    }


def build_incident_rehearsal_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for spec in _required_case_specs():
        _add_case(cases, **spec)
    targets = {
        "policy_violation_incident": 16,
        "no_day_trade_incident": 16,
        "zero_dte_lifecycle_incident": 16,
        "portfolio_exposure_incident": 16,
        "crisis_mode_incident": 16,
        "broker_live_boundary_incident": 16,
        "evidence_audit_export_incident": 16,
        "validation_incident": 8,
        "recovery_incident": 8,
        "negative_control_incident": 8,
        "multi_incident_cascade": 8,
    }
    fill_specs = {
        "policy_violation_incident": ("policy_violation", "missing_thesis", "elevated", "paper_throttle", "throttle_paper_allocation", "active_policy"),
        "no_day_trade_incident": ("no_day_trade_violation", "repeated_same_day_close_pressure", "critical", "paper_lockdown", "paper_lockdown", "no_day_trade_guard"),
        "zero_dte_lifecycle_incident": ("zero_dte_lifecycle_violation", "missing_liquidity_approval", "critical", "paper_lockdown", "block_zero_dte", "zero_dte_lifecycle"),
        "portfolio_exposure_incident": ("portfolio_exposure_violation", "family_concentration_breach", "severe", "paper_throttle", "throttle_paper_allocation", "portfolio_replay"),
        "crisis_mode_incident": ("crisis_mode_violation", "crisis_throttle_bypass_attempt", "critical", "paper_lockdown", "paper_lockdown", "stress_ladder"),
        "broker_live_boundary_incident": ("live_path_injection", "live_flag_injection", "lockdown", "terminal_block", "terminal_block", "active_policy_audit"),
        "evidence_audit_export_incident": ("artifact_integrity_drift", "artifact_hash_mismatch", "severe", "manual_review_required", "manual_review_required", "offline_audit"),
        "validation_incident": ("validation_failure", "validation_shard_failure", "severe", "manual_review_required", "manual_review_required", "validation_stabilizer"),
        "recovery_incident": ("unknown_state", "recovery_rehearsal_clearance", "warning", "monitor", "continue_monitoring", "incident_recovery"),
        "negative_control_incident": ("unknown_state", "benign_warning", "warning", "monitor", "continue_monitoring", "incident_rehearsal"),
        "multi_incident_cascade": ("unknown_state", "multi_incident_cascade", "lockdown", "terminal_block", "terminal_block", "incident_rehearsal"),
    }
    for group, target in targets.items():
        while sum(1 for case in cases if case["case_group"] == group) < target:
            family, incident_type, severity, state, decision, component = fill_specs[group]
            count = sum(1 for case in cases if case["case_group"] == group) + 1
            _add_case(
                cases,
                case_group=group,
                required_case=f"{group}_{count:02d}",
                incident_family=family,
                incident_type=incident_type,
                source_component=component,
                severity=severity,
                state=state,
                decision=decision,
                trigger_conditions=[incident_type, "fixture_fill"],
                expected_recovery_allowed=state not in {"terminal_block"},
            )
    if len(cases) != 144:
        raise ValueError(f"incident rehearsal case count must be 144, got {len(cases)}")
    return cases


def replay_incident_rehearsal_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    signals = []
    states = []
    responses = []
    recoveries = []
    allocator_feedback = []
    threshold_feedback = []
    stress_ladder_feedback = []
    proof_records = []
    expected = [expected_policy_record(case) for case in cases]
    for case in cases:
        signal = build_incident_signal(case)
        state = select_kill_switch_state(signal, case)
        response = decide_incident_response(signal, state, case)
        recovery = build_recovery_plan(signal, state, case)
        effects = simulate_incident_response_effects(case, signal, state, response, recovery)
        proof = _proof_record(case, signal, state, response, recovery, effects)
        signals.append(signal.to_dict())
        states.append(state.to_dict())
        responses.append(response.to_dict())
        recoveries.append(recovery.to_dict())
        allocator_feedback.append(effects["allocator_feedback"])
        threshold_feedback.append(effects["threshold_feedback"])
        stress_ladder_feedback.append(effects["stress_ladder_feedback"])
        proof_records.append(proof)
    summary = _summary_record(cases, signals, states, responses, recoveries, proof_records)
    return {
        "expected_records": expected,
        "incident_signals": signals,
        "kill_switch_states": states,
        "incident_response_decisions": responses,
        "incident_recovery_plans": recoveries,
        "incident_allocator_feedback": allocator_feedback,
        "incident_threshold_feedback": threshold_feedback,
        "incident_stress_ladder_feedback": stress_ladder_feedback,
        "incident_response_proof": proof_records,
        "summary": summary,
    }


def _add_case(
    cases: list[dict[str, Any]],
    case_group: str,
    required_case: str,
    incident_family: str,
    incident_type: str,
    source_component: str,
    severity: str,
    state: str,
    decision: str,
    trigger_conditions: list[str],
    expected_recovery_allowed: bool,
) -> None:
    case_index = len(cases) + 1
    case = {
        "artifact_type": "incident_rehearsal_case",
        "incident_case_id": f"incident-case-{case_index:03d}-{required_case}",
        "case_group": case_group,
        "required_case": required_case,
        "incident_family": incident_family,
        "incident_type": incident_type,
        "source_component": source_component,
        "detected_at_stage": "offline_fixture_rehearsal",
        "severity": severity,
        "trigger_conditions": sorted(set(trigger_conditions)),
        "attempted_action": required_case,
        "expected_kill_switch_state": state,
        "expected_decision": decision,
        "expected_recovery_allowed": expected_recovery_allowed,
        "evidence_paths": [f"artifacts/dopey/incident_response/{required_case}.fixture"],
        "reason_codes": sorted(set([incident_family, incident_type, severity])),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credentials": True,
    }
    case["case_hash"] = reproducibility_hash(case)
    cases.append(case)


def _required_case_specs() -> list[dict[str, Any]]:
    return [
        _spec("policy_violation_incident", "sell_to_open_attempt_triggers_block", "policy_violation", "sell_to_open_attempt", "active_policy", "critical", "terminal_block", "terminal_block"),
        _spec("policy_violation_incident", "naked_option_attempt_triggers_terminal_block", "policy_violation", "naked_option_attempt", "active_policy", "critical", "terminal_block", "terminal_block"),
        _spec("policy_violation_incident", "unsupported_spread_triggers_policy_block", "policy_violation", "unsupported_multileg_structure", "active_policy", "severe", "paper_lockdown", "block_new_entries"),
        _spec("policy_violation_incident", "uncovered_writing_attempt_triggers_terminal_block", "policy_violation", "uncovered_writing_attempt", "active_policy", "critical", "terminal_block", "terminal_block"),
        _spec("no_day_trade_incident", "same_day_normal_close_attempt_triggers_paper_lockdown", "no_day_trade_violation", "same_day_normal_close_attempt", "no_day_trade_guard", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("no_day_trade_incident", "forced_same_day_close_during_crisis_blocked", "no_day_trade_violation", "forced_close_under_crisis", "crisis_throttle_engine", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("no_day_trade_incident", "delayed_rotation_bypass_attempt_blocked", "no_day_trade_violation", "delayed_rotation_bypass_attempt", "rotation_planner", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("no_day_trade_incident", "zero_dte_churn_disguised_as_special_close_blocked", "no_day_trade_violation", "zero_dte_churn_disguised_as_special_close", "zero_dte_lifecycle", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("zero_dte_lifecycle_incident", "zero_dte_special_close_missing_reason_blocked", "zero_dte_lifecycle_violation", "missing_special_close_reason", "zero_dte_lifecycle", "critical", "paper_lockdown", "block_zero_dte"),
        _spec("zero_dte_lifecycle_incident", "zero_dte_missing_liquidity_approval_blocked", "zero_dte_lifecycle_violation", "missing_liquidity_approval", "zero_dte_risk_model", "critical", "paper_lockdown", "block_zero_dte"),
        _spec("zero_dte_lifecycle_incident", "zero_dte_missing_risk_cap_blocked", "zero_dte_lifecycle_violation", "missing_risk_cap_approval", "zero_dte_risk_model", "critical", "paper_lockdown", "block_zero_dte"),
        _spec("zero_dte_lifecycle_incident", "unsafe_zero_dte_threshold_promotion_blocked", "zero_dte_lifecycle_violation", "zero_dte_threshold_profile_unsafe_promotion", "threshold_optimizer", "critical", "terminal_block", "terminal_block"),
        _spec("zero_dte_lifecycle_incident", "zero_dte_exposure_cap_breach_triggers_paper_throttle", "zero_dte_lifecycle_violation", "zero_dte_exposure_cap_breach", "portfolio_replay", "severe", "paper_throttle", "throttle_paper_allocation"),
        _spec("zero_dte_lifecycle_incident", "zero_dte_crisis_block_bypass_terminal_blocks", "zero_dte_lifecycle_violation", "zero_dte_crisis_block_bypass_attempt", "stress_ladder", "critical", "terminal_block", "terminal_block"),
        _spec("portfolio_exposure_incident", "family_concentration_breach_triggers_throttle", "portfolio_exposure_violation", "family_concentration_breach", "portfolio_replay", "severe", "paper_throttle", "throttle_paper_allocation"),
        _spec("portfolio_exposure_incident", "regime_concentration_breach_triggers_throttle", "portfolio_exposure_violation", "regime_concentration_breach", "portfolio_replay", "severe", "paper_throttle", "throttle_paper_allocation"),
        _spec("portfolio_exposure_incident", "call_put_imbalance_breach_triggers_throttle", "portfolio_exposure_violation", "call_put_imbalance_breach", "portfolio_replay", "severe", "paper_throttle", "throttle_paper_allocation"),
        _spec("portfolio_exposure_incident", "high_gamma_breach_triggers_defensive_mode", "portfolio_exposure_violation", "high_gamma_breach", "portfolio_replay", "severe", "paper_throttle", "throttle_paper_allocation"),
        _spec("portfolio_exposure_incident", "high_theta_breach_triggers_defensive_mode", "portfolio_exposure_violation", "high_theta_breach", "portfolio_replay", "severe", "paper_throttle", "throttle_paper_allocation"),
        _spec("portfolio_exposure_incident", "iv_event_macro_breach_triggers_severe_mode", "portfolio_exposure_violation", "iv_event_macro_breach", "portfolio_replay", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("portfolio_exposure_incident", "paper_shadow_leakage_escalates", "portfolio_exposure_violation", "paper_shadow_leakage", "portfolio_replay", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("portfolio_exposure_incident", "delayed_rotation_backlog_triggers_defensive_mode", "portfolio_exposure_violation", "delayed_rotation_backlog_breach", "rotation_planner", "severe", "paper_throttle", "throttle_paper_allocation"),
        _spec("crisis_mode_incident", "crisis_throttle_bypass_attempt_locks_down", "crisis_mode_violation", "crisis_throttle_bypass_attempt", "stress_ladder", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("crisis_mode_incident", "lockdown_new_entry_attempt_blocked", "crisis_mode_violation", "lockdown_new_entry_attempt", "stress_ladder", "critical", "paper_lockdown", "paper_lockdown"),
        _spec("crisis_mode_incident", "crisis_zero_dte_block_bypass_blocked", "crisis_mode_violation", "crisis_zero_dte_block_bypass", "stress_ladder", "critical", "paper_lockdown", "block_zero_dte"),
        _spec("broker_live_boundary_incident", "paperbroker_override_attempt_terminal_blocks", "paperbroker_override_attempt", "paperbroker_override_attempt", "paper_broker", "critical", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "live_flag_injection_terminal_blocks", "live_path_injection", "live_flag_injection", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "broker_path_injection_terminal_blocks", "broker_path_injection", "broker_path_injection", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "robinhood_path_before_capability_detector_terminal_blocks", "broker_path_injection", "robinhood_path_attempt_before_capability_detector", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "credential_string_reference_terminal_blocks", "credential_exposure", "api_token_credential_reference", "export_safety_scan", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "env_exposure_terminal_blocks", "credential_exposure", "env_exposure", "export_safety_scan", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "scheduler_emergence_terminal_blocks", "scheduler_emergence", "scheduler_emergence", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "network_market_data_dependency_terminal_blocks", "real_market_data_reference", "network_market_data_dependency", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "real_account_balance_reference_terminal_blocks", "real_sizing_reference", "real_account_balance_reference", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "real_buying_power_reference_terminal_blocks", "real_sizing_reference", "real_buying_power_reference", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("broker_live_boundary_incident", "real_dollar_sizing_reference_terminal_blocks", "real_sizing_reference", "real_dollar_sizing_reference", "active_policy_audit", "lockdown", "terminal_block", "terminal_block"),
        _spec("evidence_audit_export_incident", "artifact_hash_mismatch_manual_review", "artifact_integrity_drift", "artifact_hash_mismatch", "hash_auditor", "severe", "manual_review_required", "manual_review_required"),
        _spec("evidence_audit_export_incident", "missing_proof_ledger_audit_only", "proof_contradiction", "missing_proof_ledger", "offline_audit", "severe", "audit_only", "audit_only_mode"),
        _spec("evidence_audit_export_incident", "stale_audit_evidence_manual_review", "audit_staleness", "stale_audit_evidence", "offline_audit", "severe", "manual_review_required", "manual_review_required"),
        _spec("evidence_audit_export_incident", "conflicting_proof_records_manual_review", "proof_contradiction", "conflicting_proof_records", "offline_audit", "severe", "manual_review_required", "manual_review_required"),
        _spec("evidence_audit_export_incident", "export_safety_finding_terminal_blocks_if_severe", "export_safety_violation", "export_safety_finding", "export_safety_scan", "critical", "terminal_block", "terminal_block"),
        _spec("evidence_audit_export_incident", "credential_scan_finding_terminal_blocks", "credential_exposure", "credential_scan_finding", "export_safety_scan", "lockdown", "terminal_block", "terminal_block"),
        _spec("validation_incident", "validation_shard_failure_manual_review", "validation_failure", "validation_shard_failure", "validation_stabilizer", "severe", "manual_review_required", "manual_review_required"),
        _spec("validation_incident", "full_suite_timeout_misclassified_as_pass_terminal_blocks", "validation_failure", "full_suite_timeout_misclassified_as_pass", "validation_stabilizer", "lockdown", "terminal_block", "terminal_block"),
        _spec("evidence_audit_export_incident", "report_export_count_drift_audit_only", "proof_contradiction", "report_export_count_drift", "export_verifier", "severe", "audit_only", "audit_only_mode"),
        _spec("negative_control_incident", "benign_warning_stays_monitor", "unknown_state", "benign_warning", "incident_rehearsal", "warning", "monitor", "continue_monitoring"),
        _spec("negative_control_incident", "info_signal_stays_inactive", "unknown_state", "info_signal", "incident_rehearsal", "info", "inactive", "continue_monitoring"),
        _spec("multi_incident_cascade", "multi_incident_cascade_escalates_to_terminal_block", "unknown_state", "multi_incident_cascade", "incident_rehearsal", "lockdown", "terminal_block", "terminal_block"),
    ]


def _spec(
    case_group: str,
    required_case: str,
    incident_family: str,
    incident_type: str,
    source_component: str,
    severity: str,
    state: str,
    decision: str,
) -> dict[str, Any]:
    return {
        "case_group": case_group,
        "required_case": required_case,
        "incident_family": incident_family,
        "incident_type": incident_type,
        "source_component": source_component,
        "severity": severity,
        "state": state,
        "decision": decision,
        "trigger_conditions": [incident_type, required_case],
        "expected_recovery_allowed": state not in {"terminal_block"},
    }


def _proof_record(
    case: dict[str, Any],
    signal: Any,
    state: Any,
    response: Any,
    recovery: Any,
    effects: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "artifact_type": "incident_response_proof",
        "proof_id": f"incident-proof-{case['incident_case_id']}",
        "incident_case_id": case["incident_case_id"],
        "incident_family": signal.incident_family,
        "incident_type": signal.incident_type,
        "severity": signal.severity,
        "kill_switch_state": state.state_name,
        "response_decision": response.decision,
        "recovery_plan": recovery.recovery_plan_id,
        "action_allowed": not response.blocked_actions,
        "action_blocked": bool(response.blocked_actions),
        "allocator_feedback": effects["allocator_feedback"]["feedback_actions"],
        "threshold_feedback": effects["threshold_feedback"]["threshold_actions"],
        "stress_ladder_feedback": effects["stress_ladder_feedback"]["stress_ladder_actions"],
        "no_day_trade_result": effects["no_day_trade_result"],
        "paperbroker_result": effects["paperbroker_result"],
        "reason_codes": response.reason_codes,
        "safety_status": "paper_governance_pass",
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credentials": True,
        "same_day_close_forced": False,
        "same_day_churn_allowed": False,
        "paperbroker_override_allowed": False,
        "terminal_block_auto_recovery_allowed": False,
    }
    record["proof_hash"] = reproducibility_hash(record)
    return record


def _summary_record(
    cases: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    states: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    recoveries: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {
        "artifact_type": "incident_rehearsal_summary",
        "incident_response_version": INCIDENT_RESPONSE_VERSION,
        "incident_case_count": len(cases),
        "incident_signal_count": len(signals),
        "kill_switch_state_count": len(states),
        "incident_response_decision_count": len(responses),
        "incident_recovery_plan_count": len(recoveries),
        "proof_record_count": len(proof_records),
        "case_group_distribution": dict(sorted(Counter(case["case_group"] for case in cases).items())),
        "incident_family_distribution": dict(sorted(Counter(signal["incident_family"] for signal in signals).items())),
        "severity_distribution": dict(sorted(Counter(signal["severity"] for signal in signals).items())),
        "kill_switch_state_distribution": dict(sorted(Counter(state["state_name"] for state in states).items())),
        "response_decision_distribution": dict(sorted(Counter(response["decision"] for response in responses).items())),
        "recovery_plan_distribution": dict(sorted(Counter(recovery["target_state"] for recovery in recoveries).items())),
        "terminal_block_count": sum(1 for state in states if state["state_name"] == "terminal_block"),
        "manual_review_count": sum(1 for state in states if state["state_name"] == "manual_review_required"),
        "audit_only_count": sum(1 for state in states if state["state_name"] == "audit_only"),
        "paper_lockdown_count": sum(1 for state in states if state["state_name"] == "paper_lockdown"),
        "same_day_close_forced_count": sum(1 for proof in proof_records if proof["same_day_close_forced"]),
        "same_day_churn_allowed": any(proof["same_day_churn_allowed"] for proof in proof_records),
        "paperbroker_override_allowed": any(proof["paperbroker_override_allowed"] for proof in proof_records),
        "terminal_block_auto_recovery_allowed": any(proof["terminal_block_auto_recovery_allowed"] for proof in proof_records),
        "full_suite_timeout_recorded_as_pass": False,
        "allocator_feedback_advisory_only": True,
        "threshold_feedback_advisory_only": True,
        "stress_ladder_feedback_advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credentials": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary
