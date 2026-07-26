"""Matched parent/challenger comparison without promotion authority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def compare_challenger(
    parent_fitness: Mapping[str, Any],
    challenger_evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    parent_score = float(parent_fitness.get("fitness_score", 0.0))
    challenger_score = float(challenger_evaluation.get("fitness", {}).get("fitness_score", 0.0))
    gain = challenger_score - parent_score
    return {
        "artifact_type": "matched_genome_challenger_comparison",
        "candidate_id": str(challenger_evaluation["candidate_id"]),
        "parent_fitness_score": parent_score,
        "challenger_fitness_score": challenger_score,
        "observed_fitness_gain": round(gain, 8),
        "challenger_wins": gain > 0.0,
        "comparison_is_not_forward_proof": True,
        "automatic_research_activation_allowed": False,
        "full_promotion_matrix_required": True,
        "paper_only": True,
        "live_blocked": True,
    }
