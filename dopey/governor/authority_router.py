"""Verify every assembled agent remains within its declared authority."""

from __future__ import annotations

from collections.abc import Sequence

from dopey.protocols.agents import AgentContract, validate_agent_contract


def validate_organism_authority(contracts: Sequence[AgentContract]) -> None:
    for contract in contracts:
        validate_agent_contract(contract)
