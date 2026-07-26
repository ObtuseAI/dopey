"""Assemble and budget a research organism without action authority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.protocols.agents import AgentContract
from dopey.protocols.identity import canonical_hash

from .authority_router import validate_organism_authority
from .budget_allocator import allocate_agent_units
from .morphology import select_organism_template
from .policy_field import research_policy_field


def govern_research_objective(
    objective_type: str,
    symbol: str,
    total_research_units: int,
    evidence_profile: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[AgentContract, ...]]:
    if not symbol.strip():
        raise ValueError("research governor requires a non-empty symbol")
    template_id, contracts = select_organism_template(objective_type, evidence_profile)
    validate_organism_authority(contracts)
    allocations = allocate_agent_units(contracts, total_research_units)
    body: dict[str, Any] = {
        "artifact_type": "sovereign_research_governor_plan",
        "governor_version": "dopey-sovereign-research-governor-v1",
        "objective_type": objective_type,
        "symbol": symbol,
        "template_id": template_id,
        "agent_ids": [contract.agent_id for contract in contracts],
        "research_unit_allocations": allocations,
        "policy_field": research_policy_field(),
        "morphology_mode": "deterministic_dynamic_templates",
        "evidence_profile_hash": canonical_hash(dict(evidence_profile)),
        "evolved_morphology_enabled": False,
        "readiness_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}, contracts
