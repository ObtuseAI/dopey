"""Anytime-valid bounded-mean evidence and explicit e-value FDR controls."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def _finite_values(values: Sequence[float], label: str) -> tuple[float, ...]:
    normalized = tuple(float(value) for value in values)
    invalid = tuple(value for value in normalized if not math.isfinite(value))
    if invalid:
        raise ValueError(f"{label} must contain only finite values: invalid={invalid[:5]}")
    return normalized


def bounded_mean_e_process(
    observations: Sequence[float],
    null_mean: float,
    betting_fraction: float,
    evidence_alpha: float,
) -> dict[str, Any]:
    """Build a Hoeffding e-process for bounded observations under a mean null."""

    values = _finite_values(observations, "bounded e-process observations")
    if not 0.0 <= null_mean <= 1.0:
        raise ValueError(f"bounded e-process null mean must be within [0, 1]: null_mean={null_mean}")
    if betting_fraction < 0.0 or not math.isfinite(betting_fraction):
        raise ValueError(
            "bounded e-process betting fraction must be finite and nonnegative: "
            f"betting_fraction={betting_fraction}"
        )
    if not 0.0 < evidence_alpha < 1.0:
        raise ValueError(f"bounded e-process alpha must be within (0, 1): alpha={evidence_alpha}")
    outside = tuple(value for value in values if not 0.0 <= value <= 1.0)
    if outside:
        raise ValueError(f"bounded e-process observations must be within [0, 1]: invalid={outside[:5]}")
    log_trajectory: list[float] = []
    running_log_e_value = 0.0
    first_crossing_index: int | None = None
    crossing_log_threshold = math.log(1.0 / evidence_alpha)
    for index, value in enumerate(values, start=1):
        running_log_e_value += (
            betting_fraction * (value - null_mean)
            - betting_fraction * betting_fraction / 8.0
        )
        log_trajectory.append(round(running_log_e_value, 12))
        if first_crossing_index is None and running_log_e_value >= crossing_log_threshold:
            first_crossing_index = index
    terminal_log_e_value = log_trajectory[-1] if log_trajectory else 0.0
    overflow_capped = terminal_log_e_value > 700.0
    terminal_e_value = math.exp(min(terminal_log_e_value, 700.0))
    return {
        "status": "evidence_threshold_crossed" if first_crossing_index is not None else "evidence_not_decisive",
        "method": "hoeffding_bounded_mean_e_process",
        "sample_count": len(values),
        "null_mean": null_mean,
        "betting_fraction": betting_fraction,
        "evidence_alpha": evidence_alpha,
        "terminal_log_e_value": terminal_log_e_value,
        "terminal_e_value": round(terminal_e_value, 12),
        "overflow_capped": overflow_capped,
        "first_crossing_index": first_crossing_index,
        "log_e_value_trajectory": tuple(log_trajectory),
        "assumption": "observations_are_bounded_and_conditional_mean_under_null_is_at_most_null_mean",
        "may_bypass_minimum_sample_gate": False,
        "may_increase_readiness": False,
    }


def e_lond_decisions(e_values: Sequence[float], family_alpha: float) -> dict[str, Any]:
    """Apply e-LOND with a summable gamma sequence under arbitrary dependence."""

    values = _finite_values(e_values, "e-LOND values")
    if not 0.0 < family_alpha < 1.0:
        raise ValueError(f"e-LOND family alpha must be within (0, 1): family_alpha={family_alpha}")
    invalid = tuple(value for value in values if value < 0.0)
    if invalid:
        raise ValueError(f"e-LOND values must be nonnegative: invalid={invalid[:5]}")
    discoveries = 0
    decisions: list[dict[str, float | int | bool]] = []
    for test_index, e_value in enumerate(values, start=1):
        gamma = 1.0 / (test_index * (test_index + 1.0))
        test_alpha = family_alpha * gamma * (discoveries + 1)
        rejection_threshold = 1.0 / test_alpha
        rejected = e_value >= rejection_threshold
        if rejected:
            discoveries += 1
        decisions.append(
            {
                "test_index": test_index,
                "e_value": e_value,
                "gamma": round(gamma, 12),
                "test_alpha": round(test_alpha, 12),
                "rejection_threshold": round(rejection_threshold, 12),
                "rejected": rejected,
                "discoveries_after_test": discoveries,
            }
        )
    return {
        "status": "discoveries_require_independent_adversarial_confirmation" if discoveries else "no_online_discoveries",
        "method": "e_lond_summable_gamma",
        "family_alpha": family_alpha,
        "test_count": len(values),
        "discovery_count": discoveries,
        "decisions": tuple(decisions),
        "arbitrary_dependence_supported_by_method": True,
        "input_e_values_must_be_independently_valid": True,
        "may_bypass_minimum_sample_gate": False,
        "may_promote": False,
        "may_increase_readiness": False,
    }
