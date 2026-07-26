"""Ensure exposed confidence obeys the conservative cap."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def inspect_calibration(metacognition: Mapping[str, Any]) -> dict[str, Any]:
    confidence = metacognition.get("confidence", {})
    final = float(confidence.get("final_research_confidence", 0.0) or 0.0)
    weakest = float(confidence.get("weakest_critical_value", 0.0) or 0.0)
    violations = [] if final <= weakest else ["final_confidence_exceeds_weakest_critical_dimension"]
    return {
        "guard": "calibration_guard",
        "status": "veto" if violations else "pass",
        "violations": violations,
        "may_increase_readiness": False,
    }
