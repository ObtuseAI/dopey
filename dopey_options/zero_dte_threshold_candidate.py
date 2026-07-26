"""Materialize offline 0DTE threshold candidates without mutating defaults."""
from __future__ import annotations

from dataclasses import fields
from typing import Any

from .zero_dte_risk_thresholds import ZeroDTERiskThresholds
from .zero_dte_threshold_optimizer_models import ZeroDTEThresholdCandidate


def zero_dte_thresholds_from_candidate(
    base_thresholds: ZeroDTERiskThresholds,
    candidate: ZeroDTEThresholdCandidate,
) -> ZeroDTERiskThresholds:
    threshold_overrides = candidate.change_set.get("threshold_overrides", {})
    if not isinstance(threshold_overrides, dict):
        raise TypeError("candidate threshold_overrides must be dict")
    data = base_thresholds.to_dict()
    for key, value in threshold_overrides.items():
        if key not in data:
            raise KeyError(f"unsupported 0DTE threshold override: {key}")
        data[key] = value
    data["threshold_version"] = candidate.candidate_version
    data["paper_only"] = True
    data["live_blocked"] = True
    return ZeroDTERiskThresholds.from_dict(data)


def candidate_threshold_record(
    base_thresholds: ZeroDTERiskThresholds,
    candidate: ZeroDTEThresholdCandidate,
) -> dict[str, Any]:
    thresholds = zero_dte_thresholds_from_candidate(base_thresholds, candidate)
    return {
        "candidate_threshold_id": candidate.candidate_threshold_id,
        "candidate_version": candidate.candidate_version,
        "candidate_hash": candidate.candidate_hash,
        "thresholds": thresholds.to_dict(),
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def threshold_field_names() -> list[str]:
    return [field.name for field in fields(ZeroDTERiskThresholds)]
