"""Artifact runtime for the autonomous Dynamic Evidence Sentinel lane."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .sentinel import evaluate_dynamic_evidence_sentinel


def _settlement_sequence(calibration_summary: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = calibration_summary.get("settled_error_sequence", [])
    if not isinstance(raw, list) or any(not isinstance(record, dict) for record in raw):
        raise TypeError("calibration settled_error_sequence must be an object array")
    return tuple(dict(record) for record in raw)


def write_dynamic_evidence_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(artifact), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_dynamic_evidence_cycle(
    calibration_summary: Mapping[str, Any],
    output_path: Path,
    minimum_settlements: int,
    target_error_rate: float,
    maximum_recent_error_rate: float,
    conformal_learning_rate: float,
    conformal_window: int,
    recent_error_window: int,
    alpha_floor: float,
    alpha_ceiling: float,
    reference_window: int,
    recent_drift_window: int,
    drift_alpha: float,
    null_accuracy: float,
    betting_fraction: float,
    family_alpha: float,
) -> dict[str, Any]:
    if calibration_summary.get("paper_only") is not True or calibration_summary.get("live_blocked") is not True:
        raise ValueError("dynamic evidence cycle rejects a calibration summary outside the research-only boundary")
    as_of = str(
        calibration_summary.get("observed_at")
        or calibration_summary.get("as_of_date")
        or calibration_summary.get("reproducibility_hash")
        or "calibration_summary_without_reported_time"
    )
    sentinel = evaluate_dynamic_evidence_sentinel(
        _settlement_sequence(calibration_summary),
        (),
        as_of,
        minimum_settlements,
        target_error_rate,
        maximum_recent_error_rate,
        conformal_learning_rate,
        conformal_window,
        recent_error_window,
        alpha_floor,
        alpha_ceiling,
        reference_window,
        recent_drift_window,
        drift_alpha,
        null_accuracy,
        betting_fraction,
        family_alpha,
    )
    body: dict[str, Any] = {
        "artifact_type": "dynamic_evidence_cycle",
        "cycle_version": "dopey-dynamic-evidence-cycle-v1",
        "cycle_status": "complete",
        "source_calibration_hash": str(
            calibration_summary.get("reproducibility_hash") or canonical_hash(calibration_summary)
        ),
        "sentinel": sentinel,
        "selected_control": sentinel["selected_control"],
        "sentinel_status": sentinel["sentinel_status"],
        "positive_promotion_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    artifact = {**body, "reproducibility_hash": canonical_hash(body)}
    write_dynamic_evidence_artifact(output_path, artifact)
    return artifact
