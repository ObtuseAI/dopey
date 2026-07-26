"""Focused proof for the leakage-resistant rolling-origin split surface."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from dopey_backtest.purged_rolling_origin import (
    RollingOriginObservation,
    RollingOriginTestWindow,
    build_purged_rolling_origin_plan,
)


UTC = timezone.utc


def _timestamp(day: int) -> datetime:
    return datetime(2026, 1, day, 16, 0, tzinfo=UTC)


def _identity_hash(candidate_id: str) -> str:
    return hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()


def _observation(
    observation_id: str,
    candidate_id: str,
    decision_day: int,
    label_start_day: int,
    label_end_day: int,
    purge_group_ids: tuple[str, ...],
) -> RollingOriginObservation:
    return {
        "observation_id": observation_id,
        "candidate_id": candidate_id,
        "candidate_identity_hash": _identity_hash(candidate_id),
        "decision_time": _timestamp(decision_day),
        "label_start_time": _timestamp(label_start_day),
        "label_end_time": _timestamp(label_end_day),
        "purge_group_ids": purge_group_ids,
    }


def _window(window_id: str, start_day: int, end_day: int) -> RollingOriginTestWindow:
    return {
        "window_id": window_id,
        "test_start": _timestamp(start_day),
        "test_end": _timestamp(end_day),
    }


def test_purges_embargo_boundary_interval_overlap_and_shared_groups() -> None:
    observations = (
        _observation("safe", "candidate-a", 1, 1, 3, ("asset:a",)),
        _observation("shared", "candidate-b", 2, 2, 4, ("event:earnings",)),
        _observation("boundary", "candidate-c", 3, 3, 8, ("asset:c",)),
        _observation("overlap", "candidate-d", 4, 4, 12, ("asset:d",)),
        _observation("test", "candidate-test", 10, 10, 11, ("event:earnings",)),
    )

    plan = build_purged_rolling_origin_plan(
        observations,
        (_window("origin-1", 10, 14),),
        timedelta(days=2),
        1,
        1,
    )

    fold = plan["folds"][0]
    assert fold["fold_status"] == "eligible_for_protected_evaluation"
    assert fold["train_observation_ids"] == ("safe",)
    assert fold["test_observation_ids"] == ("test",)
    assert fold["temporal_purge_observation_ids"] == ("boundary", "overlap")
    assert fold["interval_overlap_purge_observation_ids"] == ("overlap",)
    assert fold["shared_group_purge_observation_ids"] == ("shared",)
    assert fold["embargo_cutoff"] == "2026-01-08T16:00:00Z"


def test_candidate_freeze_uses_only_purged_training_observations() -> None:
    observations = (
        _observation("train", "candidate-train", 1, 1, 2, ("asset:a",)),
        _observation("test", "candidate-never-trained", 10, 10, 11, ("asset:b",)),
    )
    plan = build_purged_rolling_origin_plan(
        observations,
        (_window("origin-1", 10, 12),),
        timedelta(days=1),
        1,
        1,
    )

    fold = plan["folds"][0]
    assert fold["frozen_candidate_identities"] == (
        {
            "candidate_id": "candidate-train",
            "candidate_identity_hash": _identity_hash("candidate-train"),
        },
    )
    assert fold["candidate_freeze_scope"] == "purged_training_observations_only"
    assert plan["candidate_selection_uses_test_data"] is False
    assert plan["test_outcomes_consumed"] is False
    assert plan["performance_scored"] is False


def test_candidate_set_hash_is_deterministic_and_test_identity_independent() -> None:
    training = _observation("train", "candidate-train", 1, 1, 2, ("asset:a",))
    first_test = _observation("test", "candidate-test-a", 10, 10, 11, ("asset:b",))
    second_test = _observation("test", "candidate-test-b", 10, 10, 11, ("asset:b",))
    arguments = ((_window("origin-1", 10, 12),), timedelta(days=1), 1, 1)

    first_plan = build_purged_rolling_origin_plan(
        (training, first_test),
        arguments[0],
        arguments[1],
        arguments[2],
        arguments[3],
    )
    second_plan = build_purged_rolling_origin_plan(
        (training, second_test),
        arguments[0],
        arguments[1],
        arguments[2],
        arguments[3],
    )

    first_fold = first_plan["folds"][0]
    second_fold = second_plan["folds"][0]
    assert (
        first_fold["frozen_candidate_set_hash"]
        == second_fold["frozen_candidate_set_hash"]
    )
    assert first_fold["fold_id"] == second_fold["fold_id"]


def test_insufficient_data_is_reported_without_a_pass_or_edge_claim() -> None:
    observations = (_observation("test", "candidate-test", 10, 10, 11, ("asset:b",)),)
    plan = build_purged_rolling_origin_plan(
        observations,
        (_window("origin-1", 10, 12),),
        timedelta(days=1),
        2,
        2,
    )

    assert plan["plan_status"] == "insufficient_rolling_origins"
    assert plan["eligible_fold_count"] == 0
    assert plan["folds"][0]["fold_status"] == (
        "insufficient_train_and_test_observations"
    )
    assert plan["not_edge_evidence"] is True
    assert plan["positive_promotion_allowed"] is False
    assert plan["order_construction_allowed"] is False
    assert plan["paper_only"] is True
    assert plan["live_blocked"] is True


def test_candidate_identity_conflicts_fail_closed() -> None:
    first = _observation("first", "candidate-a", 1, 1, 2, ("asset:a",))
    second = _observation("second", "candidate-a", 2, 2, 3, ("asset:b",))
    second["candidate_identity_hash"] = _identity_hash("different-specification")

    with pytest.raises(ValueError, match="conflicting identity hashes"):
        build_purged_rolling_origin_plan(
            (first, second),
            (_window("origin-1", 10, 12),),
            timedelta(days=1),
            1,
            1,
        )


def test_naive_datetimes_fail_closed() -> None:
    observation = _observation("train", "candidate-a", 1, 1, 2, ("asset:a",))
    observation["decision_time"] = datetime(2026, 1, 1, 16, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        build_purged_rolling_origin_plan(
            (observation,),
            (_window("origin-1", 10, 12),),
            timedelta(days=1),
            1,
            1,
        )


def test_overlapping_test_windows_fail_closed() -> None:
    with pytest.raises(ValueError, match="chronological and non-overlapping"):
        build_purged_rolling_origin_plan(
            (),
            (
                _window("origin-1", 10, 14),
                _window("origin-2", 13, 16),
            ),
            timedelta(days=1),
            1,
            1,
        )
