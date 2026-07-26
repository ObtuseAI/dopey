"""Constitutionally filtered genome mutation operators."""

from __future__ import annotations

from typing import Any

from dopey.constitution.mutation_protection import assert_mutation_proposal_safe
from dopey.genome.inheritance import inherit_genome
from dopey.genome.schema import ResearchGenome

from .candidate import build_evolution_candidate


def propose_genome_mutation(
    parent: ResearchGenome,
    surface: str,
    value: Any,
    operator_id: str,
) -> dict[str, Any]:
    proposal = {
        "artifact_type": "research_mutation_proposal",
        "surface": surface,
        "operator_id": operator_id,
        "value": value,
        "auto_apply": False,
        "promotion_state": "EXPERIMENTAL",
        "paper_only": True,
        "live_blocked": True,
    }
    assert_mutation_proposal_safe(proposal)
    challenger = inherit_genome(parent, surface, value, operator_id)
    return build_evolution_candidate(parent, challenger, proposal)
