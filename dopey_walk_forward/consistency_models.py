"""Deterministic offline walk-forward consistency models (paper-only).

Workstream A of `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`.

Models:
  WalkForwardSplit          — single train/validation/holdout split.
  WalkForwardSplitSet       — collection of splits with a deterministic seed.
  RollingWalkForwardPlan    — rolling-window plan (≥ 3 splits).
  BlockedWalkForwardPlan    — blocked-window plan (≥ 2 splits, no train leakage).
  HoldoutWindowSet          — distinct holdout windows used across plans.
  ConsistencyReplayCase     — deterministic replay case for a (strategy, split) pair.

All models are stdlib dataclasses, no pydantic, no network. They are the contracts consumed
by the consistency runner, scoring, and the meta-governor / ensemble / audit layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


STRONGER_WF_CONSISTENCY_VERSION = "dopey-stronger-walk-forward-consistency-v1"

ALLOWED_SPLIT_TYPES: tuple[str, ...] = (
    "rolling",
    "blocked",
    "anchored",
    "regime_holdout",
    "stress_holdout",
)


@dataclass(frozen=True)
class WalkForwardSplit:
    split_id: str
    train_windows: tuple[str, ...]
    validation_windows: tuple[str, ...]
    holdout_windows: tuple[str, ...]
    regime_tags: tuple[str, ...]
    split_type: str = "rolling"
    notes: str = ""

    def __post_init__(self) -> None:
        if self.split_type not in ALLOWED_SPLIT_TYPES:
            raise ValueError(f"unknown split_type: {self.split_type}")
        if not self.train_windows:
            raise ValueError(f"split {self.split_id} has no train windows")
        if not self.validation_windows and self.split_type != "stress_holdout":
            raise ValueError(f"split {self.split_id} has no validation windows")
        if not self.holdout_windows:
            raise ValueError(f"split {self.split_id} has no holdout windows")
        if not self.regime_tags:
            raise ValueError(f"split {self.split_id} has no regime tags")
        # Detect leakage: holdout windows must not appear in train or validation.
        train_set = set(self.train_windows)
        val_set = set(self.validation_windows)
        for h in self.holdout_windows:
            if h in train_set:
                raise ValueError(f"split {self.split_id}: holdout {h} leaks into train")
            if h in val_set:
                raise ValueError(f"split {self.split_id}: holdout {h} leaks into validation")

    def to_dict(self) -> dict:
        return {
            "split_id": self.split_id,
            "train_windows": list(self.train_windows),
            "validation_windows": list(self.validation_windows),
            "holdout_windows": list(self.holdout_windows),
            "regime_tags": list(self.regime_tags),
            "split_type": self.split_type,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class WalkForwardSplitSet:
    plan_id: str
    splits: tuple[WalkForwardSplit, ...]

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "splits": [s.to_dict() for s in self.splits],
            "split_count": len(self.splits),
        }

    def split_ids(self) -> tuple[str, ...]:
        return tuple(s.split_id for s in self.splits)

    def split_types(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.splits:
            counts[s.split_type] = counts.get(s.split_type, 0) + 1
        return counts


@dataclass(frozen=True)
class RollingWalkForwardPlan:
    plan_id: str
    splits: tuple[WalkForwardSplit, ...]
    window_count: int
    holdout_count: int
    regime_coverage: tuple[str, ...]
    target_families: tuple[str, ...]
    deterministic_seed: str
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "splits": [s.to_dict() for s in self.splits],
            "window_count": self.window_count,
            "holdout_count": self.holdout_count,
            "regime_coverage": list(self.regime_coverage),
            "target_families": list(self.target_families),
            "deterministic_seed": self.deterministic_seed,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class BlockedWalkForwardPlan:
    plan_id: str
    splits: tuple[WalkForwardSplit, ...]
    window_count: int
    holdout_count: int
    regime_coverage: tuple[str, ...]
    target_families: tuple[str, ...]
    deterministic_seed: str
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "splits": [s.to_dict() for s in self.splits],
            "window_count": self.window_count,
            "holdout_count": self.holdout_count,
            "regime_coverage": list(self.regime_coverage),
            "target_families": list(self.target_families),
            "deterministic_seed": self.deterministic_seed,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HoldoutWindowSet:
    set_id: str
    window_ids: tuple[str, ...]
    regime_tags: tuple[str, ...]
    coverage_holds: tuple[str, ...] = ()   # e.g. ("regime_holdout", "stress_holdout")
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "set_id": self.set_id,
            "window_ids": list(self.window_ids),
            "regime_tags": list(self.regime_tags),
            "coverage_holds": list(self.coverage_holds),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ConsistencyReplayCase:
    case_id: str
    split_id: str
    strategy_id: str
    strategy_family: str
    expected_kind: str                       # rolling | blocked | anchored | regime_holdout | stress_holdout
    train_window_ids: tuple[str, ...]
    validation_window_ids: tuple[str, ...]
    holdout_window_ids: tuple[str, ...]
    regime_tags: tuple[str, ...]
    reproducible: bool = True
    safety_state: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "split_id": self.split_id,
            "strategy_id": self.strategy_id,
            "strategy_family": self.strategy_family,
            "expected_kind": self.expected_kind,
            "train_window_ids": list(self.train_window_ids),
            "validation_window_ids": list(self.validation_window_ids),
            "holdout_window_ids": list(self.holdout_window_ids),
            "regime_tags": list(self.regime_tags),
            "reproducible": self.reproducible,
            "safety_state": dict(self.safety_state),
        }


# ---------------------------------------------------------------------------
# Convenience constructors used by tests and the runner.
# ---------------------------------------------------------------------------

def make_split(
    split_id: str,
    train: list[str],
    validation: list[str],
    holdout: list[str],
    regime_tags: list[str],
    split_type: str = "rolling",
    notes: str = "",
) -> WalkForwardSplit:
    return WalkForwardSplit(
        split_id=split_id,
        train_windows=tuple(train),
        validation_windows=tuple(validation),
        holdout_windows=tuple(holdout),
        regime_tags=tuple(regime_tags),
        split_type=split_type,
        notes=notes,
    )


def split_set_from_dict(record: dict) -> WalkForwardSplitSet:
    splits = [
        WalkForwardSplit(
            split_id=s["split_id"],
            train_windows=tuple(s.get("train_windows", [])),
            validation_windows=tuple(s.get("validation_windows", [])),
            holdout_windows=tuple(s.get("holdout_windows", [])),
            regime_tags=tuple(s.get("regime_tags", [])),
            split_type=s.get("split_type", "rolling"),
            notes=s.get("notes", ""),
        )
        for s in record.get("splits", [])
    ]
    return WalkForwardSplitSet(plan_id=record.get("plan_id", "split-set"), splits=tuple(splits))
