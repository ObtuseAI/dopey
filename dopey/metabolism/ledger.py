"""Immutable research resource ledger."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceUsage:
    data_calls: int
    provider_calls: int
    tokens: int
    cpu_seconds: float
    peak_memory_mb: float
    simulation_count: int
    backtest_count: int
    option_chain_rows: int
    storage_bytes: int
    wall_seconds: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class ResourceBudget:
    maximum_data_calls: int
    maximum_provider_calls: int
    maximum_tokens: int
    maximum_cpu_seconds: float
    maximum_peak_memory_mb: float
    maximum_simulations: int
    maximum_backtests: int
    maximum_option_chain_rows: int
    maximum_storage_bytes: int
    maximum_wall_seconds: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def _ratio(used: int | float, maximum: int | float) -> float:
    if maximum <= 0:
        return 1.0 if used > 0 else 0.0
    return float(used) / float(maximum)


def evaluate_resource_usage(usage: ResourceUsage, budget: ResourceBudget) -> dict[str, Any]:
    ratios = {
        "data_calls": _ratio(usage.data_calls, budget.maximum_data_calls),
        "provider_calls": _ratio(usage.provider_calls, budget.maximum_provider_calls),
        "tokens": _ratio(usage.tokens, budget.maximum_tokens),
        "cpu_seconds": _ratio(usage.cpu_seconds, budget.maximum_cpu_seconds),
        "peak_memory_mb": _ratio(usage.peak_memory_mb, budget.maximum_peak_memory_mb),
        "simulation_count": _ratio(usage.simulation_count, budget.maximum_simulations),
        "backtest_count": _ratio(usage.backtest_count, budget.maximum_backtests),
        "option_chain_rows": _ratio(usage.option_chain_rows, budget.maximum_option_chain_rows),
        "storage_bytes": _ratio(usage.storage_bytes, budget.maximum_storage_bytes),
        "wall_seconds": _ratio(usage.wall_seconds, budget.maximum_wall_seconds),
    }
    exceeded = sorted(name for name, ratio in ratios.items() if ratio > 1.0)
    return {
        "artifact_type": "research_resource_ledger",
        "usage": usage.to_dict(),
        "budget": budget.to_dict(),
        "utilization": {name: round(ratio, 6) for name, ratio in ratios.items()},
        "maximum_utilization": round(max(ratios.values()), 6),
        "budget_exceeded": bool(exceeded),
        "exceeded_dimensions": exceeded,
        "paper_only": True,
        "live_blocked": True,
    }
