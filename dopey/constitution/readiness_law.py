"""Research outputs are permanently separate from action readiness."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ReadinessLawViolation(ValueError):
    """Raised when research attempts to influence protected readiness state."""


def assert_readiness_is_external(record: Mapping[str, Any]) -> None:
    forbidden_truthy = (
        "action_ready",
        "live_allowed",
        "promotion_allowed",
        "strategy_promotion_allowed",
    )
    violations = sorted(key for key in forbidden_truthy if record.get(key) is True)
    if violations:
        raise ReadinessLawViolation(
            "vNext research cannot raise readiness: "
            f"truthy_fields={violations}"
        )
