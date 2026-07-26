"""Focused proof for leak-free baseline-relative probability calibration."""

from __future__ import annotations

import math
from typing import Any

import pytest

from dopey.settlement.calibration import summarize_calibration


def _settled_record(
    prediction_id: str,
    settlement_date: str,
    realized_class: str,
    model_brier_score: float,
    model_log_loss: float,
) -> dict[str, Any]:
    return {
        "prediction_id": prediction_id,
        "settlement_status": "settled_forward_outcome",
        "actual_settlement_date": settlement_date,
        "realized_class": realized_class,
        "research_confidence": 0.6,
        "dominant_correct": realized_class == "bull",
        "multiclass_brier_score": model_brier_score,
        "multiclass_log_loss": model_log_loss,
        "contested_truth": False,
    }


def test_prequential_historical_baseline_batches_same_date_before_updating() -> None:
    records = (
        _settled_record("day-two", "2026-07-09", "neutral", 0.1, 0.5),
        _settled_record("day-one-bear", "2026-07-08", "bear", 0.1, 0.5),
        _settled_record("day-one-bull", "2026-07-08", "bull", 0.1, 0.5),
    )

    summary = summarize_calibration(records, 10, 3)
    baselines = summary["prequential_baselines"]
    first_batch, second_batch = baselines["batches"]

    assert first_batch["actual_settlement_date"] == "2026-07-08"
    assert first_batch["record_count"] == 2
    assert first_batch["prior_observation_count"] == 0
    assert first_batch["historical_frequency_probabilities"] == {
        "bull": 0.25,
        "bear": 0.25,
        "neutral": 0.25,
        "unknown": 0.25,
    }
    assert second_batch["actual_settlement_date"] == "2026-07-09"
    assert second_batch["prior_observation_count"] == 2
    assert second_batch["laplace_class_counts_before_batch"] == {
        "bull": 2,
        "bear": 2,
        "neutral": 1,
        "unknown": 1,
    }
    assert second_batch["historical_frequency_probabilities"] == {
        "bull": 0.33333333,
        "bear": 0.33333333,
        "neutral": 0.16666667,
        "unknown": 0.16666667,
    }
    assert (
        baselines["same_settlement_date_outcomes_used_for_same_date_baseline"] is False
    )
    assert baselines["mean_uniform_multiclass_brier_score"] == 0.1875
    assert baselines["mean_uniform_multiclass_log_loss"] == pytest.approx(math.log(4.0))
    assert baselines["mean_historical_frequency_multiclass_brier_score"] == 0.2037037
    assert baselines["mean_historical_frequency_multiclass_log_loss"] == pytest.approx(
        (2.0 * math.log(4.0) + math.log(6.0)) / 3.0,
    )


def test_baseline_relative_skill_is_withheld_below_existing_sample_threshold() -> None:
    records = (
        _settled_record("one", "2026-07-08", "bull", 0.1, 0.5),
        _settled_record("two", "2026-07-09", "bear", 0.1, 0.5),
    )

    summary = summarize_calibration(records, 10, 3)
    skill = summary["baseline_relative_skill"]

    assert summary["calibration_status"] == "insufficient_forward_settlements"
    assert summary["calibration_sample_sufficient"] is False
    assert skill == {
        "status": "insufficient_forward_settlements",
        "skill_claim_allowed": False,
        "brier_skill_vs_uniform": None,
        "log_loss_skill_vs_uniform": None,
        "brier_skill_vs_historical_frequency": None,
        "log_loss_skill_vs_historical_frequency": None,
    }
    assert summary["prequential_baselines"]["prequential_sample_count"] == 2


def test_baseline_relative_skill_is_reported_only_at_sufficient_sample() -> None:
    records = (
        _settled_record("one", "2026-07-08", "bull", 0.1, 0.5),
        _settled_record("two", "2026-07-09", "bear", 0.1, 0.5),
    )

    summary = summarize_calibration(records, 10, 2)
    skill = summary["baseline_relative_skill"]

    assert summary["calibration_sample_sufficient"] is True
    assert skill["status"] == "baseline_relative_skill_available"
    assert skill["skill_claim_allowed"] is True
    assert skill["brier_skill_vs_uniform"] == 0.46666667
    assert skill["log_loss_skill_vs_uniform"] == pytest.approx(
        1.0 - 0.5 / math.log(4.0),
    )
    assert skill["brier_skill_vs_historical_frequency"] == 0.50920245
    assert skill["log_loss_skill_vs_historical_frequency"] == pytest.approx(
        1.0 - 0.5 / ((math.log(4.0) + math.log(5.0)) / 2.0),
    )


def test_settled_record_without_a_valid_settlement_date_is_rejected() -> None:
    record = _settled_record("invalid-date", "07/08/2026", "bull", 0.1, 0.5)

    with pytest.raises(ValueError, match="actual_settlement_date must be ISO-8601"):
        summarize_calibration((record,), 10, 30)
