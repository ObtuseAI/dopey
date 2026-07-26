"""Deterministic parent sampling for mutation population bundles."""
from __future__ import annotations

from .strategy_genome import StrategyGenome


POPULATION_SAMPLER_VERSION = "dopey-population-sampler-v1"


def sample_population_parents(
    genomes: list[StrategyGenome],
    seed: str,
) -> list[StrategyGenome]:
    """Return deterministic parent ordering; no randomness or external state."""
    if not genomes:
        raise ValueError("sample_population_parents requires at least one genome")
    seed_offset = sum(ord(char) for char in seed) % len(genomes)
    ordered = sorted(genomes, key=lambda genome: genome.genome_id)
    return ordered[seed_offset:] + ordered[:seed_offset]
