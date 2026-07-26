"""Evaluate health and emit advisory-only interventions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .health_state import build_health_state
from .interventions import recommend_interventions


def evaluate_homeostasis(
    world_model: Mapping[str, Any],
    metacognition: Mapping[str, Any],
    resource_ledger: Mapping[str, Any],
    settlement_pending: bool,
    strategy_concentration: float,
    operational_metrics: Mapping[str, float],
) -> dict[str, Any]:
    state = build_health_state(
        world_model,
        metacognition,
        resource_ledger,
        settlement_pending,
        strategy_concentration,
        operational_metrics,
    )
    interventions = recommend_interventions(state["variables"])
    return {
        **state,
        "health_status": "intervention_recommended" if interventions else "stable_research_only",
        "interventions": interventions,
        "interventions_auto_applied": False,
        "human_review_required": False,
        "automatic_application_policy": "bounded_runtime_controls_only",
        "promotion_threshold_effect": "none",
    }
