"""Proof-gated incident recovery rehearsal rules."""
from __future__ import annotations

from typing import Any

from .incident_models import IncidentSignal
from .kill_switch_models import KillSwitchState
from .recovery_rehearsal_models import IncidentRecoveryPlan, incident_recovery_plan_hash


GRADUAL_TARGETS = {
    "terminal_block": "manual_review_required",
    "manual_review_required": "audit_only",
    "paper_lockdown": "paper_throttle",
    "audit_only": "monitor",
    "paper_throttle": "monitor",
    "monitor": "inactive",
    "inactive": "inactive",
}


def build_recovery_plan(signal: IncidentSignal, state: KillSwitchState, case: dict[str, Any]) -> IncidentRecoveryPlan:
    required_checks = sorted(set(state.recovery_requirements + _family_required_checks(signal)))
    required_artifacts = _required_artifacts(signal)
    terminal_like = state.state_name == "terminal_block"
    manual_required = signal.incident_family in {
        "credential_exposure",
        "live_path_injection",
        "broker_path_injection",
        "scheduler_emergence",
        "real_market_data_reference",
        "real_sizing_reference",
        "paperbroker_override_attempt",
    }
    recovery_allowed = bool(case.get("expected_recovery_allowed", not terminal_like and not manual_required))
    if terminal_like or manual_required:
        recovery_allowed = False
    blockers = []
    if terminal_like:
        blockers.append("terminal_block_requires_manual_review")
    if manual_required:
        blockers.append("boundary_incident_requires_manual_review")
    if not recovery_allowed and not blockers:
        blockers.append("proof_gate_not_satisfied")
    seed = IncidentRecoveryPlan(
        recovery_plan_id=f"incident-recovery-plan-{signal.signal_id}",
        source_incident_id=signal.signal_id,
        current_kill_switch_state=state.state_name,
        target_state=GRADUAL_TARGETS[state.state_name],
        required_checks=required_checks,
        required_artifacts=required_artifacts,
        cooldown_steps=_cooldown_steps(state.state_name, signal),
        recovery_allowed=recovery_allowed,
        recovery_blockers=sorted(set(blockers)),
        paper_only=True,
        live_blocked=True,
        plan_hash="",
    )
    return IncidentRecoveryPlan(**{**seed.to_dict(), "plan_hash": incident_recovery_plan_hash(seed)})


def _family_required_checks(signal: IncidentSignal) -> list[str]:
    checks = {
        "no_day_trade_violation": ["no_day_trade_policy_proof_rerun"],
        "zero_dte_lifecycle_violation": ["zero_dte_lifecycle_proof_rerun"],
        "portfolio_exposure_violation": ["portfolio_replay_rerun"],
        "crisis_mode_violation": ["stress_ladder_rerun"],
        "artifact_integrity_drift": ["audit_rerun", "artifact_hash_recheck"],
        "audit_staleness": ["proof_refresh"],
        "proof_contradiction": ["proof_refresh"],
        "validation_failure": ["validation_rerun"],
    }
    return checks.get(signal.incident_family, [])


def _required_artifacts(signal: IncidentSignal) -> list[str]:
    artifacts = ["incident_response_proof", "incident_rehearsal_summary"]
    if signal.incident_family == "no_day_trade_violation":
        artifacts.append("no_day_trade_guard_proof")
    if signal.incident_family == "zero_dte_lifecycle_violation":
        artifacts.append("zero_dte_lifecycle_proof")
    if signal.incident_family == "portfolio_exposure_violation":
        artifacts.append("portfolio_replay_proof")
    if signal.incident_family == "crisis_mode_violation":
        artifacts.append("stress_ladder_proof")
    return sorted(set(artifacts))


def _cooldown_steps(state_name: str, signal: IncidentSignal) -> int:
    base = {
        "inactive": 0,
        "monitor": 1,
        "paper_throttle": 2,
        "audit_only": 3,
        "manual_review_required": 4,
        "paper_lockdown": 5,
        "terminal_block": 9,
    }[state_name]
    if signal.incident_family in {"zero_dte_lifecycle_violation", "no_day_trade_violation"}:
        base += 1
    return base

