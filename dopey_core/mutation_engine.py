"""Dopey mutation engine: strategy-genome mutation primitives (research-only, deterministic).

DOPEY-native module (not directly forked from a single Blunder file, but follows the
Blunder self-improvement doctrine: recommend-only, proof-gated, no safety weakening). The
mutation primitives here are used by dopey_strategy_lab to generate candidate genomes for
walk-forward validation. They NEVER place trades and NEVER weaken the live-order gate.

DOPEY lineage: Blunder self-improvement doctrine (recommend-only) -> dopey_core.mutation_engine
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def mutate_field(value: Any, delta: float) -> Any:
    """Apply a bounded numeric perturbation to a scalar value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return type(value)(round(value * (1.0 + delta), 8))
    return value


def mutate_genome(genome: dict, field_paths: list[str], delta: float) -> dict:
    """Return a deep-copied genome with the given dot-path fields perturbed by `delta`.
    No in-place mutation; original genome is untouched. Deterministic given the same inputs."""
    g = copy.deepcopy(genome)
    for path in field_paths:
        parts = path.split(".")
        cur: Any = g
        for p in parts[:-1]:
            if not isinstance(cur, dict) or p not in cur:
                cur = None
                break
            cur = cur[p]
        if isinstance(cur, dict) and parts[-1] in cur:
            cur[parts[-1]] = mutate_field(cur[parts[-1]], delta)
    return g


def genome_hash(genome: dict) -> str:
    """Stable content hash of a genome dict (sorted keys) for proof-ledger lineage."""
    return hashlib.sha256(json.dumps(genome, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def mutation_recommendation(genome: dict, weak_signals: list[str]) -> dict:
    """Recommend (do not auto-apply) mutation candidates based on weak-signal starving input.
    The output is a recommendation record only; promotion requires proof-ledger validation."""
    recs = []
    if "low_oos_edge" in weak_signals:
        recs.append({"field": "entry_threshold", "delta": -0.02, "reason": "tighten entry on weak OOS edge"})
    if "high_drawdown_slope" in weak_signals:
        recs.append({"field": "max_position_fraction", "delta": -0.05, "reason": "reduce size on drawdown acceleration"})
    if "low_liquidity" in weak_signals:
        recs.append({"field": "min_open_interest", "delta": 0.10, "reason": "raise liquidity floor"})
    return {
        "kind": "mutation_recommendation",
        "source_genome_hash": genome_hash(genome),
        "recommendations": recs,
        "auto_applied": False,
        "requires_proof_validation": True,
    }
