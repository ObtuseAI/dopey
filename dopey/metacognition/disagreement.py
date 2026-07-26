"""Quantify hypothesis disagreement without treating consensus as proof."""

from __future__ import annotations

from collections.abc import Sequence


def disagreement_score(hypothesis_probabilities: Sequence[float]) -> float:
    if not hypothesis_probabilities:
        return 1.0
    invalid = [value for value in hypothesis_probabilities if not 0.0 <= value <= 1.0]
    if invalid:
        raise ValueError(f"hypothesis probabilities must be within [0, 1]: invalid={invalid}")
    total = sum(hypothesis_probabilities)
    if total <= 0.0:
        return 1.0
    normalized = [value / total for value in hypothesis_probabilities]
    maximum = max(normalized)
    return round(1.0 - maximum, 6)
