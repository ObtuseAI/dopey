"""Immutable typed contracts for deterministic research agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from dopey.constitution.authority import Authority, assert_research_authority
from dopey.constitution.permissions import validate_agent_capabilities

from .messages import ResearchMessage, validate_message


@dataclass(frozen=True)
class AgentContract:
    agent_id: str
    role: str
    authority: Authority
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    clock_domain: str
    resource_budget: dict[str, float | int]
    evidence_requirements: tuple[str, ...]
    failure_policy: str
    capabilities: tuple[str, ...]
    agent_version: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["authority"] = self.authority.value
        return record


@dataclass(frozen=True)
class AgentRuntime:
    seconds: float
    tokens: int
    data_reads: int
    cpu_seconds: float
    peak_memory_mb: float


@dataclass(frozen=True)
class AgentResult:
    agent_id: str
    status: str
    observations: tuple[ResearchMessage, ...]
    claims: tuple[ResearchMessage, ...]
    counterevidence: tuple[ResearchMessage, ...]
    uncertainties: tuple[ResearchMessage, ...]
    requested_followups: tuple[ResearchMessage, ...]
    confidence: float
    evidence_ids: tuple[str, ...]
    runtime: AgentRuntime
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        for key in (
            "observations",
            "claims",
            "counterevidence",
            "uncertainties",
            "requested_followups",
        ):
            record[key] = [message.to_dict() for message in getattr(self, key)]
        return record


class ResearchAgent(Protocol):
    contract: AgentContract

    def run(self, inputs: dict[str, Any]) -> AgentResult:
        """Return one typed, research-only invocation result."""


def validate_agent_contract(contract: AgentContract) -> None:
    if not contract.agent_id or not contract.role or not contract.agent_version:
        raise ValueError(
            "agent contract requires identity, role, and version: "
            f"agent_id={contract.agent_id}"
        )
    assert_research_authority(contract.authority)
    validate_agent_capabilities(contract.capabilities)
    if contract.failure_policy not in {"FAIL_CLOSED", "ABSTAIN", "TERMINATE"}:
        raise ValueError(
            "agent failure policy is not fail-closed: "
            f"agent_id={contract.agent_id}, failure_policy={contract.failure_policy}"
        )


def validate_agent_result(result: AgentResult) -> None:
    if result.paper_only is not True or result.live_blocked is not True:
        raise ValueError(
            "agent result crossed research-only boundary: "
            f"agent_id={result.agent_id}"
        )
    if not 0.0 <= result.confidence <= 1.0:
        raise ValueError(
            "agent result confidence must be within [0, 1]: "
            f"agent_id={result.agent_id}, confidence={result.confidence}"
        )
    messages = (
        result.observations
        + result.claims
        + result.counterevidence
        + result.uncertainties
        + result.requested_followups
    )
    for message in messages:
        validate_message(message)
