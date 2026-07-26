"""Capability validation for research agents."""

from __future__ import annotations

from collections.abc import Sequence

from .execution_seal import assert_capabilities_research_only


def validate_agent_capabilities(capabilities: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(sorted({capability.strip().lower() for capability in capabilities if capability.strip()}))
    assert_capabilities_research_only(normalized)
    return normalized
