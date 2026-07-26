"""Leakage-resistant rolling-origin split construction for protected research.

This module assigns observations to explicit chronological test windows.  It
does not score candidates, consume outcomes, promote a strategy, or construct
an order.  A fold is eligible for later protected evaluation only when its
training labels are strictly older than the embargo cutoff and its training
observations do not share declared dependency groups with the test window.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Sequence, TypedDict


PURGED_ROLLING_ORIGIN_VERSION = "dopey-purged-rolling-origin-v1"


class RollingOriginObservation(TypedDict):
    observation_id: str
    candidate_id: str
    candidate_identity_hash: str
    decision_time: datetime
    label_start_time: datetime
    label_end_time: datetime
    purge_group_ids: tuple[str, ...]


class RollingOriginTestWindow(TypedDict):
    window_id: str
    test_start: datetime
    test_end: datetime


class FrozenCandidateIdentity(TypedDict):
    candidate_id: str
    candidate_identity_hash: str


class PurgedRollingOriginFold(TypedDict):
    fold_id: str
    window_id: str
    fold_status: str
    test_start: str
    test_end: str
    embargo_cutoff: str
    train_observation_ids: tuple[str, ...]
    test_observation_ids: tuple[str, ...]
    temporal_purge_observation_ids: tuple[str, ...]
    interval_overlap_purge_observation_ids: tuple[str, ...]
    shared_group_purge_observation_ids: tuple[str, ...]
    future_or_outside_observation_ids: tuple[str, ...]
    frozen_candidate_identities: tuple[FrozenCandidateIdentity, ...]
    frozen_candidate_set_hash: str
    train_observation_count: int
    test_observation_count: int
    minimum_train_observations: int
    minimum_test_observations: int
    candidate_freeze_scope: str
    test_outcomes_consumed: bool
    performance_scored: bool
    not_edge_evidence: bool
    positive_promotion_allowed: bool
    order_construction_allowed: bool
    paper_only: bool
    live_blocked: bool


class PurgedRollingOriginPlan(TypedDict):
    artifact_type: str
    version: str
    plan_status: str
    fold_count: int
    eligible_fold_count: int
    insufficient_fold_count: int
    embargo_seconds: int
    minimum_train_observations: int
    minimum_test_observations: int
    folds: tuple[PurgedRollingOriginFold, ...]
    candidate_selection_uses_test_data: bool
    test_outcomes_consumed: bool
    performance_scored: bool
    not_edge_evidence: bool
    positive_promotion_allowed: bool
    order_construction_allowed: bool
    paper_only: bool
    live_blocked: bool


class _NormalizedObservation(TypedDict):
    observation_id: str
    candidate_id: str
    candidate_identity_hash: str
    decision_time: datetime
    label_start_time: datetime
    label_end_time: datetime
    purge_group_ids: tuple[str, ...]


class _NormalizedTestWindow(TypedDict):
    window_id: str
    test_start: datetime
    test_end: datetime


def build_purged_rolling_origin_plan(
    observations: Sequence[RollingOriginObservation],
    test_windows: Sequence[RollingOriginTestWindow],
    embargo: timedelta,
    minimum_train_observations: int,
    minimum_test_observations: int,
) -> PurgedRollingOriginPlan:
    """Build deterministic purged folds without reading labels or performance."""

    _validate_configuration(
        embargo,
        minimum_train_observations,
        minimum_test_observations,
    )
    normalized_observations = _normalize_observations(observations)
    normalized_windows = _normalize_test_windows(test_windows)
    folds = tuple(
        _build_fold(
            normalized_observations,
            window,
            embargo,
            minimum_train_observations,
            minimum_test_observations,
        )
        for window in normalized_windows
    )
    eligible_fold_count = sum(
        fold["fold_status"] == "eligible_for_protected_evaluation" for fold in folds
    )
    if eligible_fold_count == len(folds):
        plan_status = "ready_for_protected_evaluation"
    elif eligible_fold_count > 0:
        plan_status = "partially_ready_for_protected_evaluation"
    else:
        plan_status = "insufficient_rolling_origins"
    return {
        "artifact_type": "purged_rolling_origin_plan",
        "version": PURGED_ROLLING_ORIGIN_VERSION,
        "plan_status": plan_status,
        "fold_count": len(folds),
        "eligible_fold_count": eligible_fold_count,
        "insufficient_fold_count": len(folds) - eligible_fold_count,
        "embargo_seconds": int(embargo.total_seconds()),
        "minimum_train_observations": minimum_train_observations,
        "minimum_test_observations": minimum_test_observations,
        "folds": folds,
        "candidate_selection_uses_test_data": False,
        "test_outcomes_consumed": False,
        "performance_scored": False,
        "not_edge_evidence": True,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _build_fold(
    observations: tuple[_NormalizedObservation, ...],
    window: _NormalizedTestWindow,
    embargo: timedelta,
    minimum_train_observations: int,
    minimum_test_observations: int,
) -> PurgedRollingOriginFold:
    test_start = window["test_start"]
    test_end = window["test_end"]
    embargo_cutoff = test_start - embargo
    test_observations = tuple(
        observation
        for observation in observations
        if test_start <= observation["decision_time"] < test_end
    )
    pre_origin_observations = tuple(
        observation
        for observation in observations
        if observation["decision_time"] < test_start
    )
    temporal_purge = tuple(
        observation
        for observation in pre_origin_observations
        if observation["label_end_time"] >= embargo_cutoff
    )
    temporally_eligible = tuple(
        observation
        for observation in pre_origin_observations
        if observation["label_end_time"] < embargo_cutoff
    )
    overlap_purge = tuple(
        observation
        for observation in temporal_purge
        if _intervals_overlap_test_window(observation, window)
    )
    test_group_ids = frozenset(
        group_id
        for observation in test_observations
        for group_id in observation["purge_group_ids"]
    )
    shared_group_purge = tuple(
        observation
        for observation in temporally_eligible
        if test_group_ids.intersection(observation["purge_group_ids"])
    )
    shared_group_purge_ids = frozenset(
        observation["observation_id"] for observation in shared_group_purge
    )
    train_observations = tuple(
        observation
        for observation in temporally_eligible
        if observation["observation_id"] not in shared_group_purge_ids
    )
    train_ids = _observation_ids(train_observations)
    test_ids = _observation_ids(test_observations)
    temporal_purge_ids = _observation_ids(temporal_purge)
    overlap_purge_ids = _observation_ids(overlap_purge)
    shared_group_ids = _observation_ids(shared_group_purge)
    assigned_ids = frozenset(
        train_ids + test_ids + temporal_purge_ids + shared_group_ids
    )
    outside_ids = tuple(
        observation["observation_id"]
        for observation in observations
        if observation["observation_id"] not in assigned_ids
    )
    frozen_identities = _freeze_candidate_identities(train_observations)
    frozen_candidate_set_hash = _candidate_set_hash(frozen_identities)
    fold_status = _fold_status(
        len(train_observations),
        len(test_observations),
        minimum_train_observations,
        minimum_test_observations,
    )
    fold_id = _fold_id(
        window,
        embargo,
        train_ids,
        test_ids,
        frozen_candidate_set_hash,
    )
    return {
        "fold_id": fold_id,
        "window_id": window["window_id"],
        "fold_status": fold_status,
        "test_start": _isoformat_utc(test_start),
        "test_end": _isoformat_utc(test_end),
        "embargo_cutoff": _isoformat_utc(embargo_cutoff),
        "train_observation_ids": train_ids,
        "test_observation_ids": test_ids,
        "temporal_purge_observation_ids": temporal_purge_ids,
        "interval_overlap_purge_observation_ids": overlap_purge_ids,
        "shared_group_purge_observation_ids": shared_group_ids,
        "future_or_outside_observation_ids": outside_ids,
        "frozen_candidate_identities": frozen_identities,
        "frozen_candidate_set_hash": frozen_candidate_set_hash,
        "train_observation_count": len(train_observations),
        "test_observation_count": len(test_observations),
        "minimum_train_observations": minimum_train_observations,
        "minimum_test_observations": minimum_test_observations,
        "candidate_freeze_scope": "purged_training_observations_only",
        "test_outcomes_consumed": False,
        "performance_scored": False,
        "not_edge_evidence": True,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _normalize_observations(
    observations: Sequence[RollingOriginObservation],
) -> tuple[_NormalizedObservation, ...]:
    normalized: list[_NormalizedObservation] = []
    seen_observation_ids: set[str] = set()
    candidate_hashes: dict[str, str] = {}
    for index, observation in enumerate(observations):
        observation_id = _require_nonempty_string(
            observation.get("observation_id"),
            f"observations[{index}].observation_id",
        )
        if observation_id in seen_observation_ids:
            raise ValueError(f"duplicate observation_id: {observation_id}")
        seen_observation_ids.add(observation_id)
        candidate_id = _require_nonempty_string(
            observation.get("candidate_id"),
            f"observations[{index}].candidate_id",
        )
        candidate_identity_hash = _require_sha256(
            observation.get("candidate_identity_hash"),
            f"observations[{index}].candidate_identity_hash",
        )
        prior_hash = candidate_hashes.get(candidate_id)
        if prior_hash is not None and prior_hash != candidate_identity_hash:
            raise ValueError(
                "candidate_id maps to conflicting identity hashes: "
                f"candidate_id={candidate_id}"
            )
        candidate_hashes[candidate_id] = candidate_identity_hash
        decision_time = _require_aware_datetime(
            observation.get("decision_time"),
            f"observations[{index}].decision_time",
        )
        label_start_time = _require_aware_datetime(
            observation.get("label_start_time"),
            f"observations[{index}].label_start_time",
        )
        label_end_time = _require_aware_datetime(
            observation.get("label_end_time"),
            f"observations[{index}].label_end_time",
        )
        if decision_time > label_start_time:
            raise ValueError(
                "decision_time must not follow label_start_time: "
                f"observation_id={observation_id}"
            )
        if label_start_time > label_end_time:
            raise ValueError(
                "label_start_time must not follow label_end_time: "
                f"observation_id={observation_id}"
            )
        purge_group_ids = _require_group_ids(
            observation.get("purge_group_ids"),
            f"observations[{index}].purge_group_ids",
        )
        normalized.append(
            {
                "observation_id": observation_id,
                "candidate_id": candidate_id,
                "candidate_identity_hash": candidate_identity_hash,
                "decision_time": decision_time,
                "label_start_time": label_start_time,
                "label_end_time": label_end_time,
                "purge_group_ids": purge_group_ids,
            }
        )
    return tuple(
        sorted(
            normalized,
            key=lambda observation: (
                observation["decision_time"],
                observation["observation_id"],
            ),
        )
    )


def _normalize_test_windows(
    test_windows: Sequence[RollingOriginTestWindow],
) -> tuple[_NormalizedTestWindow, ...]:
    if not test_windows:
        raise ValueError("test_windows must contain at least one explicit window")
    normalized: list[_NormalizedTestWindow] = []
    seen_window_ids: set[str] = set()
    for index, window in enumerate(test_windows):
        window_id = _require_nonempty_string(
            window.get("window_id"),
            f"test_windows[{index}].window_id",
        )
        if window_id in seen_window_ids:
            raise ValueError(f"duplicate test window_id: {window_id}")
        seen_window_ids.add(window_id)
        test_start = _require_aware_datetime(
            window.get("test_start"),
            f"test_windows[{index}].test_start",
        )
        test_end = _require_aware_datetime(
            window.get("test_end"),
            f"test_windows[{index}].test_end",
        )
        if test_start >= test_end:
            raise ValueError(f"test_start must precede test_end: window_id={window_id}")
        normalized.append(
            {
                "window_id": window_id,
                "test_start": test_start,
                "test_end": test_end,
            }
        )
    ordered = tuple(
        sorted(
            normalized,
            key=lambda window: (window["test_start"], window["window_id"]),
        )
    )
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous["test_end"] > current["test_start"]:
            raise ValueError(
                "test windows must be chronological and non-overlapping: "
                f"previous={previous['window_id']}, current={current['window_id']}"
            )
    return ordered


def _freeze_candidate_identities(
    observations: tuple[_NormalizedObservation, ...],
) -> tuple[FrozenCandidateIdentity, ...]:
    identities = {
        observation["candidate_id"]: observation["candidate_identity_hash"]
        for observation in observations
    }
    return tuple(
        {
            "candidate_id": candidate_id,
            "candidate_identity_hash": candidate_identity_hash,
        }
        for candidate_id, candidate_identity_hash in sorted(identities.items())
    )


def _candidate_set_hash(
    identities: tuple[FrozenCandidateIdentity, ...],
) -> str:
    payload = {
        "version": PURGED_ROLLING_ORIGIN_VERSION,
        "candidate_identities": identities,
    }
    return _canonical_hash(payload)


def _fold_id(
    window: _NormalizedTestWindow,
    embargo: timedelta,
    train_ids: tuple[str, ...],
    test_ids: tuple[str, ...],
    frozen_candidate_set_hash: str,
) -> str:
    payload = {
        "version": PURGED_ROLLING_ORIGIN_VERSION,
        "window_id": window["window_id"],
        "test_start": _isoformat_utc(window["test_start"]),
        "test_end": _isoformat_utc(window["test_end"]),
        "embargo_seconds": int(embargo.total_seconds()),
        "train_observation_ids": train_ids,
        "test_observation_ids": test_ids,
        "frozen_candidate_set_hash": frozen_candidate_set_hash,
    }
    return f"purged-origin:{window['window_id']}:{_canonical_hash(payload)[:20]}"


def _fold_status(
    train_count: int,
    test_count: int,
    minimum_train_observations: int,
    minimum_test_observations: int,
) -> str:
    train_sufficient = train_count >= minimum_train_observations
    test_sufficient = test_count >= minimum_test_observations
    if train_sufficient and test_sufficient:
        return "eligible_for_protected_evaluation"
    if not train_sufficient and not test_sufficient:
        return "insufficient_train_and_test_observations"
    if not train_sufficient:
        return "insufficient_train_observations"
    return "insufficient_test_observations"


def _observation_ids(
    observations: tuple[_NormalizedObservation, ...],
) -> tuple[str, ...]:
    return tuple(observation["observation_id"] for observation in observations)


def _intervals_overlap_test_window(
    observation: _NormalizedObservation,
    window: _NormalizedTestWindow,
) -> bool:
    return (
        observation["label_start_time"] < window["test_end"]
        and observation["label_end_time"] >= window["test_start"]
    )


def _validate_configuration(
    embargo: timedelta,
    minimum_train_observations: int,
    minimum_test_observations: int,
) -> None:
    if not isinstance(embargo, timedelta):
        raise TypeError("embargo must be a datetime.timedelta")
    if embargo < timedelta(0):
        raise ValueError("embargo must not be negative")
    _require_positive_integer(
        minimum_train_observations,
        "minimum_train_observations",
    )
    _require_positive_integer(
        minimum_test_observations,
        "minimum_test_observations",
    )


def _require_positive_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_nonempty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_sha256(value: object, field_name: str) -> str:
    normalized = _require_nonempty_string(value, field_name).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase or uppercase SHA-256")
    return normalized


def _require_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _require_group_ids(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{field_name} must be a non-empty tuple")
    normalized = tuple(
        _require_nonempty_string(group_id, f"{field_name}[]") for group_id in value
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicate group IDs")
    return tuple(sorted(normalized))


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
