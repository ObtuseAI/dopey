"""Allocate bounded research attention without permission expansion."""

from __future__ import annotations

from collections.abc import Mapping


def allocate_research_budget(
    agent_utility: Mapping[str, float],
    total_units: int,
) -> dict[str, int]:
    if total_units < 0:
        raise ValueError(f"total research units cannot be negative: total_units={total_units}")
    positive = {agent_id: max(0.0, utility) for agent_id, utility in agent_utility.items()}
    total_weight = sum(positive.values())
    if total_weight == 0.0:
        return {agent_id: 0 for agent_id in sorted(positive)}
    raw = {agent_id: total_units * weight / total_weight for agent_id, weight in positive.items()}
    allocated = {agent_id: int(value) for agent_id, value in raw.items()}
    remaining = total_units - sum(allocated.values())
    ranked = sorted(raw, key=lambda agent_id: (raw[agent_id] - allocated[agent_id], agent_id), reverse=True)
    for agent_id in ranked[:remaining]:
        allocated[agent_id] += 1
    return dict(sorted(allocated.items()))
