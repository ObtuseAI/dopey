"""Policy mapping from incident signals to kill-switch responses."""
from __future__ import annotations

from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .incident_models import IncidentSignal, incident_signal_hash
from .incident_response_models import IncidentResponseDecision, incident_response_decision_hash
from .incident_taxonomy import taxonomy_by_incident_type
from .kill_switch_models import KillSwitchState, kill_switch_state_hash


STATE_RANKS = {
    "inactive": 0,
    "monitor": 1,
    "paper_throttle": 2,
    "audit_only": 3,
    "manual_review_required": 4,
    "paper_lockdown": 5,
    "terminal_block": 6,
}
STATE_BLOCKS = {
    "inactive": [],
    "monitor": ["live_trading", "broker_execution"],
    "paper_throttle": ["live_trading", "broker_execution", "aggressive_paper_allocation"],
    "audit_only": ["live_trading", "broker_execution", "new_entries", "threshold_promotion"],
    "manual_review_required": ["live_trading", "broker_execution", "new_entries", "threshold_promotion", "export_publication"],
    "paper_lockdown": ["live_trading", "broker_execution", "new_entries", "same_day_close", "paperbroker_override", "threshold_promotion"],
    "terminal_block": ["live_trading", "broker_execution", "new_entries", "same_day_close", "paperbroker_override", "threshold_promotion", "future_live_readiness"],
}


def build_incident_signal(case: dict[str, Any]) -> IncidentSignal:
    taxonomy = taxonomy_by_incident_type().get(str(case["incident_type"]), {})
    severity = str(case.get("severity") or taxonomy.get("default_severity", "warning"))
    seed = IncidentSignal(
        signal_id=f"incident-signal-{case['incident_case_id']}",
        incident_family=str(case["incident_family"]),
        incident_type=str(case["incident_type"]),
        source_component=str(case["source_component"]),
        detected_at_stage=str(case["detected_at_stage"]),
        severity=severity,
        trigger_conditions=[str(value) for value in case["trigger_conditions"]],
        evidence_paths=[str(value) for value in case["evidence_paths"]],
        reason_codes=[str(value) for value in case["reason_codes"]],
        paper_only=True,
        live_blocked=True,
        signal_hash="",
    )
    return IncidentSignal(**{**seed.to_dict(), "signal_hash": incident_signal_hash(seed)})


def select_kill_switch_state(signal: IncidentSignal, case: dict[str, Any]) -> KillSwitchState:
    taxonomy = taxonomy_by_incident_type().get(signal.incident_type, {})
    state_name = str(case.get("expected_kill_switch_state") or taxonomy.get("default_kill_switch_state", "monitor"))
    blocked = sorted(set(STATE_BLOCKS[state_name]))
    if "force_same_day_close" in blocked:
        raise ValueError("kill-switch state cannot force same-day close")
    seed = KillSwitchState(
        kill_switch_id=f"kill-switch-{signal.signal_id}",
        state_name=state_name,
        state_rank=STATE_RANKS[state_name],
        triggering_incident_ids=[signal.signal_id],
        blocked_actions=blocked,
        allowed_actions=_allowed_actions_for_state(state_name),
        audit_only_actions=["write_incident_report", "write_proof_record", "refresh_evidence_inventory"],
        paper_only_actions=_paper_actions_for_state(state_name),
        recovery_requirements=_recovery_requirements_for_state(state_name, signal),
        manual_review_required=state_name in {"manual_review_required", "terminal_block"},
        paper_only=True,
        live_blocked=True,
        state_hash="",
    )
    return KillSwitchState(**{**seed.to_dict(), "state_hash": kill_switch_state_hash(seed)})


