"""Shared, fail-closed semantics for operational status values."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, TypedDict


class OperationalStatusClass(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class OperationalStatusAssessment(TypedDict):
    raw_status: str
    status_class: OperationalStatusClass
    failure_signal: bool
    retry_candidate: bool
    evidence_trustworthy: bool


_HEALTHY_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "complete",
        "completed",
        "ok",
        "pass",
        "verified_complete",
        "within_error_budget",
    }
)
_FAILED_TOKENS: Final[tuple[str, ...]] = (
    "failed",
    "failure",
    "error",
    "exception",
    "inconclusive_timeout",
    "timed_out",
)
_DEGRADED_TOKENS: Final[tuple[str, ...]] = (
    "degraded",
    "stale",
    "partial",
    "incomplete",
    "missing_or_invalid",
    "future_timestamp",
    "unverified",
)
_BLOCKED_TOKENS: Final[tuple[str, ...]] = (
    "blocked",
    "quarantined",
    "not_action_ready",
    "not_available",
    "awaiting_",
)


def classify_operational_status(status: str) -> OperationalStatusAssessment:
    normalized = status.strip().lower()
    if normalized in _HEALTHY_STATUSES:
        status_class = OperationalStatusClass.HEALTHY
    elif any(token in normalized for token in _FAILED_TOKENS):
        status_class = OperationalStatusClass.FAILED
    elif any(token in normalized for token in _BLOCKED_TOKENS):
        status_class = OperationalStatusClass.BLOCKED
    elif any(token in normalized for token in _DEGRADED_TOKENS):
        status_class = OperationalStatusClass.DEGRADED
    elif normalized.startswith("complete_"):
        status_class = OperationalStatusClass.HEALTHY
    else:
        status_class = OperationalStatusClass.UNKNOWN
    return {
        "raw_status": status,
        "status_class": status_class,
        "failure_signal": status_class
        in {
            OperationalStatusClass.DEGRADED,
            OperationalStatusClass.FAILED,
            OperationalStatusClass.BLOCKED,
        },
        "retry_candidate": status_class
        in {
            OperationalStatusClass.DEGRADED,
            OperationalStatusClass.FAILED,
        },
        "evidence_trustworthy": status_class is OperationalStatusClass.HEALTHY,
    }
