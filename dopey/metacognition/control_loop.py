"""Closed-loop research controls restricted to non-protected runtime choices."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.protocols.identity import canonical_hash


ALLOWED_CONTROL_OUTPUTS: frozenset[str] = frozenset(
    {
        "CONTINUE",
        "EXPAND_EVIDENCE",
        "ADD_ADVERSARY",
        "CHANGE_STRATEGY",
        "REPLAY_HISTORY",
        "ESCALATE_MODEL",
        "NARROW_SCOPE",
        "ABSTAIN",
        "TERMINATE",
    }
)


def choose_closed_loop_control(
    metacognition: Mapping[str, Any],
    shadow: Mapping[str, Any],
    homeostasis: Mapping[str, Any],
    metabolism: Mapping[str, Any],
    current_round: int,
    maximum_rounds: int,
) -> dict[str, Any]:
    if current_round < 0 or maximum_rounds <= 0 or current_round >= maximum_rounds:
        raise ValueError(
            "closed-loop round bounds are invalid: "
            f"current_round={current_round}, maximum_rounds={maximum_rounds}"
        )
    shadow_decision = str(shadow.get("shadow_decision", "NO_DOWNGRADE"))
    primary = str(metacognition.get("primary_control", "ABSTAIN"))
    secondary = {str(value) for value in metacognition.get("secondary_controls", [])}
    interventions = {str(value) for value in homeostasis.get("interventions", [])}
    if bool(metabolism.get("automatic_low_yield_termination", False)) or shadow_decision == "TERMINATE":
        selected = "TERMINATE"
        action = "terminate_research_episode"
    elif shadow_decision == "ABSTAIN" or primary == "ABSTAIN":
        selected = "ABSTAIN"
        action = "record_abstention_and_await_settlement"
    elif current_round + 1 >= maximum_rounds:
        selected = "NARROW_SCOPE"
        action = "stop_expansion_and_synthesize_current_scope"
    elif "ADD_ADVERSARY" in secondary or shadow_decision == "ADD_ADVERSARY":
        selected = "ADD_ADVERSARY"
        action = "instantiate_advisory_adversary"
    elif "EXPAND_EVIDENCE" in secondary or shadow_decision == "EXPAND_EVIDENCE":
        selected = "EXPAND_EVIDENCE"
        action = "request_typed_missing_evidence"
    elif "REPLAY_HISTORY" in secondary:
        selected = "REPLAY_HISTORY"
        action = "run_isolated_replay"
    elif "expand_missing_world_model_evidence" in interventions:
        selected = "EXPAND_EVIDENCE"
        action = "request_typed_missing_world_model_evidence"
    else:
        selected = "CONTINUE"
        action = "continue_current_bounded_strategy"
    if selected not in ALLOWED_CONTROL_OUTPUTS:
        raise ValueError(f"closed-loop control is outside constitutional vocabulary: selected={selected}")
    body: dict[str, Any] = {
        "artifact_type": "bounded_metacognitive_control",
        "control_loop_version": "dopey-bounded-control-loop-v1",
        "current_round": current_round,
        "maximum_rounds": maximum_rounds,
        "selected_control": selected,
        "automatic_action": action,
        "closed_loop_enabled": True,
        "allowed_control_outputs": sorted(ALLOWED_CONTROL_OUTPUTS),
        "mutable_surfaces": ["research_depth", "agent_selection", "evidence_requests", "replay_count", "early_stopping", "abstention"],
        "protected_surfaces": ["truth", "readiness", "execution_seal", "provenance", "settlement", "autonomous_promotion_thresholds"],
        "may_change_readiness": False,
        "may_promote": False,
        "may_expand_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
