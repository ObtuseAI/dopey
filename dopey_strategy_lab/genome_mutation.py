"""Deterministic offline StrategyGenome mutation primitives."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

from .strategy_genome import StrategyGenome


MUTATION_BATCH_VERSION = "dopey-mutation-batch-v1"


@dataclass(frozen=True)
class MutationInstruction:
    mutation_id: str
    mutation_type: str
    target_path: str
    numeric_delta: float | None = None
    replacement_value: Any | None = None
    rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MutatedStrategyGenome:
    parent_genome_id: str
    mutation_id: str
    mutation_type: str
    genome: StrategyGenome
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["genome"] = self.genome.to_dict()
        return data


@dataclass(frozen=True)
class MutationBatch:
    batch_id: str
    seed: str
    parent_genome_ids: list[str]
    mutations: list[MutatedStrategyGenome]
    mutation_batch_version: str = MUTATION_BATCH_VERSION

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "seed": self.seed,
            "parent_genome_ids": self.parent_genome_ids,
            "mutations": [m.to_dict() for m in self.mutations],
            "mutation_batch_version": self.mutation_batch_version,
        }


def _set_path(data: dict, path: str, value: Any) -> dict:
    updated = copy.deepcopy(data)
    parts = path.split(".")
    current = updated
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return updated


def _mutate_numeric(value: Any, delta: float | None) -> Any:
    if delta is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return type(value)(round(float(value) * (1.0 + delta), 8))


def apply_mutation_instruction(parent: StrategyGenome, instruction: MutationInstruction) -> MutatedStrategyGenome:
    data = copy.deepcopy(parent.to_dict())
    if instruction.replacement_value is not None:
        data = _set_path(data, instruction.target_path, instruction.replacement_value)
    elif instruction.numeric_delta is not None:
        parts = instruction.target_path.split(".")
        current = data
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = _mutate_numeric(current.get(parts[-1], 0.0), instruction.numeric_delta)

    data["genome_id"] = f"{parent.genome_id}-{instruction.mutation_id}"
    data["version"] = int(parent.version) + 1
    data["defined_risk_only"] = True
    data["live_allowed"] = False
    params = data.setdefault("parameters", {})
    params["mutation_parent_id"] = parent.genome_id
    params["mutation_id"] = instruction.mutation_id
    params["mutation_type"] = instruction.mutation_type
    params["mutation_rationale"] = instruction.rationale
    params["structure_risk"] = "defined"
    params.setdefault("promotion_tier", "research_only")
    params.setdefault("forbidden_live_targets", ["live_candidate", "micro_live", "adaptive_live"])
    genome = StrategyGenome.from_dict(data)
    return MutatedStrategyGenome(
        parent_genome_id=parent.genome_id,
        mutation_id=instruction.mutation_id,
        mutation_type=instruction.mutation_type,
        genome=genome,
        safety_notes=[
            "live_allowed=false preserved",
            "defined_risk_only=true preserved",
            "no broker path added",
        ],
    )


def build_mutation_batch(
    parent_genomes: list[StrategyGenome],
    instructions: list[MutationInstruction],
    seed: str = "dopey-offline-edge-v1",
) -> MutationBatch:
    if not parent_genomes:
        raise ValueError("build_mutation_batch requires at least one parent genome")
    parent = parent_genomes[0]
    mutations = [apply_mutation_instruction(parent, instruction) for instruction in instructions]
    return MutationBatch(
        batch_id=f"mutation-batch-{seed}",
        seed=seed,
        parent_genome_ids=[g.genome_id for g in parent_genomes],
        mutations=mutations,
    )
