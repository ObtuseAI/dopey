"""Deterministic template selection before evolved morphology is validated."""

from __future__ import annotations

from dopey.protocols.agents import AgentContract

from collections.abc import Mapping
from typing import Any

from dopey.organisms.templates import OBJECTIVE_SPECIALISTS, dynamic_organism_template


def select_organism_template(
    objective_type: str,
    evidence_profile: Mapping[str, Any],
) -> tuple[str, tuple[AgentContract, ...]]:
    if objective_type not in OBJECTIVE_SPECIALISTS:
        raise ValueError(
            "research objective has no governed deterministic template: "
            f"objective_type={objective_type}, supported={sorted(OBJECTIVE_SPECIALISTS)}"
        )
    unknown_count = int(evidence_profile.get("unknown_world_dimension_count", 0) or 0)
    include_boundary = unknown_count > 0 or bool(evidence_profile.get("out_of_distribution", False))
    contracts = dynamic_organism_template(objective_type, include_boundary)
    boundary_suffix = "with_boundary" if include_boundary else "known_boundary"
    return f"{objective_type}_dynamic_v1_{boundary_suffix}", contracts
