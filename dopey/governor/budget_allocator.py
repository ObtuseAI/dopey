"""Bounded per-agent research allocation."""

from __future__ import annotations

from collections.abc import Sequence

from dopey.metabolism.allocation import allocate_research_budget
from dopey.protocols.agents import AgentContract


def allocate_agent_units(contracts: Sequence[AgentContract], total_units: int) -> dict[str, int]:
    utilities = {
        contract.agent_id: 1.25 if contract.authority.value == "ADVERSARIAL_REVIEW" else 1.0
        for contract in contracts
    }
    return allocate_research_budget(utilities, total_units)