def decide_incident_response(signal: IncidentSignal, state: KillSwitchState, case: dict[str, Any]) -> IncidentResponseDecision:
    taxonomy = taxonomy_by_incident_type().get(signal.incident_type, {})
    decision = str(case.get("expected_decision") or taxonomy.get("default_response_decision", "continue_monitoring"))
    blocked = sorted(set(state.blocked_actions + _decision_blocks(decision)))
    if "force_same_day_close" in blocked:
        raise ValueError("incident response cannot force same-day close")
    seed = IncidentResponseDecision(
        response_id=f"incident-response-{signal.signal_id}",
        incident_id=signal.signal_id,
        kill_switch_state=state.state_name,
        decision=decision,
        blocked_actions=blocked,
        allowed_actions=state.allowed_actions,
        audit_actions=state.audit_only_actions,
        remediation_actions=_remediation_actions(signal, state, decision),
        recovery_plan_id=f"incident-recovery-plan-{signal.signal_id}",
        reason_codes=sorted(set(signal.reason_codes + [f"state_{state.state_name}", f"decision_{decision}"])),
        paper_only=True,
        live_blocked=True,
        decision_hash="",
    )
    return IncidentResponseDecision(**{**seed.to_dict(), "decision_hash": incident_response_decision_hash(seed)})


def expected_policy_record(case: dict[str, Any]) -> dict[str, Any]:
    signal = build_incident_signal(case)
    state = select_kill_switch_state(signal, case)
    response = decide_incident_response(signal, state, case)
    return {
        "incident_case_id": case["incident_case_id"],
        "expected_kill_switch_state": state.state_name,
        "expected_response_decision": response.decision,
        "expected_recovery_allowed": bool(case.get("expected_recovery_allowed", state.state_name not in {"terminal_block"})),
        "paper_only": True,
        "live_blocked": True,
        "expectation_hash": reproducibility_hash({
            "incident_case_id": case["incident_case_id"],
            "state": state.state_name,
            "decision": response.decision,
        }),
    }


def _allowed_actions_for_state(state_name: str) -> list[str]:
    if state_name == "inactive":
        return ["audit_append", "paper_monitoring"]
    if state_name == "monitor":
        return ["audit_append", "paper_monitoring", "paper_watchlist_review"]
    return ["audit_append", "incident_report", "proof_refresh"]


def _paper_actions_for_state(state_name: str) -> list[str]:
    if state_name == "paper_throttle":
        return ["paper_allocation_throttle", "paper_watchlist_review"]
    if state_name == "paper_lockdown":
        return ["paper_no_trade", "paper_audit_replay"]
    return ["paper_monitoring"]


def _recovery_requirements_for_state(state_name: str, signal: IncidentSignal) -> list[str]:
    requirements = ["incident_proof_record", "safety_boundary_check"]
    if state_name in {"manual_review_required", "terminal_block"}:
        requirements.append("manual_review_signoff")
    if signal.incident_family in {"artifact_integrity_drift", "audit_staleness", "proof_contradiction"}:
        requirements.extend(["artifact_hash_recheck", "proof_refresh"])
    if signal.incident_family == "validation_failure":
        requirements.append("validation_rerun")
    return sorted(set(requirements))


def _decision_blocks(decision: str) -> list[str]:
    if decision == "block_zero_dte":
        return ["zero_dte_new_entries"]
    if decision == "throttle_paper_allocation":
        return ["aggressive_paper_allocation"]
    if decision == "audit_only_mode":
        return ["paper_allocation", "portfolio_rotation"]
    if decision == "terminal_block":
        return ["credential_use", "scheduler_start", "market_data_network", "real_sizing"]
    return []


def _remediation_actions(signal: IncidentSignal, state: KillSwitchState, decision: str) -> list[str]:
    actions = ["write_incident_report", "write_proof_record"]
    if decision in {"manual_review_required", "audit_only_mode", "terminal_block"}:
        actions.append("quarantine_artifact_family")
    if signal.incident_family in {"artifact_integrity_drift", "audit_staleness", "proof_contradiction"}:
        actions.append("require_proof_refresh")
        actions.append("require_audit_rerun")
    if signal.incident_family == "validation_failure":
        actions.append("require_validation_rerun")
    if signal.incident_family == "export_safety_violation":
        actions.append("require_export_safety_rerun")
    if state.state_name == "terminal_block":
        actions.append("terminal_block_future_live_readiness")
    return sorted(set(actions))

