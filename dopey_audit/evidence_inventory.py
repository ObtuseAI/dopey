"""Evidence inventory facade re-exported for ergonomic imports."""
from __future__ import annotations

from .artifact_loader import (
    ARTIFACT_ROOT,
    ARTIFACT_SPECS,
    build_artifact_record,
    build_completeness_report,
    build_freshness_report,
    build_inventory,
    load_latest_record,
    load_records,
)

__all__ = [
    "ARTIFACT_ROOT",
    "ARTIFACT_SPECS",
    "build_artifact_record",
    "build_completeness_report",
    "build_freshness_report",
    "build_inventory",
    "load_latest_record",
    "load_records",
]
