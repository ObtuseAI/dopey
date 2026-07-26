"""Bounded marginal-utility allocation for subsequent research rounds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey.protocols.agents import AgentContract, AgentResult
from dopey.protocols.identity import canonical_hash

from .allocation import allocate_research_budget
from .marginal_utility import should_terminate_low_yield


def plan_research_allocation(
    contracts: Sequence[AgentContract],
    results: Sequence[AgentResult],
    metacognition: Mapping[str, Any],
    resource_ledger: Mapping[str, Any],
    total_units: int,
) -> dict[str, Any]:
    result_by_id = {result.agent_id: result for result in results}
    information_gain = float(metacognition.get("expected_information_gain", 0.0) or 0.0)
    utility_by_agent: dict[str, float] = {}
    for contract in contracts:
        result = result_by_id.get(contract.agent_id)
        confidence = result.confidence if result is not None else 0.0
        data_gap_penalty = 0.5 if result is not None and result.status == "completed_with_data_gap" else 0.0
        utility_by_agent[contract.agent_id] = max(0.0, confidence * 0.6 + information_gain * 0.4 - data_gap_penalty)
    allocation = allocate_research_budget(utility_by_agent, total_units)
    overall_utility = float(metacognition.get("research_utility", -1.0) or -1.0)
    budget_exceeded = bool(resource_ledger.get("budget_exceeded", False))
    terminate = should_terminate_low_yield(overall_utility, budget_exceeded)
    body: dict[str, Any] = {
        "artifact_type": "research_metabolism_allocation",
        "metabolism_control_version": "dopey-metabolism-control-v1",
        "agent_marginal_utility": {key: round(value, 6) for key, value in sorted(utility_by_agent.items())},
        "next_round_allocation": allocation if not terminate else {key: 0 for key in allocation},
        "total_units": total_units,
        "automatic_low_yield_termination": terminate,
        "termination_reason": "budget_or_nonpositive_utility" if terminate else "continue_bounded_research",
        "may_expand_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
