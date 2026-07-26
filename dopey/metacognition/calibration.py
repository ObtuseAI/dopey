"""Translate settlement evidence into conservative calibration quality."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def calibration_state(summary: Mapping[str, Any]) -> dict[str, float | int | str]:
    settled = int(summary.get("settled_total", 0) or 0)
    contested = int(summary.get("contested_total", 0) or 0)
    if settled <= 0:
        return {
            "status": "uncalibrated_no_settlements",
            "settled_total": 0,
            "contested_total": 0,
            "sample_size_score": 0.0,
            "calibration_quality": 0.0,
        }
    sample_score = min(1.0, math.log10(settled + 1) / 5.0)
    contested_fraction = min(1.0, contested / max(settled, 1))
    has_calibration_error = summary.get("expected_calibration_error") is not None
    if has_calibration_error:
        error = float(summary["expected_calibration_error"])
        quality = max(0.0, 1.0 - error)
        status = "calibration_error_available"
    else:
        quality = min(0.45, 0.25 + 0.2 * contested_fraction)
        status = "settlement_accuracy_available_but_probability_calibration_missing"
    return {
        "status": status,
        "settled_total": settled,
        "contested_total": contested,
        "sample_size_score": round(sample_score, 6),
        "calibration_quality": round(quality, 6),
    }
