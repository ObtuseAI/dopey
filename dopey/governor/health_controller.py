"""Convert fail-closed component health into governor status."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def governor_health(component_statuses: Mapping[str, Any]) -> dict[str, Any]:
    unhealthy = sorted(
        name
        for name, status in component_statuses.items()
        if status in {False, "blocked", "failed", "unknown"}
    )
    return {
        "health_status": "degraded_fail_closed" if unhealthy else "healthy_research_only",
        "unhealthy_components": unhealthy,
        "may_increase_readiness": False,
        "paper_only": True,
        "live_blocked": True,
    }
