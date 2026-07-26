"""Diversity-aware experimental population construction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_population(candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(candidate["candidate_id"]): candidate for candidate in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("evolution population contains duplicate candidate identities")
    challenger_genome_ids = [
        str(candidate["challenger_genome"]["genome_id"]) for candidate in candidates
    ]
    if len(challenger_genome_ids) != len(set(challenger_genome_ids)):
        raise ValueError("evolution population contains duplicate challenger genomes")
    surfaces = {
        str(candidate["mutation_proposal"]["surface"]) for candidate in candidates
    }
    parents = {str(candidate["parent_genome_id"]) for candidate in candidates}
    diversity = len(surfaces) / max(len(candidates), 1)
    return {
        "artifact_type": "research_evolution_population",
        "population_version": "dopey-evolution-population-v1",
        "candidate_count": len(candidates),
        "parent_count": len(parents),
        "mutation_surface_count": len(surfaces),
        "archive_diversity": round(diversity, 8),
        "candidate_ids": sorted(by_id),
        "challenger_genome_ids": sorted(challenger_genome_ids),
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
