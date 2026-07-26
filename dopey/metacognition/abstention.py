"""Fail-closed research continuation and abstention policy."""

from __future__ import annotations

from .state import ControlOutput, KnowledgeBoundary


def choose_control_output(
    boundary: KnowledgeBoundary,
    final_confidence: float,
    information_gain: float,
    resource_utility: float,
    budget_exceeded: bool,
) -> ControlOutput:
    if boundary == KnowledgeBoundary.OUTSIDE_AUTHORITY:
        return ControlOutput.TERMINATE
    if budget_exceeded:
        return ControlOutput.TERMINATE
    if resource_utility <= 0.0 or information_gain < 0.1:
        return ControlOutput.ABSTAIN
    if boundary == KnowledgeBoundary.UNKNOWN:
        return ControlOutput.EXPAND_EVIDENCE
    if final_confidence < 0.45:
        return ControlOutput.ABSTAIN
    if final_confidence < 0.6:
        return ControlOutput.ADD_ADVERSARY
    return ControlOutput.CONTINUE
