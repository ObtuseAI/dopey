"""Metacognitive interpretation of resource utility."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.metabolism.cost_model import normalized_resource_cost
from dopey.metabolism.marginal_utility import research_utility


def evaluate_research_utility(
    information_gain: float,
    evidence_quality: float,
    resource_ledger: Mapping[str, Any],
    duplication_penalty: float,
    uncertainty_penalty: float,
) -> float:
    utilization = resource_ledger.get("utilization", {})
    if not isinstance(utilization, Mapping):
        raise TypeError("resource ledger utilization must be a mapping")
    cost = normalized_resource_cost({str(key): float(value) for key, value in utilization.items()})
    return research_utility(
        information_gain,
        information_gain,
        evidence_quality,
        cost,
        duplication_penalty,
        uncertainty_penalty,
    )
