"""Run or preflight the DOPEY Live Branch."""
from __future__ import annotations

import argparse
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from dopey_live.ledger import write_latest_cycle
from dopey_live.service import default_gateway, run_live_branch_cycle


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROCESS_LOCK_STALE_AGE = timedelta(minutes=15)


def _process_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    try:
        os.kill(process_id, 0)
    except (OSError, OverflowError):
        return False
    return True


def _recoverable_existing_process_lock(
    lock_path: Path,
    now_utc: datetime,
) -> Path:
    age = now_utc.astimezone(timezone.utc) - datetime.fromtimestamp(
        lock_path.stat().st_mtime,
        tz=timezone.utc,
    )
    if age < timedelta(0):
        raise RuntimeError(
            f"Live Branch process lock is future-dated: lock={lock_path}, age={age}"
        )
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        if age < PROCESS_LOCK_STALE_AGE:
            raise RuntimeError(
                "Recent Live Branch process lock is unreadable and was preserved: "
                f"lock={lock_path}, age={age}"
            ) from error
        payload = {}
    if not isinstance(payload, dict):
        if age < PROCESS_LOCK_STALE_AGE:
            raise RuntimeError(
                "Recent Live Branch process lock is not an object and was preserved: "
                f"lock={lock_path}, age={age}"
            )
        payload = {}
    process_id = int(payload.get("process_id", 0) or 0)
    if _process_running(process_id):
        raise RuntimeError(
            "Another Live Branch process is still running: "
            f"lock={lock_path}, process_id={process_id}"
        )
    if age < PROCESS_LOCK_STALE_AGE:
        raise RuntimeError(
            "Dead-owner Live Branch process lock is too recent for automatic recovery: "
            f"lock={lock_path}, process_id={process_id}, age={age}"
        )
    archive_path = lock_path.with_name(
        f"{lock_path.name}.recovered.{now_utc.strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    os.replace(lock_path, archive_path)
    return archive_path


@contextmanager
def _exclusive_live_process(now_utc: datetime) -> Iterator[None]:
    lock_path = (
        REPOSITORY_ROOT
        / "artifacts"
        / "dopey"
        / "live_branch"
        / "live_branch_process.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        _recoverable_existing_process_lock(lock_path, now_utc)
    lock_id = uuid.uuid4().hex
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError as error:
        raise RuntimeError(
            f"Live Branch process lock was acquired concurrently: lock={lock_path}"
        ) from error
    try:
        encoded = json.dumps(
            {
                "lock_id": lock_id,
                "process_id": os.getpid(),
                "started_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
            },
            sort_keys=True,
        ).encode("utf-8")
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Live Branch process lock became unreadable: lock={lock_path}"
            ) from error
        if not isinstance(current, dict) or current.get("lock_id") != lock_id:
            raise RuntimeError(
                f"Live Branch process lock identity changed: lock={lock_path}"
            )
        lock_path.unlink()


def _run_with_crash_tombstone(execute_orders: bool) -> dict[str, object]:
    started_at_utc = datetime.now(timezone.utc)
    try:
        with _exclusive_live_process(started_at_utc):
            return run_live_branch_cycle(
                REPOSITORY_ROOT,
                default_gateway(),
                started_at_utc,
                execute_orders,
            )
    except Exception as error:
        tombstone: dict[str, object] = {
            "schema_version": "dopey-live-branch-cycle-v2",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "started_at_utc": started_at_utc.isoformat(),
            "cycle_status": "cycle_crashed_unhandled",
            "execute_orders_requested": execute_orders,
            "error_type": type(error).__name__,
            "error": str(error)[:2000],
            "orders": [],
            "stale_prior_success_hidden": True,
        }
        try:
            write_latest_cycle(REPOSITORY_ROOT, tombstone)
        except Exception as tombstone_error:
            raise RuntimeError(
                "Live Branch crashed and its crash tombstone could not be written: "
                f"cycle_error={type(error).__name__}: {error}; "
                f"tombstone_error={type(tombstone_error).__name__}: {tombstone_error}"
            ) from error
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate DOPEY Live Branch through official Robinhood Agentic MCP")
    parser.add_argument("--execute", action="store_true", help="Submit eligible reviewed orders while the market is open")
    arguments = parser.parse_args()
    result = _run_with_crash_tombstone(bool(arguments.execute))
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    cycle_status = str(result.get("cycle_status", ""))
    successful_statuses = {
        "complete",
        "market_closed_monitoring_complete",
        "preflight_complete",
    }
    return 0 if cycle_status in successful_statuses else 2


if __name__ == "__main__":
    raise SystemExit(main())
