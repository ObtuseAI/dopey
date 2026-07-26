"""Detect unsupported, duplicated, and data-gap-obscuring agent output."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from dopey.protocols.agents import AgentResult


def inspect_claim_quality(agent_results: Sequence[AgentResult]) -> dict[str, Any]:
    unsupported = sorted(
        message.message_id
        for result in agent_results
        for message in result.claims + result.counterevidence
        if not message.evidence_ids
    )
    content_ids = [
        message.message_id
        for result in agent_results
        for message in result.observations + result.claims + result.counterevidence + result.uncertainties
    ]
    duplicates = sorted(identifier for identifier, count in Counter(content_ids).items() if count > 1)
    data_gap_agents = sorted(result.agent_id for result in agent_results if result.status == "completed_with_data_gap")
    counterevidence_count = sum(len(result.counterevidence) for result in agent_results)
    findings: list[str] = []
    if unsupported:
        findings.append("unsupported_material_claim")
    if duplicates:
        findings.append("duplicated_analysis")
    if data_gap_agents:
        findings.append("specialist_data_gaps_present")
    if counterevidence_count == 0:
        findings.append("counterevidence_omitted")
    status = "veto" if unsupported else "request_more_evidence" if findings else "pass"
    return {
        "guard": "claim_quality_guard",
        "status": status,
        "findings": findings,
        "unsupported_message_ids": unsupported,
        "duplicated_message_ids": duplicates,
        "data_gap_agent_ids": data_gap_agents,
        "may_increase_readiness": False,
    }
