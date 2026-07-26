"""Immutable behavioral-state transitions for paper-research circuit breakers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from .gates import BehavioralState, GateDecision, evaluate_behavioral_gate
from .identity import parse_utc, require_utc_iso


@dataclass(frozen=True, slots=True)
class BehavioralFirewallState:
    last_event_time: str | None
    last_position_fraction: float
    last_session_decision_count: int
    cooldown_until: str | None
    quarantined: bool
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BehavioralDecisionEvent:
    event_id: str
    event_time: str
    previous_outcome_was_loss: bool
    proposed_position_fraction: float
    session_decision_count: int
    abstention_overridden: bool
    fomo_entry: bool
    loss_limit_changed: bool
    invalidated_position_held: bool


@dataclass(frozen=True, slots=True)
class BehavioralTransition:
    state: BehavioralFirewallState
    gate: GateDecision


def advance_behavioral_firewall(
    state: BehavioralFirewallState,
    event: BehavioralDecisionEvent,
    cooldown_hours: float,
) -> BehavioralTransition:
    require_utc_iso(event.event_time)
    if not event.event_id or event.event_id in state.event_ids:
        raise ValueError("behavioral event identity is empty or duplicated")
    if state.last_event_time is not None:
        require_utc_iso(state.last_event_time)
        if parse_utc(event.event_time) <= parse_utc(state.last_event_time):
            raise ValueError("behavioral events must be strictly chronological")
    if not math.isfinite(event.proposed_position_fraction) or not 0.0 <= event.proposed_position_fraction <= 1.0:
        raise ValueError("behavioral event position fraction is invalid")
    if event.session_decision_count < 0 or state.last_session_decision_count < 0:
        raise ValueError("behavioral decision counts cannot be negative")
    if not math.isfinite(cooldown_hours) or cooldown_hours <= 0.0:
        raise ValueError("behavioral cooldown must be positive and finite")
    cooldown_active = (
        state.cooldown_until is not None
        and parse_utc(event.event_time) < parse_utc(state.cooldown_until)
    )
    size_ratio = 1.0
    frequency_ratio = 1.0
    if event.previous_outcome_was_loss:
        size_ratio = (
            event.proposed_position_fraction / state.last_position_fraction
            if state.last_position_fraction > 0.0
            else math.inf if event.proposed_position_fraction > 0.0 else 1.0
        )
        frequency_ratio = (
            event.session_decision_count / state.last_session_decision_count
            if state.last_session_decision_count > 0
            else math.inf if event.session_decision_count > 0 else 1.0
        )
    gate = evaluate_behavioral_gate(
        BehavioralState(
            size_ratio,
            frequency_ratio,
            1 if event.abstention_overridden else 0,
            event.fomo_entry,
            event.loss_limit_changed,
            event.invalidated_position_held,
            cooldown_active,
        )
    )
    next_cooldown = state.cooldown_until
    if not gate.passed:
        next_cooldown = (
            parse_utc(event.event_time) + timedelta(hours=cooldown_hours)
        ).isoformat().replace("+00:00", "Z")
    hard_quarantine = event.loss_limit_changed or event.invalidated_position_held
    next_state = BehavioralFirewallState(
        event.event_time,
        event.proposed_position_fraction,
        event.session_decision_count,
        next_cooldown,
        state.quarantined or hard_quarantine,
        (*state.event_ids, event.event_id),
    )
    return BehavioralTransition(next_state, gate)
