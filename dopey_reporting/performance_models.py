"""Performance-attribution helpers for DOPEY reporting artifacts."""
from __future__ import annotations

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .report_models import PerformanceAttributionSummary


def canonical_reporting_hash(record: dict) -> str:
    """Return the canonical single-record hash used by reporting artifacts."""
    stripped = {key: value for key, value in record.items() if key != "reproducibility_hash"}
    return reproducibility_hash(stripped)


def attribution_record_hash(record: dict) -> str:
    """Return the deterministic attribution hash without the hash fields."""
    stripped = {
        key: value
        for key, value in record.items()
        if key not in {"deterministic_hash", "reproducibility_hash"}
    }
    return reproducibility_hash(stripped)


__all__ = ["PerformanceAttributionSummary", "attribution_record_hash", "canonical_reporting_hash"]
