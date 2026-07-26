"""Fuse sequential calibration, shift, and false-discovery evidence fail closed."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from dopey.protocols.identity import canonical_hash

from .calibration import adaptive_conformal_monitor
from .drift import empirical_distribution_shift
from .sequential import bounded_mean_e_process, e_lond_decisions


def _settlement_sequence(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    identities: set[str] = set()
    for index, record in enumerate(records):
        prediction_id = str(record.get("prediction_id", "")).strip()
        if not prediction_id:
            raise ValueError(f"dynamic evidence settlement requires prediction_id: index={index}")
        if prediction_id in identities:
            raise ValueError(f"dynamic evidence settlement identity is duplicated: prediction_id={prediction_id}")
        if record.get("paper_only") is not True or record.get("live_blocked") is not True:
            raise ValueError(
                "dynamic evidence settlement violates the research-only boundary: "
                f"prediction_id={prediction_id}"
            )
        if record.get("settlement_status") != "settled_forward_outcome":
            raise ValueError(
                "dynamic evidence accepts settled forward outcomes only: "
                f"prediction_id={prediction_id}, status={record.get('settlement_status')}"
            )
        confidence = float(record.get("research_confidence", 0.0))
        correct = bool(record.get("dominant_correct", False))
        error = float(record.get("confidence_absolute_error", abs(confidence - float(correct))))
        if not math.isfinite(error) or not 0.0 <= error <= 1.0:
            raise ValueError(
                "dynamic evidence confidence error must be finite and within [0, 1]: "
                f"prediction_id={prediction_id}, error={error}"
            )
        identities.add(prediction_id)
        normalized.append(
            {
                "prediction_id": prediction_id,
                "actual_settlement_date": str(record.get("actual_settlement_date", "")),
                "confidence_absolute_error": error,
                "dominant_correct": correct,
                "contested_truth": bool(record.get("contested_truth", False)),
            }
        )
    return tuple(
        sorted(
            normalized,
            key=lambda record: (str(record["actual_settlement_date"]), str(record["prediction_id"])),
        )
    )


def evaluate_dynamic_evidence_sentinel(
    settlements: Sequence[Mapping[str, Any]],
    candidate_e_values: Sequence[float],
    as_of: str,
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
    """Produce a downgrade-only research control from settled forward evidence."""

    if not as_of.strip():
        raise ValueError("dynamic evidence sentinel requires a non-empty as_of identity")
    if minimum_settlements <= 0:
        raise ValueError(
            "dynamic evidence minimum settlements must be positive: "
            f"minimum_settlements={minimum_settlements}"
        )
    if reference_window <= 1 or recent_drift_window <= 1:
        raise ValueError(
            "dynamic evidence drift windows must exceed one observation: "
            f"reference_window={reference_window}, recent_window={recent_drift_window}"
        )
    sequence = _settlement_sequence(settlements)
    errors = tuple(float(record["confidence_absolute_error"]) for record in sequence)
    correctness = tuple(float(bool(record["dominant_correct"])) for record in sequence)
    conformal = adaptive_conformal_monitor(
        errors,
        target_error_rate,
        conformal_learning_rate,
        minimum_settlements,
        conformal_window,
        recent_error_window,
        maximum_recent_error_rate,
        alpha_floor,
        alpha_ceiling,
    )
    enough_nonoverlapping_windows = len(errors) >= reference_window + recent_drift_window
    reference_values = errors[:reference_window] if enough_nonoverlapping_windows else ()
    recent_values = errors[-recent_drift_window:] if enough_nonoverlapping_windows else ()
    drift = empirical_distribution_shift(
        reference_values,
        recent_values,
        drift_alpha,
        min(reference_window, recent_drift_window),
    )
    accuracy_evidence = bounded_mean_e_process(
        correctness,
        null_accuracy,
        betting_fraction,
        family_alpha,
    )
    online_fdr = e_lond_decisions(candidate_e_values, family_alpha)
    enough_settlements = len(sequence) >= minimum_settlements
    miscoverage_detected = conformal["status"] == "adaptive_miscoverage_detected"
    drift_detected = bool(drift["drift_detected"])
    discovery_count = int(online_fdr["discovery_count"])
    accuracy_decisive = accuracy_evidence["status"] == "evidence_threshold_crossed"
    if not enough_settlements:
        sentinel_status = "insufficient_forward_evidence"
        control = "EXPAND_EVIDENCE"
    elif drift_detected:
        sentinel_status = "distribution_shift_detected"
        control = "ABSTAIN"
    elif miscoverage_detected:
        sentinel_status = "calibration_decay_detected"
        control = "ABSTAIN"
    elif discovery_count > 0:
        sentinel_status = "candidate_discovery_requires_adversarial_confirmation"
        control = "ADD_ADVERSARY"
    elif accuracy_decisive:
        sentinel_status = "evidence_monitoring_nominal"
        control = "CONTINUE"
    else:
        sentinel_status = "evidence_not_yet_decisive"
        control = "EXPAND_EVIDENCE"
    recent_error_rate = conformal.get("recent_error_rate")
    miscoverage_risk = (
        1.0
        if recent_error_rate is None
        else min(1.0, float(recent_error_rate) / max(maximum_recent_error_rate, 1e-12))
    )
    body: dict[str, Any] = {
        "artifact_type": "dynamic_evidence_sentinel",
        "sentinel_version": "dopey-dynamic-evidence-sentinel-v1",
        "as_of": as_of,
        "sentinel_status": sentinel_status,
        "selected_control": control,
        "settlement_count": len(sequence),
        "minimum_settlements": minimum_settlements,
        "settlement_sequence": sequence,
        "adaptive_conformal": conformal,
        "distribution_shift": drift,
        "accuracy_e_process": accuracy_evidence,
        "online_fdr": online_fdr,
        "candidate_e_values_supplied": bool(candidate_e_values),
        "risk_score": round(max(float(drift["risk_score"]), miscoverage_risk), 10),
        "valid_controls": ("CONTINUE", "EXPAND_EVIDENCE", "ADD_ADVERSARY", "ABSTAIN"),
        "minimum_sample_gate_preserved": True,
        "positive_promotion_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
