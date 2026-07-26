"""Append-only paper execution-quality evidence logging.

The logger accepts only paper-only, live-blocked observations.  It stores a
defensive copy and a deterministic content identity so later calibration can
distinguish observed quotes from simulated mechanics without mutable history.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from dopey.ascendancy.execution_quality import (
    ExecutionQualityPolicy,
    PaperExecutionQualityInput,
    evaluate_paper_execution_quality,
)


class InvalidExecutionQualityEventError(ValueError):
    """Raised when an event attempts to weaken the paper-only evidence law."""


def execution_quality_event_hash(event: Mapping[str, object]) -> str:
    """Return a deterministic identity for one immutable execution event."""
    encoded = json.dumps(dict(event), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_execution_quality_event(event: Mapping[str, object]) -> dict[str, object]:
    """Validate and copy an execution event before it enters the ledger."""
    normalized = dict(event)
    if normalized.get("paper_only") is not True:
        raise InvalidExecutionQualityEventError("Execution-quality evidence must assert paper_only=true")
    if normalized.get("live_blocked") is not True:
        raise InvalidExecutionQualityEventError("Execution-quality evidence must assert live_blocked=true")
    if normalized.get("live_trading_enabled") is True:
        raise InvalidExecutionQualityEventError("Execution-quality evidence cannot enable live trading")
    return normalized


class ExecutionQualityLogger:
    """In-memory connector for immutable paper execution-quality events."""

    def __init__(self) -> None:
        self._events: list[dict[str, object]] = []

    def log(self, event: Mapping[str, object]) -> None:
        normalized = validate_execution_quality_event(event)
        self._events.append(
            {
                **normalized,
                "execution_quality_event_hash": execution_quality_event_hash(normalized),
            }
        )

    def evaluate_and_log(
        self,
        observation: PaperExecutionQualityInput,
        policy: ExecutionQualityPolicy,
    ) -> dict[str, object]:
        measurement = evaluate_paper_execution_quality(observation, policy)
        self.log(measurement)
        return dict(measurement)

    def events(self) -> list[dict[str, object]]:
        return [dict(event) for event in self._events]
