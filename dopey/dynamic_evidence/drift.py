"""Conservative empirical distribution-shift diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def _ks_statistic(reference: Sequence[float], recent: Sequence[float]) -> float:
    reference_sorted = sorted(reference)
    recent_sorted = sorted(recent)
    values = sorted(set(reference_sorted + recent_sorted))
    reference_index = 0
    recent_index = 0
    maximum_distance = 0.0
    for value in values:
        while reference_index < len(reference_sorted) and reference_sorted[reference_index] <= value:
            reference_index += 1
        while recent_index < len(recent_sorted) and recent_sorted[recent_index] <= value:
            recent_index += 1
        distance = abs(
            reference_index / len(reference_sorted)
            - recent_index / len(recent_sorted)
        )
        maximum_distance = max(maximum_distance, distance)
    return maximum_distance


def empirical_distribution_shift(
    reference_values: Sequence[float],
    recent_values: Sequence[float],
    detection_alpha: float,
    minimum_window_size: int,
) -> dict[str, Any]:
    """Compare two bounded windows with a two-sample KS-style threshold."""

    reference = tuple(float(value) for value in reference_values)
    recent = tuple(float(value) for value in recent_values)
    invalid = tuple(
        value
        for value in (*reference, *recent)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0
    )
    if invalid:
        raise ValueError(f"distribution-shift inputs must be finite and within [0, 1]: invalid={invalid[:5]}")
    if not 0.0 < detection_alpha < 1.0:
        raise ValueError(f"distribution-shift alpha must be within (0, 1): alpha={detection_alpha}")
    if minimum_window_size <= 1:
        raise ValueError(
            "distribution-shift minimum window must exceed one observation: "
            f"minimum_window_size={minimum_window_size}"
        )
    if len(reference) < minimum_window_size or len(recent) < minimum_window_size:
        return {
            "status": "insufficient_nonoverlapping_windows",
            "method": "two_sample_empirical_cdf_distance",
            "reference_count": len(reference),
            "recent_count": len(recent),
            "minimum_window_size": minimum_window_size,
            "drift_detected": False,
            "risk_score": 1.0,
            "change_point_claim_allowed": False,
            "may_increase_readiness": False,
        }
    statistic = _ks_statistic(reference, recent)
    threshold = math.sqrt(
        -0.5 * math.log(detection_alpha / 2.0)
        * (1.0 / len(reference) + 1.0 / len(recent))
    )
    detected = statistic > threshold
    mean_shift = sum(recent) / len(recent) - sum(reference) / len(reference)
    return {
        "status": "distribution_shift_detected" if detected else "no_detected_distribution_shift",
        "method": "two_sample_empirical_cdf_distance",
        "reference_count": len(reference),
        "recent_count": len(recent),
        "detection_alpha": detection_alpha,
        "statistic": round(statistic, 10),
        "threshold": round(threshold, 10),
        "mean_shift": round(mean_shift, 10),
        "drift_detected": detected,
        "risk_score": round(min(1.0, statistic / max(threshold, 1e-12)), 10),
        "iid_bound_not_claimed_for_financial_time_series": True,
        "change_point_claim_allowed": False,
        "routing_and_abstention_use_only": True,
        "may_increase_readiness": False,
    }
