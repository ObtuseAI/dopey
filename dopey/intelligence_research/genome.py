"""Content-addressed inheritance record for validated cognitive architecture."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dopey.protocols.identity import canonical_hash


def build_cognitive_genome(
    parent_genome_ids: tuple[str, ...],
    generation: int,
    reasoning_method_ids: Sequence[str],
    research_method_ids: Sequence[str],
    creativity_operators: Sequence[str],
    planning_method_ids: Sequence[str],
    evaluation_method_ids: Sequence[str],
    memory_policy_ids: Sequence[str],
    organization_method_ids: Sequence[str],
) -> dict[str, Any]:
    if generation < 0:
        raise ValueError(f"cognitive genome generation cannot be negative: generation={generation}")
    collections = {
        "reasoning_method_ids": reasoning_method_ids,
        "research_method_ids": research_method_ids,
        "creativity_operators": creativity_operators,
        "planning_method_ids": planning_method_ids,
        "evaluation_method_ids": evaluation_method_ids,
        "memory_policy_ids": memory_policy_ids,
        "organization_method_ids": organization_method_ids,
    }
    empty = sorted(name for name, values in collections.items() if not values)
    if empty:
        raise ValueError(f"cognitive genome requires every cognitive family: empty={empty}")
    duplicates = sorted(name for name, values in collections.items() if len(values) != len(set(values)))
    if duplicates:
        raise ValueError(f"cognitive genome families contain duplicates: fields={duplicates}")
    body: dict[str, Any] = {
        "artifact_type": "cognitive_architecture_genome",
        "genome_version": "dopey-cognitive-genome-v1",
        "parent_genome_ids": list(parent_genome_ids),
        "generation": generation,
        **{name: list(values) for name, values in collections.items()},
        "candidate_self_activation_allowed": False,
        "authority_surfaces_evolvable": False,
        "truth_surfaces_evolvable": False,
        "paper_only": True,
        "live_blocked": True,
    }
    content_hash = canonical_hash(body)
    return {**body, "genome_id": f"cognitive-genome:{content_hash[:24]}", "content_hash": content_hash}
