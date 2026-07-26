"""Detect stale or cross-version evidence state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any


def inspect_drift(
    evidence_records: Sequence[Mapping[str, Any]],
    event_time: str,
    maximum_age_hours: float,
) -> dict[str, Any]:
    event = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    stale: list[str] = []
    for record in evidence_records:
        observed = datetime.fromisoformat(str(record["observed_at"]).replace("Z", "+00:00"))
        age_hours = (event - observed).total_seconds() / 3600.0
        if age_hours < 0.0 or age_hours > maximum_age_hours:
            stale.append(str(record["evidence_id"]))
    return {
        "guard": "drift_detector",
        "status": "request_more_evidence" if stale else "pass",
        "stale_or_future_evidence_ids": sorted(stale),
        "maximum_age_hours": maximum_age_hours,
        "may_increase_readiness": False,
    }
