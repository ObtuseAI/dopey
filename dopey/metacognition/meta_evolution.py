"""Validate metacognitive changes as shadow-only mutation proposals."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.constitution.mutation_protection import assert_mutation_proposal_safe


def validate_metacognitive_mutation(proposal: Mapping[str, Any]) -> dict[str, Any]:
    assert_mutation_proposal_safe(proposal)
    if proposal.get("surface") not in {"calibration_models", "stopping_policies", "disagreement_resolution"}:
        raise ValueError(
            "proposal is not a metacognitive evolvable surface: "
            f"surface={proposal.get('surface')}"
        )
    return {
        **dict(proposal),
        "validated_for": "isolated_shadow_replay_only",
        "human_review_required": False,
        "protected_evaluator_required": True,
        "automatic_research_activation_allowed": False,
        "readiness_effect": "none",
    }
