"""Refresh guard that restores the public lake after synthetic test rewrites."""
from __future__ import annotations

from .public_lake_freeze_guard import run_public_lake_freeze_guard


def run_public_lake_refresh_guard() -> dict[str, object]:
    return run_public_lake_freeze_guard()

