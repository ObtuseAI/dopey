"""Typed policy for honest per-symbol targeting research."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetingPolicy:
    """Immutable evidence and capacity floors for the shadow targeting lane."""

    minimum_effective_samples: int
    minimum_era_samples: int
    positive_excess_floor: float
    positive_hit_rate_floor: float
    negative_hit_rate_ceiling: float
    maximum_null_p_value: float
    minimum_average_dollar_volume: float
    option_dte_days: int
    maximum_shadow_candidates: int
    maximum_shadow_candidates_per_direction: int
    maximum_symbol_weight: float


def default_targeting_policy() -> TargetingPolicy:
    """Return the versioned conservative targeting policy."""

    return TargetingPolicy(
        minimum_effective_samples=30,
        minimum_era_samples=10,
        positive_excess_floor=0.002,
        positive_hit_rate_floor=0.52,
        negative_hit_rate_ceiling=0.48,
        maximum_null_p_value=0.10,
        minimum_average_dollar_volume=5_000_000.0,
        option_dte_days=30,
        maximum_shadow_candidates=20,
        maximum_shadow_candidates_per_direction=10,
        maximum_symbol_weight=0.10,
    )
