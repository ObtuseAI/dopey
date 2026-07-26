"""Apply offline incident response effects to paper-governance subsystems."""
from __future__ import annotations

from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .incident_models import IncidentSignal
from .incident_response_models import IncidentResponseDecision
from .kill_switch_models import KillSwitchState
from .recovery_rehearsal_models import IncidentRecoveryPlan


def simulate_incident_response_effects(
    case: dict[str, Any],
    signal: IncidentSignal,
    state: KillSwitchState,
    response: IncidentResponseDecision,
    recovery: IncidentRecoveryPlan,
) -> dict[str, Any]:
    effects = {
        "effect_id": f"incident-effects-{case['incident_case_id']}",
        "incident_case_id": case["incident_case_id"],
        "allocator_feedback": allocator_incident_feedback(case, signal, state, response),
        "threshold_feedback": threshold_incident_feedback(case, signal, state, response),
        "stress_ladder_feedback": stress_ladder_incident_feedback(case, signal, state, response),
        "no_day_trade_result": {
            "same_day_close_forced": False,
            "same_day_churn_allowed": False,
            "no_day_trade_dominant": True,
            "paper_only": True,
            "live_blocked": True,
        },
        "paperbroker_result": {
            "paperbroker_override_allowed": False,
            "broker_execution_allowed": False,
            "paperbroker_dominant": True,
            "paper_only": True,
            "live_blocked": True,
        },
        "recovery_result": {
            "recovery_allowed": recovery.recovery_allowed,
            "target_state": recovery.target_state,
            "terminal_block_auto_recovery_allowed": False,
        },
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credentials": True,
    }
    effects["effect_hash"] = reproducibility_hash(effects)
    return effects


def allocator_incident_feedback(case: dict[str, Any], signal: IncidentSignal, state: KillSwitchState, response: IncidentResponseDecision) -> dict[str, Any]:
    actions = ["keep_live_default_behavior_unchanged"]
    if response.decision in {"throttle_paper_allocation", "paper_lockdown", "block_new_entries"}:
        actions.append("throttle_paper_allocation")
    if response.decision in {"paper_lockdown", "terminal_block"}:
        actions.append("force_no_trade")
    if state.state_name == "terminal_block":
        actions.append("incident_terminal_block")
    record = {
        "artifact_type": "incident_allocator_feedback",
        "feedback_id": f"incident-allocator-feedback-{case['incident_case_id']}",
        "incident_case_id": case["incident_case_id"],
        "incident_family": signal.incident_family,
        "incident_type": signal.incident_type,
        "kill_switch_state": state.state_name,
        "response_decision": response.decision,
        "feedback_actions": sorted(set(actions)),
        "advisory_only": True,
        "live_allocation_mutation_allowed": False,
        "real_allocation_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["feedback_hash"] = reproducibility_hash(record)
    return record


def threshold_incident_feedback(case: dict[str, Any], signal: IncidentSignal, state: KillSwitchState, response: IncidentResponseDecision) -> dict[str, Any]:
    actions = ["no_live_threshold_mutation"]
    if signal.incident_family == "zero_dte_lifecycle_violation" or response.decision == "block_zero_dte":
        actions.append("block_threshold_profile")
    if response.decision in {"manual_review_required", "audit_only_mode"}:
        actions.append("require_more_fixture_coverage")
    if state.state_name == "terminal_block":
        actions.append("incident_terminal_block")
    record = {
        "artifact_type": "incident_threshold_feedback",
        "feedback_id": f"incident-threshold-feedback-{case['incident_case_id']}",
        "incident_case_id": case["incident_case_id"],
        "incident_family": signal.incident_family,
        "incident_type": signal.incident_type,
        "kill_switch_state": state.state_name,
        "response_decision": response.decision,
        "threshold_actions": sorted(set(actions)),
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["feedback_hash"] = reproducibility_hash(record)
    return record


def stress_ladder_incident_feedback(case: dict[str, Any], signal: IncidentSignal, state: KillSwitchState, response: IncidentResponseDecision) -> dict[str, Any]:
    actions = ["incident_rehearsal_observed"]
    if state.state_name in {"paper_lockdown", "terminal_block"}:
        actions.append("force_no_trade")
    if signal.incident_family in {"portfolio_exposure_violation", "crisis_mode_violation"}:
        actions.append("require_stress_ladder_rerun")
    if response.decision == "block_zero_dte":
        actions.append("block_zero_dte")
    record = {
        "artifact_type": "incident_stress_ladder_feedback",
        "feedback_id": f"incident-stress-ladder-feedback-{case['incident_case_id']}",
        "incident_case_id": case["incident_case_id"],
        "incident_family": signal.incident_family,
        "incident_type": signal.incident_type,
        "kill_switch_state": state.state_name,
        "response_decision": response.decision,
        "stress_ladder_actions": sorted(set(actions)),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["feedback_hash"] = reproducibility_hash(record)
    return record
