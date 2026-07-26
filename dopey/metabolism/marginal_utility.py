"""Research utility and automatic low-yield termination policy."""

from __future__ import annotations


def research_utility(
    information_gain: float,
    expected_learning_value: float,
    evidence_quality: float,
    resource_cost: float,
    duplication_penalty: float,
    uncertainty_penalty: float,
) -> float:
    values = {
        "information_gain": information_gain,
        "expected_learning_value": expected_learning_value,
        "evidence_quality": evidence_quality,
        "resource_cost": resource_cost,
        "duplication_penalty": duplication_penalty,
        "uncertainty_penalty": uncertainty_penalty,
    }
    invalid = {name: value for name, value in values.items() if not 0.0 <= value <= 1.0}
    if invalid:
        raise ValueError(f"research utility inputs must be within [0, 1]: invalid={invalid}")
    positive = information_gain + expected_learning_value + evidence_quality
    negative = resource_cost + duplication_penalty + uncertainty_penalty
    return round(max(-1.0, min(1.0, (positive - negative) / 3.0)), 6)


def should_terminate_low_yield(utility: float, budget_exceeded: bool) -> bool:
    if not -1.0 <= utility <= 1.0:
        raise ValueError(f"research utility must be within [-1, 1]: utility={utility}")
    return budget_exceeded or utility <= 0.0
