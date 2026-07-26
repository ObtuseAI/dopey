"""Conservative genome fitness capped by its weakest evidence dimension."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.protocols.identity import canonical_hash

from .schema import ResearchGenome


def evaluate_genome_fitness(
    genome: ResearchGenome,
    causal_evaluation: Mapping[str, Any],
    calibration_summary: Mapping[str, Any],
    efficiency_score: float,
) -> dict[str, Any]:
    if not 0.0 <= efficiency_score <= 1.0:
        raise ValueError(f"genome efficiency score must be within [0, 1]: efficiency_score={efficiency_score}")
    evaluations = list(causal_evaluation.get("evaluations", []))
    causal_confidence = max((float(record.get("causal_confidence", 0.0)) for record in evaluations), default=0.0)
    transfer = max(
        (
            min(
                float(record.get("symbol_transfer_fraction_positive", 0.0)),
                float(record.get("era_transfer_fraction_positive", 0.0)),
            )
            for record in evaluations
        ),
        default=0.0,
    )
    settled = int(calibration_summary.get("settled_total", 0) or 0)
    expected_error = calibration_summary.get("expected_calibration_error")
    calibration_quality = 0.0 if expected_error is None else max(0.0, 1.0 - float(expected_error))
    sample_quality = min(1.0, settled / max(int(calibration_summary.get("minimum_calibration_sample", 30) or 30), 1))
    dimensions = {
        "causal_confidence": causal_confidence,
        "cross_symbol_era_transfer": transfer,
        "calibration_quality": calibration_quality,
        "settlement_sample_quality": sample_quality,
        "research_efficiency": efficiency_score,
    }
    weakest_name, weakest_value = min(dimensions.items(), key=lambda item: (item[1], item[0]))
    body: dict[str, Any] = {
        "artifact_type": "research_genome_fitness",
        "fitness_version": "dopey-genome-fitness-v1",
        "genome_id": genome.genome_id,
        "dimensions": {name: round(value, 8) for name, value in dimensions.items()},
        "weakest_dimension": weakest_name,
        "fitness_score": round(weakest_value, 8),
        "held_out_validated": any(bool(record.get("cohort_regime_robust", False)) for record in evaluations),
        "optimizer_may_tune_fitness_judge": False,
        "automatic_research_activation_allowed": False,
        "full_promotion_matrix_required": True,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
