"""Dopey champion registry: in-memory champion genome registry (research stub).

DOPEY-native stub. Records promoted champion genomes by family. No live exec.
"""
from __future__ import annotations

from .strategy_genome import StrategyGenome


class ChampionRegistry:
    def __init__(self):
        self._by_family: dict[str, StrategyGenome] = {}

    def register(self, genome: StrategyGenome) -> None:
        self._by_family[genome.family] = genome

    def get(self, family: str) -> StrategyGenome | None:
        return self._by_family.get(family)

    def all_champions(self) -> list[StrategyGenome]:
        return list(self._by_family.values())
