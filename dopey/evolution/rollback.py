"""Immutable rollback plan for research-genome state transitions."""

from __future__ import annotations

from dopey.genome.schema import ResearchGenome
from dopey.protocols.identity import canonical_hash


def build_rollback_plan(
    current: ResearchGenome,
    prior: ResearchGenome,
    reason: str,
) -> dict[str, object]:
    if prior.genome_id not in current.parent_ids:
        raise ValueError(
            "rollback target must be a direct immutable parent: "
            f"current={current.genome_id}, prior={prior.genome_id}"
        )
    if not reason:
        raise ValueError("rollback plan requires an explicit reason")
    body: dict[str, object] = {
        "artifact_type": "research_genome_rollback_plan",
        "rollback_version": "dopey-genome-rollback-v1",
        "current_genome_id": current.genome_id,
        "restore_genome_id": prior.genome_id,
        "reason": reason,
        "source_data_mutation_required": False,
        "human_review_required": False,
        "transition_status": "proposed_not_persisted",
        "auto_applied": False,
        "automatic_safety_rollback": True,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "rollback_hash": canonical_hash(body)}
