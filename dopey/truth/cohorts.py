"""Canonical cohort routing that preserves child-level attribution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey_strategy_cohorts.strategy_id_canonicalizer import assign_cohort_ids


def canonicalize_evaluation_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen_children: set[str] = set()
    for index, record in enumerate(records):
        child_id = str(record.get("child_id", record.get("prediction_id", "")))
        if not child_id:
            raise ValueError(f"causal evaluation record requires child identity: index={index}")
        if child_id in seen_children:
            raise ValueError(f"causal evaluation child identity must be unique: child_id={child_id}")
        seen_children.add(child_id)
        cohort_ids = assign_cohort_ids(record)
        output.append(
            {
                **dict(record),
                **cohort_ids,
                "child_id": child_id,
                "child_attribution_preserved": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return output
