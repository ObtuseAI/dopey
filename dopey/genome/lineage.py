"""Lineage validation for immutable research genomes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .schema import ResearchGenome


def build_lineage(genomes: Sequence[ResearchGenome]) -> dict[str, Any]:
    by_id = {genome.genome_id: genome for genome in genomes}
    if len(by_id) != len(genomes):
        raise ValueError("genome lineage contains duplicate genome identities")
    missing = sorted(
        parent_id
        for genome in genomes
        for parent_id in genome.parent_ids
        if parent_id not in by_id
    )
    if missing:
        raise ValueError(f"genome lineage has missing parents: parent_ids={missing}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(genome_id: str) -> None:
        if genome_id in visiting:
            raise ValueError(f"genome lineage contains a cycle: genome_id={genome_id}")
        if genome_id in visited:
            return
        visiting.add(genome_id)
        for parent_id in by_id[genome_id].parent_ids:
            visit(parent_id)
        visiting.remove(genome_id)
        visited.add(genome_id)

    for genome_id in sorted(by_id):
        visit(genome_id)
    edges = [
        {"parent_id": parent_id, "child_id": genome.genome_id}
        for genome in genomes
        for parent_id in genome.parent_ids
    ]
    return {
        "artifact_type": "research_genome_lineage",
        "genome_count": len(genomes),
        "roots": sorted(genome.genome_id for genome in genomes if not genome.parent_ids),
        "edges": sorted(edges, key=lambda edge: (edge["parent_id"], edge["child_id"])),
        "acyclic": True,
        "paper_only": True,
        "live_blocked": True,
    }
