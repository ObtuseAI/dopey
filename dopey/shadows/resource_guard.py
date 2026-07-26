"""Enforce resource budgets without hidden fallbacks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def inspect_resources(resource_ledger: Mapping[str, Any]) -> dict[str, Any]:
    exceeded = list(resource_ledger.get("exceeded_dimensions", []))
    return {
        "guard": "resource_guard",
        "status": "terminate" if exceeded else "pass",
        "exceeded_dimensions": exceeded,
        "may_increase_readiness": False,
    }
