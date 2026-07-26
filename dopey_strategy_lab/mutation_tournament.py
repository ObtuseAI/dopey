"""Dopey mutation tournament: deterministic genome tournament (research stub).

DOPEY-native stub. Runs a small deterministic tournament over mutated genomes; returns ranked
candidates. No live exec.
"""
from __future__ import annotations

from dopey_core.mutation_engine import mutate_genome, genome_hash
from .strategy_genome import StrategyGenome


def run_mutation_tournament(base_genome: StrategyGenome, field_paths: list[str],
                            deltas: list[float], score_fn) -> list[dict]:
    """score_fn(genome_dict) -> float. Returns ranked [{genome, hash, score}]."""
    rows = []
    for d in deltas:
        g = mutate_genome(base_genome.to_dict(), field_paths, d)
        rows.append({"genome": g, "hash": genome_hash(g), "score": round(score_fn(g), 6), "delta": d})
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows
