"""Advisory retirement and quarantine recommendations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .schema import ResearchGenome


def recommend_retirement(
    genome: ResearchGenome,
    fitness: Mapping[str, Any],
    calibration_drift: float,
    provenance_violation: bool,
) -> dict[str, Any]:
    if not 0.0 <= calibration_drift <= 1.0:
        raise ValueError(
            f"calibration drift must be within [0, 1]: calibration_drift={calibration_drift}"
        )
    if provenance_violation:
        recommendation = "QUARANTINED"
        reason = "provenance_violation"
    elif calibration_drift >= 0.25 or float(fitness.get("fitness_score", 0.0)) <= 0.0:
        recommendation = "RETIRED"
        reason = "fitness_or_calibration_deterioration"
    else:
        recommendation = genome.promotion_state.value
        reason = "retain_current_state"
    return {
        "artifact_type": "research_genome_retirement_recommendation",
        "genome_id": genome.genome_id,
        "recommended_state": recommendation,
        "reason": reason,
        "transition_status": "recommended_not_persisted",
        "auto_applied": False,
        "human_review_required": False,
        "automatic_safety_demotion": recommendation in {"QUARANTINED", "RETIRED"},
        "paper_only": True,
        "live_blocked": True,
    }
