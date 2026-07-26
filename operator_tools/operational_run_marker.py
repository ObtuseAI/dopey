"""Fail-closed overlap markers for independently scheduled DOPEY operations."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dopey_autonomy.run_resilient_research_supervisor import supervisor_run_active
from dopey_research_pipeline.artifact_io import append_jsonl, write_json_atomic


REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_ROOT = REPO_ROOT / "artifacts" / "dopey" / "observability" / "operational_runs"
ALLOWED_RUN_NAMES = frozenset({"daily_ritual"})
MAX_ACTIVE_AGE_SECONDS = 6 * 3600
CORRUPT_MARKER_STALE_SECONDS = 15 * 60


def marker_path(run_name: str) -> Path:
    if run_name not in ALLOWED_RUN_NAMES:
        raise ValueError(f"unsupported operational run name: run_name={run_name}")
    return MARKER_ROOT / f"{run_name}.json"


def _read_marker(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"operational marker is unreadable and was preserved: path={path}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"operational marker must be a JSON object: path={path}")
    return value


def _started_at(marker: dict[str, Any], path: Path) -> datetime:
    raw_started = marker.get("started_at_utc")
    if not isinstance(raw_started, str) or not raw_started:
        raise RuntimeError(f"operational marker is missing started_at_utc: path={path}")
    try:
        started = datetime.fromisoformat(raw_started.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(f"operational marker timestamp is invalid: path={path}, value={raw_started}") from error
    if started.tzinfo is None:
        raise RuntimeError(f"operational marker timestamp must be timezone-aware: path={path}")
    return started.astimezone(timezone.utc)


def operational_run_active(run_name: str, now_utc: datetime) -> bool:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    path = marker_path(run_name)
    if not path.exists():
        return False
    try:
        marker = _read_marker(path)
        started_at = _started_at(marker, path)
    except RuntimeError as error:
        return _recover_stale_corrupt_marker(path, now_utc, error)
    age_seconds = (
        now_utc.astimezone(timezone.utc) - started_at
    ).total_seconds()
    if age_seconds < 0:
        raise RuntimeError(f"operational marker timestamp is in the future: path={path}, age_seconds={age_seconds}")
    return age_seconds <= MAX_ACTIVE_AGE_SECONDS


def _recover_stale_corrupt_marker(
    path: Path,
    now_utc: datetime,
    error: RuntimeError,
) -> bool:
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_seconds = (
        now_utc.astimezone(timezone.utc) - modified_at
    ).total_seconds()
    if age_seconds < 0:
        raise RuntimeError(
            "operational marker filesystem timestamp is in the future: "
            f"path={path}, age_seconds={age_seconds}"
        ) from error
    if age_seconds <= CORRUPT_MARKER_STALE_SECONDS:
        raise RuntimeError(
            "recent unreadable operational marker was preserved fail-closed: "
            f"path={path}, age_seconds={age_seconds}"
        ) from error
    recovered_at = now_utc.astimezone(timezone.utc)
    archive = path.with_name(
        f"{path.stem}.corrupt.{recovered_at.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    )
    os.replace(path, archive)
    append_jsonl(
        MARKER_ROOT / "operational_marker_recovery.jsonl",
        {
            "artifact_type": "dopey_operational_marker_recovery",
            "run_name": path.stem,
            "recovery_status": "stale_corrupt_marker_archived",
            "source_path": str(path),
            "archive_path": str(archive),
            "marker_age_seconds": round(age_seconds, 3),
            "error_type": type(error).__name__,
            "error": str(error),
            "recovered_at_utc": recovered_at.isoformat(),
            "paper_only": True,
            "live_blocked": True,
        },
    )
    return False


def acquire_marker(run_name: str, now_utc: datetime) -> dict[str, Any]:
    path = marker_path(run_name)
    if supervisor_run_active():
        raise RuntimeError(
            f"operational run cannot overlap the active research supervisor: run_name={run_name}"
        )
    if operational_run_active(run_name, now_utc):
        raise RuntimeError(f"operational run is already active: run_name={run_name}, marker={path}")
    if path.exists():
        stale = _read_marker(path)
        stale_started = _started_at(stale, path).strftime("%Y%m%dT%H%M%SZ")
        archive = path.with_name(f"{path.stem}.stale.{stale_started}.json")
        os.replace(path, archive)
    record: dict[str, Any] = {
        "artifact_type": "dopey_operational_run_marker",
        "run_name": run_name,
        "run_status": "running",
        "started_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
        "maximum_active_age_seconds": MAX_ACTIVE_AGE_SECONDS,
        "owner": "scheduled_command_wrapper",
        "broker_authority": False,
        "order_authority": False,
    }
    write_json_atomic(path, record)
    return record


def release_marker(run_name: str, now_utc: datetime) -> dict[str, Any]:
    path = marker_path(run_name)
    if not path.exists():
        raise FileNotFoundError(f"operational marker is missing during release: path={path}")
    marker = _read_marker(path)
    record = {
        **marker,
        "run_status": "complete",
        "finished_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
    }
    write_json_atomic(MARKER_ROOT / f"{run_name}_last_complete.json", record)
    path.unlink()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("acquire", "release", "check-clear", "status"))
    parser.add_argument("run_name", choices=tuple(sorted(ALLOWED_RUN_NAMES)))
    args = parser.parse_args()
    now_utc = datetime.now(timezone.utc)
    if args.action == "acquire":
        result = acquire_marker(args.run_name, now_utc)
    elif args.action == "release":
        result = release_marker(args.run_name, now_utc)
    else:
        active = operational_run_active(args.run_name, now_utc)
        result = {"run_name": args.run_name, "active": active}
        if args.action == "check-clear" and active:
            print(json.dumps(result, indent=2, sort_keys=True))
            return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
