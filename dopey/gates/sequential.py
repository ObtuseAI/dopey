"""Anytime-valid and conformal primitives for continuously inspected research."""

from __future__ import annotations

import math
from collections.abc import Sequence


def confidence_sequence(values: Sequence[float], alpha: float) -> dict[str, float | int | str]:
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"confidence sequence alpha must be within (0, 1): alpha={alpha}")
    if not values:
        return {"status": "insufficient_observations", "sample_count": 0, "mean": 0.0, "lower": 0.0, "upper": 1.0, "alpha": alpha}
    invalid = tuple(value for value in values if not math.isfinite(value) or not 0.0 <= value <= 1.0)
    if invalid:
        raise ValueError(f"confidence sequence values must be finite and within [0, 1]: invalid={invalid[:5]}")
    count = len(values)
    allocated_alpha = alpha / (count * (count + 1))
    radius = math.sqrt(math.log(2.0 / allocated_alpha) / (2.0 * count))
    mean = sum(values) / count
    return {
        "status": "anytime_valid_union_bound",
        "sample_count": count,
        "mean": round(mean, 10),
        "lower": round(max(0.0, mean - radius), 10),
        "upper": round(min(1.0, mean + radius), 10),
        "alpha": alpha,
    }


def online_alpha_budget(family_alpha: float, test_index: int) -> dict[str, float | int]:
    if not 0.0 < family_alpha < 1.0 or test_index <= 0:
        raise ValueError(f"online alpha budget requires family_alpha in (0, 1) and positive index: alpha={family_alpha}, index={test_index}")
    allocation = family_alpha / (test_index * (test_index + 1))
    spent_upper_bound = family_alpha * (1.0 - 1.0 / (test_index + 1))
    return {"test_index": test_index, "test_alpha": allocation, "spent_upper_bound": spent_upper_bound, "family_alpha": family_alpha}


def conformal_abstention_threshold(nonconformity_scores: Sequence[float], alpha: float) -> dict[str, float | int | str]:
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"conformal alpha must be within (0, 1): alpha={alpha}")
    if not nonconformity_scores:
        return {"status": "insufficient_calibration_scores", "sample_count": 0, "threshold": 1.0, "alpha": alpha}
    invalid = tuple(score for score in nonconformity_scores if not math.isfinite(score) or not 0.0 <= score <= 1.0)
    if invalid:
        raise ValueError(f"conformal scores must be finite and within [0, 1]: invalid={invalid[:5]}")
    ordered = sorted(nonconformity_scores)
    rank = math.ceil((len(ordered) + 1) * (1.0 - alpha))
    threshold = 1.0 if rank > len(ordered) else ordered[max(0, rank - 1)]
    return {"status": "finite_sample_split_conformal", "sample_count": len(ordered), "threshold": threshold, "alpha": alpha}
