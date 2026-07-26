"""Probability calibration summaries derived only from settled predictions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from dopey.protocols.identity import canonical_hash


_OUTCOME_CLASSES: tuple[str, ...] = ("bull", "bear", "neutral", "unknown")


def _validated_settlement_date(record: Mapping[str, Any]) -> date:
    raw_date = str(record.get("actual_settlement_date", "")).strip()
    if not raw_date:
        raise ValueError(
            "settled calibration record requires actual_settlement_date: "
            f"prediction_id={record.get('prediction_id', '')}"
        )
    try:
        return date.fromisoformat(raw_date)
    except ValueError as error:
        raise ValueError(
            "settled calibration record actual_settlement_date must be ISO-8601: "
            f"prediction_id={record.get('prediction_id', '')}, actual_settlement_date={raw_date}"
        ) from error


def _validated_realized_class(record: Mapping[str, Any]) -> str:
    realized_class = str(record.get("realized_class", "")).strip()
    if realized_class not in _OUTCOME_CLASSES:
        raise ValueError(
            "settled calibration record realized_class violates the governed class contract: "
            f"prediction_id={record.get('prediction_id', '')}, realized_class={realized_class}, "
            f"expected={list(_OUTCOME_CLASSES)}"
        )
    return realized_class


def _multiclass_scores(
    probabilities: Mapping[str, float],
    realized_class: str,
) -> tuple[float, float]:
    brier_score = sum(
        (probabilities[name] - (1.0 if name == realized_class else 0.0)) ** 2
        for name in _OUTCOME_CLASSES
    ) / len(_OUTCOME_CLASSES)
    log_loss = -math.log(probabilities[realized_class])
    return brier_score, log_loss


def _prequential_baseline_summary(
    settlements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    outcomes_by_date: dict[date, list[str]] = {}
    for record in settlements:
        settlement_date = _validated_settlement_date(record)
        outcomes_by_date.setdefault(settlement_date, []).append(
            _validated_realized_class(record)
        )

    laplace_counts = {name: 1 for name in _OUTCOME_CLASSES}
    uniform_probabilities = {
        name: 1.0 / len(_OUTCOME_CLASSES) for name in _OUTCOME_CLASSES
    }
    uniform_brier_scores: list[float] = []
    uniform_log_losses: list[float] = []
    historical_brier_scores: list[float] = []
    historical_log_losses: list[float] = []
    batches: list[dict[str, Any]] = []

    for settlement_date in sorted(outcomes_by_date):
        outcomes = outcomes_by_date[settlement_date]
        prior_total = sum(laplace_counts.values())
        historical_probabilities = {
            name: laplace_counts[name] / prior_total for name in _OUTCOME_CLASSES
        }
        realized_counts = {name: outcomes.count(name) for name in _OUTCOME_CLASSES}
        for realized_class in outcomes:
            uniform_brier, uniform_log_loss = _multiclass_scores(
                uniform_probabilities,
                realized_class,
            )
            historical_brier, historical_log_loss = _multiclass_scores(
                historical_probabilities,
                realized_class,
            )
            uniform_brier_scores.append(uniform_brier)
            uniform_log_losses.append(uniform_log_loss)
            historical_brier_scores.append(historical_brier)
            historical_log_losses.append(historical_log_loss)

        batches.append(
            {
                "actual_settlement_date": settlement_date.isoformat(),
                "record_count": len(outcomes),
                "prior_observation_count": prior_total - len(_OUTCOME_CLASSES),
                "laplace_class_counts_before_batch": dict(laplace_counts),
                "historical_frequency_probabilities": {
                    name: round(historical_probabilities[name], 8)
                    for name in _OUTCOME_CLASSES
                },
                "realized_class_counts": realized_counts,
            }
        )
        for name in _OUTCOME_CLASSES:
            laplace_counts[name] += realized_counts[name]

    sample_count = len(settlements)
    return {
        "baseline_method": "strictly_prequential_uniform_and_laplace_historical_frequency",
        "governed_outcome_classes": list(_OUTCOME_CLASSES),
        "laplace_prior_count_per_class": 1,
        "settlement_date_batching": True,
        "same_settlement_date_outcomes_used_for_same_date_baseline": False,
        "prequential_sample_count": sample_count,
        "mean_uniform_multiclass_brier_score": (
            round(sum(uniform_brier_scores) / sample_count, 8) if sample_count else None
        ),
        "mean_uniform_multiclass_log_loss": (
            round(sum(uniform_log_losses) / sample_count, 8) if sample_count else None
        ),
        "mean_historical_frequency_multiclass_brier_score": (
            round(sum(historical_brier_scores) / sample_count, 8)
            if sample_count
            else None
        ),
        "mean_historical_frequency_multiclass_log_loss": (
            round(sum(historical_log_losses) / sample_count, 8)
            if sample_count
            else None
        ),
        "batches": batches,
    }


def _skill_score(model_score: float, baseline_score: float) -> float:
    if baseline_score <= 0.0:
        raise ValueError(
            "baseline score must be positive for relative skill calculation: "
            f"baseline_score={baseline_score}"
        )
    return 1.0 - model_score / baseline_score


def _reliability_bins(
    settlements: Sequence[Mapping[str, Any]],
    bin_count: int,
) -> list[dict[str, float | int]]:
    if bin_count <= 0:
        raise ValueError(
            f"calibration bin count must be positive: bin_count={bin_count}"
        )
    bins: list[dict[str, float | int]] = []
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        members = [
            record
            for record in settlements
            if lower <= float(record["research_confidence"]) < upper
            or (index == bin_count - 1 and float(record["research_confidence"]) == 1.0)
        ]
        if not members:
            bins.append(
                {
                    "lower": round(lower, 6),
                    "upper": round(upper, 6),
                    "count": 0,
                    "mean_confidence": 0.0,
                    "accuracy": 0.0,
                    "absolute_gap": 0.0,
                }
            )
            continue
        mean_confidence = sum(
            float(record["research_confidence"]) for record in members
        ) / len(members)
        accuracy = sum(bool(record["dominant_correct"]) for record in members) / len(
            members
        )
        bins.append(
            {
                "lower": round(lower, 6),
                "upper": round(upper, 6),
                "count": len(members),
                "mean_confidence": round(mean_confidence, 8),
                "accuracy": round(accuracy, 8),
                "absolute_gap": round(abs(mean_confidence - accuracy), 8),
            }
        )
    return bins


def summarize_calibration(
    records: Sequence[Mapping[str, Any]],
    bin_count: int,
    minimum_calibration_sample: int,
) -> dict[str, Any]:
    if minimum_calibration_sample <= 0:
        raise ValueError(
            "minimum calibration sample must be positive: "
            f"minimum_calibration_sample={minimum_calibration_sample}"
        )
    settled = [
        record
        for record in records
        if record.get("settlement_status") == "settled_forward_outcome"
    ]
    pending = sum(
        record.get("settlement_status") == "pending_minimum_horizon"
        for record in records
    )
    missing = sum(
        record.get("settlement_status") == "due_missing_verified_price"
        for record in records
    )
    quarantined = sum(
        record.get("settlement_status") == "quarantined_missing_point_in_time_proof"
        for record in records
    )
    reliability = _reliability_bins(settled, bin_count)
    total = len(settled)
    sample_sufficient = total >= minimum_calibration_sample
    mean_model_brier = (
        sum(float(record["multiclass_brier_score"]) for record in settled) / total
        if total
        else None
    )
    mean_model_log_loss = (
        sum(float(record["multiclass_log_loss"]) for record in settled) / total
        if total
        else None
    )
    prequential_baselines = _prequential_baseline_summary(settled)
    uniform_brier = prequential_baselines["mean_uniform_multiclass_brier_score"]
    uniform_log_loss = prequential_baselines["mean_uniform_multiclass_log_loss"]
    historical_brier = prequential_baselines[
        "mean_historical_frequency_multiclass_brier_score"
    ]
    historical_log_loss = prequential_baselines[
        "mean_historical_frequency_multiclass_log_loss"
    ]
    baseline_relative_skill = {
        "status": (
            "baseline_relative_skill_available"
            if sample_sufficient
            else "insufficient_forward_settlements"
        ),
        "skill_claim_allowed": sample_sufficient,
        "brier_skill_vs_uniform": (
            round(_skill_score(mean_model_brier, float(uniform_brier)), 8)
            if sample_sufficient
            and mean_model_brier is not None
            and uniform_brier is not None
            else None
        ),
        "log_loss_skill_vs_uniform": (
            round(_skill_score(mean_model_log_loss, float(uniform_log_loss)), 8)
            if sample_sufficient
            and mean_model_log_loss is not None
            and uniform_log_loss is not None
            else None
        ),
        "brier_skill_vs_historical_frequency": (
            round(_skill_score(mean_model_brier, float(historical_brier)), 8)
            if sample_sufficient
            and mean_model_brier is not None
            and historical_brier is not None
            else None
        ),
        "log_loss_skill_vs_historical_frequency": (
            round(_skill_score(mean_model_log_loss, float(historical_log_loss)), 8)
            if sample_sufficient
            and mean_model_log_loss is not None
            and historical_log_loss is not None
            else None
        ),
    }
    expected_calibration_error = (
        sum(
            int(record["count"]) * float(record["absolute_gap"])
            for record in reliability
        )
        / total
        if total
        else None
    )
    body: dict[str, Any] = {
        "artifact_type": "vnext_probability_calibration_summary",
        "calibration_version": "dopey-vnext-calibration-v2",
        "settled_total": total,
        "pending_total": pending,
        "due_missing_verified_price_total": missing,
        "quarantined_missing_point_in_time_proof_total": quarantined,
        "contested_total": sum(
            bool(record.get("contested_truth")) for record in settled
        ),
        "dominant_accuracy": (
            round(
                sum(bool(record["dominant_correct"]) for record in settled) / total, 8
            )
            if total
            else None
        ),
        "mean_multiclass_brier_score": (
            round(mean_model_brier, 8) if mean_model_brier is not None else None
        ),
        "mean_multiclass_log_loss": (
            round(mean_model_log_loss, 8) if mean_model_log_loss is not None else None
        ),
        "prequential_baselines": prequential_baselines,
        "baseline_relative_skill": baseline_relative_skill,
        "expected_calibration_error": (
            round(expected_calibration_error, 8)
            if expected_calibration_error is not None
            else None
        ),
        "maximum_calibration_error": (
            max(
                (
                    float(record["absolute_gap"])
                    for record in reliability
                    if int(record["count"]) > 0
                ),
                default=None,
            )
        ),
        "reliability_bins": reliability,
        "minimum_calibration_sample": minimum_calibration_sample,
        "calibration_sample_sufficient": sample_sufficient,
        "calibration_status": (
            "calibrated_sample_available"
            if sample_sufficient
            else "insufficient_forward_settlements"
        ),
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
