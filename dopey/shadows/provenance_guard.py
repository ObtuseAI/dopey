"""Detect missing or dangling evidence references."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey.constitution.evidence_law import validate_evidence_record
from dopey.protocols.agents import AgentResult


def inspect_provenance(
    evidence_records: Sequence[Mapping[str, Any]],
    agent_results: Sequence[AgentResult],
) -> dict[str, Any]:
    for record in evidence_records:
        validate_evidence_record(record)
    available = {str(record["evidence_id"]) for record in evidence_records}
    dangling = sorted(
        {
            evidence_id
            for result in agent_results
            for evidence_id in result.evidence_ids
            if evidence_id not in available
        }
    )
    return {
        "guard": "provenance_guard",
        "status": "veto" if dangling else "pass",
        "dangling_evidence_ids": dangling,
        "may_increase_readiness": False,
    }
