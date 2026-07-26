"""Normalize multidimensional resource cost."""

from __future__ import annotations

from collections.abc import Mapping


def normalized_resource_cost(utilization: Mapping[str, float]) -> float:
    if not utilization:
        return 0.0
    invalid = {name: value for name, value in utilization.items() if value < 0.0}
    if invalid:
        raise ValueError(f"resource utilization cannot be negative: invalid={invalid}")
    capped = [min(float(value), 1.5) / 1.5 for value in utilization.values()]
    return round(sum(capped) / len(capped), 6)
