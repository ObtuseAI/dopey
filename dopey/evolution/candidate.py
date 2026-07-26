"""Immutable experimental challenger records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.genome.schema import ResearchGenome
from dopey.protocols.identity import canonical_hash


def build_evolution_candidate(
    parent: ResearchGenome,
    challenger: ResearchGenome,
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    if challenger.parent_ids != (parent.genome_id,):
        raise ValueError(
            "evolution challenger must directly inherit from parent: "
            f"parent={parent.genome_id}, challenger_parents={challenger.parent_ids}"
        )
    body: dict[str, Any] = {
        "artifact_type": "research_evolution_candidate",
        "candidate_version": "dopey-evolution-candidate-v1",
        "parent_genome_id": parent.genome_id,
        "challenger_genome": challenger.to_dict(),
        "mutation_proposal": dict(proposal),
        "promotion_state": "EXPERIMENTAL",
        "isolated_replay_required": True,
        "human_review_required": False,
        "protected_evaluator_required": True,
        "candidate_self_activation_allowed": False,
        "auto_apply": False,
        "paper_only": True,
        "live_blocked": True,
    }
    content_hash = canonical_hash(body)
    return {**body, "candidate_id": f"evolution-candidate:{content_hash[:24]}", "content_hash": content_hash}
