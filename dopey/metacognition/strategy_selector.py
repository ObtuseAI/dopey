"""Select bounded research methods from task state."""

from __future__ import annotations

from .state import KnowledgeBoundary


def select_strategy(
    objective_type: str,
    boundary: KnowledgeBoundary,
    difficulty_level: str,
) -> str:
    if boundary == KnowledgeBoundary.OUTSIDE_AUTHORITY:
        return "terminate_outside_authority"
    if boundary == KnowledgeBoundary.UNKNOWN:
        return "evidence_gap_mapping_and_historical_replay"
    if difficulty_level == "HIGH":
        return "fixed_template_with_adversarial_replay"
    if objective_type == "breakout":
        return "deterministic_breakout_organism"
    return "deterministic_general_research_organism"
