"""Build immutable health telemetry from one organism episode."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.protocols.identity import canonical_hash


def build_health_state(
    world_model: Mapping[str, Any],
    metacognition: Mapping[str, Any],
    resource_ledger: Mapping[str, Any],
    settlement_pending: bool,
    strategy_concentration: float,
    operational_metrics: Mapping[str, float],
) -> dict[str, Any]:
    known = int(world_model.get("known_dimension_count", 0) or 0)
    unknown = int(world_model.get("unknown_dimension_count", 0) or 0)
    total = max(known + unknown, 1)
    confidence = metacognition.get("confidence", {})
    variables: dict[str, float] = {
        "data_freshness": float(confidence.get("evidence_freshness", 0.0) or 0.0),
        "signal_diversity": 1.0 - float(confidence.get("agent_disagreement", 1.0) or 1.0),
        "strategy_concentration": strategy_concentration,
        "calibration_quality": float(confidence.get("calibration_quality", 0.0) or 0.0),
        "agent_disagreement": float(confidence.get("agent_disagreement", 1.0) or 1.0),
        "resource_pressure": min(1.0, float(resource_ledger.get("maximum_utilization", 0.0) or 0.0)),
        "settlement_completion": 0.0 if settlement_pending else 1.0,
        "world_model_coverage": known / total,
        "lane_completion": float(operational_metrics.get("lane_completion", 0.0)),
        "option_chain_continuity": float(operational_metrics.get("option_chain_continuity", 0.0)),
        "universe_health": float(operational_metrics.get("universe_health", 0.0)),
        "model_dependence": float(operational_metrics.get("model_dependence", 0.0)),
        "archive_diversity": float(operational_metrics.get("archive_diversity", 0.0)),
        "research_backlog_pressure": float(operational_metrics.get("research_backlog_pressure", 0.0)),
        "phantom_signal_coverage": float(operational_metrics.get("phantom_signal_coverage", 0.0)),
    }
    invalid = {name: value for name, value in variables.items() if not 0.0 <= value <= 1.0}
    if invalid:
        raise ValueError(f"homeostasis variables must be within [0, 1]: invalid={invalid}")
    body: dict[str, Any] = {
        "artifact_type": "research_homeostasis_state",
        "homeostasis_version": "dopey-homeostasis-v2",
        "variables": {name: round(value, 6) for name, value in variables.items()},
        "paper_only": True,
        "live_blocked": True,
        "automatic_protected_surface_mutation": False,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
