"""Leak-safe replay-era definitions and causal ordering."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import StrEnum
from typing import Any


class ReplayRole(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    HELD_OUT = "HELD_OUT"
    CONTESTED_TRUTH = "CONTESTED_TRUTH"


@dataclass(frozen=True)
class ReplayEra:
    era_id: str
    start_date: str
    end_date: str
    role: ReplayRole

    def to_dict(self) -> dict[str, str]:
        value = asdict(self)
        value["role"] = self.role.value
        return value


def validate_replay_eras(eras: tuple[ReplayEra, ...]) -> dict[str, Any]:
    if not eras:
        raise ValueError("isolated replay requires at least one era")
    if len({era.era_id for era in eras}) != len(eras):
        raise ValueError("isolated replay era identities must be unique")
    ordered = sorted(eras, key=lambda era: (era.start_date, era.end_date, era.era_id))
    prior_end: date | None = None
    for era in ordered:
        start = date.fromisoformat(era.start_date)
        end = date.fromisoformat(era.end_date)
        if start > end:
            raise ValueError(f"replay era starts after it ends: era_id={era.era_id}")
        if prior_end is not None and start <= prior_end:
            raise ValueError(f"replay eras overlap or touch without purge gap: era_id={era.era_id}")
        prior_end = end
    if not any(era.role is ReplayRole.HELD_OUT for era in eras):
        raise ValueError("isolated replay requires a sealed held-out era")
    return {
        "artifact_type": "chronos_replay_era_validation",
        "era_count": len(eras),
        "roles": sorted({era.role.value for era in eras}),
        "overlap_detected": False,
        "held_out_present": True,
        "paper_only": True,
        "live_blocked": True,
    }
