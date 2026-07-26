"""Adaptive, past-only conformal miscoverage monitoring."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def _conformal_threshold(scores: Sequence[float], alpha: float) -> float:
    ordered = sorted(scores)
    rank = math.ceil((len(ordered) + 1) * (1.0 - alpha))
    return 1.0 if rank > len(ordered) else float(ordered[max(rank - 1, 0)])


def adaptive_conformal_monitor(
    nonconformity_scores: Sequence[float],
    target_error_rate: float,
    learning_rate: float,
    minimum_calibration_size: int,
    calibration_window: int,
    recent_error_window: int,
    maximum_recent_error_rate: float,
    alpha_floor: float,
    alpha_ceiling: float,
) -> dict[str, Any]:
    """Monitor sequential miscoverage without using a score to calibrate itself."""

    scores = tuple(float(score) for score in nonconformity_scores)
    invalid = tuple(
        score for score in scores if not math.isfinite(score) or not 0.0 <= score <= 1.0
    )
    if invalid:
        raise ValueError(f"adaptive conformal scores must be finite and within [0, 1]: invalid={invalid[:5]}")
    if not 0.0 < target_error_rate < 1.0:
        raise ValueError(
            "adaptive conformal target error must be within (0, 1): "
            f"target_error_rate={target_error_rate}"
        )
    if learning_rate <= 0.0 or not math.isfinite(learning_rate):
        raise ValueError(f"adaptive conformal learning rate must be positive: learning_rate={learning_rate}")
    if minimum_calibration_size <= 0 or calibration_window < minimum_calibration_size:
        raise ValueError(
            "adaptive conformal window must cover its positive calibration minimum: "
            f"minimum={minimum_calibration_size}, window={calibration_window}"
        )
    if recent_error_window <= 0:
        raise ValueError(
            "adaptive conformal recent error window must be positive: "
            f"recent_error_window={recent_error_window}"
        )
    if not target_error_rate <= maximum_recent_error_rate <= 1.0:
        raise ValueError(
            "adaptive conformal maximum recent error must be between target and 1: "
            f"target={target_error_rate}, maximum={maximum_recent_error_rate}"
        )
    if not 0.0 < alpha_floor <= target_error_rate <= alpha_ceiling < 1.0:
        raise ValueError(
            "adaptive conformal alpha bounds must contain the target inside (0, 1): "
            f"floor={alpha_floor}, target={target_error_rate}, ceiling={alpha_ceiling}"
        )
    current_alpha = target_error_rate
    errors: list[int] = []
    trace: list[dict[str, float | int | str]] = []
    for index, score in enumerate(scores):
        if index < minimum_calibration_size:
            trace.append(
                {
                    "sequence_index": index + 1,
                    "status": "calibration_warmup",
                    "score": score,
                    "alpha_before": round(current_alpha, 10),
                }
            )
            continue
        calibration_start = max(0, index - calibration_window)
        calibration_scores = scores[calibration_start:index]
        threshold = _conformal_threshold(calibration_scores, current_alpha)
        error = int(score > threshold)
        errors.append(error)
        next_alpha = min(
            alpha_ceiling,
            max(alpha_floor, current_alpha + learning_rate * (target_error_rate - error)),
        )
        trace.append(
            {
                "sequence_index": index + 1,
                "status": "evaluated_past_only",
                "score": score,
                "threshold": round(threshold, 10),
                "error": error,
                "alpha_before": round(current_alpha, 10),
                "alpha_after": round(next_alpha, 10),
                "calibration_count": len(calibration_scores),
            }
        )
        current_alpha = next_alpha
    recent_errors = errors[-recent_error_window:]
    recent_error_rate = sum(recent_errors) / len(recent_errors) if recent_errors else None
    total_error_rate = sum(errors) / len(errors) if errors else None
    if not errors:
        status = "insufficient_calibration_scores"
    elif recent_error_rate is not None and recent_error_rate > maximum_recent_error_rate:
        status = "adaptive_miscoverage_detected"
    else:
        status = "adaptive_monitoring_nominal"
    return {
        "status": status,
        "method": "bounded_adaptive_conformal_controller",
        "sample_count": len(scores),
        "evaluated_count": len(errors),
        "target_error_rate": target_error_rate,
        "maximum_recent_error_rate": maximum_recent_error_rate,
        "total_error_rate": None if total_error_rate is None else round(total_error_rate, 10),
        "recent_error_rate": None if recent_error_rate is None else round(recent_error_rate, 10),
        "final_alpha": round(current_alpha, 10),
        "trace": tuple(trace),
        "uses_only_prior_scores_for_each_threshold": True,
        "coverage_guarantee_claimed": False,
        "financial_time_dependence_requires_empirical_validation": True,
        "may_increase_readiness": False,
    }
