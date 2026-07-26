"""DOPEY research acceleration and cross-client agent control plane."""

from .capabilities import discover_capabilities
from .compounding import build_compounding_plan
from .readiness import build_readiness_acceleration_plan
from .schedule import build_schedule_plan
from .universe import build_universe_expansion_plan, seed_universe_candidates

__all__ = [
    "build_compounding_plan",
    "build_readiness_acceleration_plan",
    "build_schedule_plan",
    "build_universe_expansion_plan",
    "discover_capabilities",
    "seed_universe_candidates",
]
