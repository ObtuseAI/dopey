"""Shadow-only proposals for improving the evolution process."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.constitution.mutation_protection import assert_mutation_proposal_safe


META_EVOLVABLE_SURFACES: frozenset[str] = frozenset(
    {"stopping_policies", "calibration_models", "morphology_rules", "evidence_budgets", "disagreement_resolution"}
)


def validate_meta_evolution_proposal(proposal: Mapping[str, Any]) -> dict[str, Any]:
    assert_mutation_proposal_safe(proposal)
    surface = str(proposal["surface"])
    if surface not in META_EVOLVABLE_SURFACES:
        raise ValueError(f"surface is not eligible for meta-evolution: surface={surface}")
    return {
        **dict(proposal),
        "recursive_level": 5,
        "validated_for": "isolated_shadow_replay_only",
        "evaluator_mutation_allowed": False,
        "human_review_required": False,
        "protected_evaluator_required": True,
        "automatic_research_activation_allowed": False,
        "readiness_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
