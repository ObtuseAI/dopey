"""Disk-watermark telemetry and fail-closed scheduler backpressure."""

from __future__ import annotations

import shutil
from enum import StrEnum
from pathlib import Path
from typing import Final, TypedDict


class StoragePressureLevel(StrEnum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


class StoragePressureState(TypedDict):
    pressure_level: StoragePressureLevel
    total_bytes: int
    used_bytes: int
    free_bytes: int
    free_fraction: float
    artifact_bytes: int | None
    artifact_file_count: int | None
    write_backpressure_active: bool
    deletion_performed: bool


CRITICAL_FREE_BYTES: Final[int] = 5 * 1024**3
ELEVATED_FREE_BYTES: Final[int] = 10 * 1024**3
CRITICAL_FREE_FRACTION: Final[float] = 0.05
ELEVATED_FREE_FRACTION: Final[float] = 0.10
WRITE_HEAVY_LANES: Final[frozenset[str]] = frozenset(
    {
        "governed_universe_growth",
        "symbol_intelligence_lab",
        "vnext_forward_research",
        "strategy_engineering_research",
        "evidence_intelligence",
    }
)


def _artifact_inventory(artifact_root: Path) -> tuple[int, int]:
    total_bytes = 0
    file_count = 0
    if not artifact_root.exists():
        return total_bytes, file_count
    for path in artifact_root.rglob("*"):
        if not path.is_file():
            continue
        total_bytes += path.stat().st_size
        file_count += 1
    return total_bytes, file_count


def measure_storage_pressure(
    repo_root: Path,
    include_artifact_inventory: bool,
) -> StoragePressureState:
    usage = shutil.disk_usage(repo_root)
    free_fraction = usage.free / float(usage.total)
    if (
        usage.free < CRITICAL_FREE_BYTES
        or free_fraction < CRITICAL_FREE_FRACTION
    ):
        level = StoragePressureLevel.CRITICAL
    elif (
        usage.free < ELEVATED_FREE_BYTES
        or free_fraction < ELEVATED_FREE_FRACTION
    ):
        level = StoragePressureLevel.ELEVATED
    else:
        level = StoragePressureLevel.NORMAL
    artifact_bytes: int | None = None
    artifact_file_count: int | None = None
    if include_artifact_inventory:
        artifact_bytes, artifact_file_count = _artifact_inventory(
            repo_root / "artifacts"
        )
    return {
        "pressure_level": level,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_fraction": round(free_fraction, 8),
        "artifact_bytes": artifact_bytes,
        "artifact_file_count": artifact_file_count,
        "write_backpressure_active": level is StoragePressureLevel.CRITICAL,
        "deletion_performed": False,
    }


def storage_blocker_for_lane(
    lane_id: str,
    pressure: StoragePressureState,
) -> str | None:
    if (
        pressure["write_backpressure_active"]
        and lane_id in WRITE_HEAVY_LANES
    ):
        return "critical_storage_pressure"
    return None
