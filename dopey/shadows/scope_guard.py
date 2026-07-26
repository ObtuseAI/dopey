"""Detect authority or execution-scope drift."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey.constitution.execution_seal import assert_output_research_only
from dopey.constitution.readiness_law import assert_readiness_is_external
from dopey.protocols.agents import AgentResult, validate_agent_result


def inspect_scope(
    organism: Mapping[str, Any],
    agent_results: Sequence[AgentResult],
) -> dict[str, Any]:
    assert_output_research_only(organism)
    assert_readiness_is_external(organism)
    for result in agent_results:
        validate_agent_result(result)
    return {
        "guard": "scope_guard",
        "status": "pass",
        "violations": [],
        "may_increase_readiness": False,
    }
