"""Process-owned leases with stale-state quarantine and explicit recovery."""

from __future__ import annotations

import json
import os
import uuid
import ctypes
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


class LeaseAlreadyHeldError(RuntimeError):
    """Raised when a live process owns the requested operation lease."""


def _process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            process_id,
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _load_lease(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"operation lease contains invalid JSON and must be quarantined: path={path}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"operation lease must be an object: path={path}")
    return value


def _quarantine_lease(path: Path, quarantine_directory: Path, reason: str) -> Path:
    quarantine_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = quarantine_directory / f"{path.stem}.{timestamp}.{reason}.json"
    os.replace(path, target)
    return target


def _create_lease(path: Path, ttl_seconds: int) -> dict[str, Any]:
    if ttl_seconds <= 0:
        raise ValueError(f"operation lease ttl must be positive: ttl_seconds={ttl_seconds}")
    acquired_at = datetime.now(timezone.utc)
    record: dict[str, Any] = {
        "artifact_type": "dopey_operation_lease",
        "lease_version": "dopey-chronos-process-lease-v1",
        "lease_id": str(uuid.uuid4()),
        "process_id": os.getpid(),
        "acquired_at": acquired_at.isoformat(),
        "expires_at": (acquired_at + timedelta(seconds=ttl_seconds)).isoformat(),
        "paper_only": True,
        "live_blocked": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


@contextmanager
def operation_lease(
    path: Path,
    ttl_seconds: int,
    quarantine_directory: Path,
) -> Iterator[dict[str, Any]]:
    owned: dict[str, Any] | None = None
    for attempt in range(2):
        try:
            owned = _create_lease(path, ttl_seconds)
            break
        except FileExistsError as exc:
            try:
                existing = _load_lease(path)
            except (ValueError, TypeError):
                _quarantine_lease(path, quarantine_directory, "corrupt")
                if attempt == 0:
                    continue
                raise
            process_id = int(existing.get("process_id", 0) or 0)
            if _process_is_alive(process_id):
                raise LeaseAlreadyHeldError(
                    "operation lease is held by a live process: "
                    f"path={path}, process_id={process_id}, lease_id={existing.get('lease_id', '')}"
                ) from exc
            _quarantine_lease(path, quarantine_directory, "stale_process")
            if attempt == 0:
                continue
            raise RuntimeError(f"operation lease stale recovery failed: path={path}") from exc
    if owned is None:
        raise RuntimeError(f"operation lease could not be acquired: path={path}")
    try:
        yield owned
    finally:
        if path.exists():
            current = _load_lease(path)
            if current.get("lease_id") != owned["lease_id"]:
                raise RuntimeError(
                    "operation lease ownership changed before release: "
                    f"path={path}, expected={owned['lease_id']}, actual={current.get('lease_id', '')}"
                )
            path.unlink()
