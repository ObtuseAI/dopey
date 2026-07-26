"""Decomposed confidence with a weakest-critical-dimension cap."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ConfidenceDimensions:
    model: float
    evidence_completeness: float
    evidence_freshness: float
    historical_analogue_quality: float
    calibration_quality: float
    causal_confidence: float
    agent_disagreement: float
    regime_familiarity: float
    settlement_sample_size: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def aggregate_confidence(dimensions: ConfidenceDimensions) -> dict[str, Any]:
    values = dimensions.to_dict()
    invalid = {name: value for name, value in values.items() if not 0.0 <= value <= 1.0}
    if invalid:
        raise ValueError(f"confidence dimensions must be within [0, 1]: invalid={invalid}")
    critical = {
        name: value
        for name, value in values.items()
        if name != "agent_disagreement"
    }
    weakest_name, weakest_value = min(critical.items(), key=lambda item: (item[1], item[0]))
    disagreement_penalty = 1.0 - 0.5 * dimensions.agent_disagreement
    final = min(weakest_value, sum(critical.values()) / len(critical)) * disagreement_penalty
    return {
        **values,
        "weakest_critical_dimension": weakest_name,
        "weakest_critical_value": round(weakest_value, 6),
        "disagreement_penalty": round(disagreement_penalty, 6),
        "final_research_confidence": round(final, 6),
        "aggregation_rule": "minimum_critical_dimension_capped_then_disagreement_penalized",
        "not_readiness_score": True,
    }
