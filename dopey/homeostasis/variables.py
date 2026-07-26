"""Health-variable names monitored by the vNext vertical slice."""

from __future__ import annotations


HEALTH_VARIABLES: tuple[str, ...] = (
    "data_freshness",
    "signal_diversity",
    "strategy_concentration",
    "calibration_quality",
    "agent_disagreement",
    "resource_pressure",
    "settlement_completion",
    "world_model_coverage",
)
