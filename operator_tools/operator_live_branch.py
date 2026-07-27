"""Run or preflight the DOPEY Live Branch."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

from dopey_live.dumbmoney_authority import DumbMoneyAuthorityContext
from dopey_live.dumbmoney_command_feed import DumbMoneyCommandDispatch
from dopey_live.dumbmoney_promotion import PromotionAuthorityResolver
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


def _run_with_crash_tombstone(
    execute_orders: bool,
    dumbmoney_authority: DumbMoneyAuthorityContext | None = None,
    *,
    dumbmoney_controls: DumbMoneyCommandDispatch | None = None,
    dumbmoney_control_refresh: (
        Callable[[datetime], DumbMoneyCommandDispatch] | None
    ) = None,
    dumbmoney_promotion_resolver: PromotionAuthorityResolver | None = None,
) -> dict[str, object]:
    if execute_orders:
        raise RuntimeError(
            "Legacy operator execution is disabled; use the supervised "
            "DumbMoney Windows service"
        )
    started_at_utc = datetime.now(timezone.utc)
    try:
        with _exclusive_live_process(started_at_utc):
            resolved_controls = dumbmoney_controls
            if (
                resolved_controls is None
                and dumbmoney_authority is None
                and dumbmoney_control_refresh is not None
            ):
                resolved_controls = dumbmoney_control_refresh(started_at_utc)
            arguments = (
                REPOSITORY_ROOT,
                default_gateway(),
                started_at_utc,
                execute_orders,
            )
            if (
                dumbmoney_authority is None
                and resolved_controls is None
                and dumbmoney_control_refresh is None
            ):
                return run_live_branch_cycle(*arguments)
            return run_live_branch_cycle(
                *arguments,
                dumbmoney_authority=dumbmoney_authority,
                dumbmoney_controls=resolved_controls,
                dumbmoney_control_refresh=dumbmoney_control_refresh,
                dumbmoney_promotion_resolver=dumbmoney_promotion_resolver,
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


def run_supervised_dumbmoney_cycle(
    command_feed_poll: Callable[[datetime], DumbMoneyCommandDispatch],
    promotion_resolver: PromotionAuthorityResolver,
    *,
    execute_orders: bool,
) -> dict[str, object]:
    """Run one process-locked cycle with initial and broker-boundary feed polls."""

    return _run_with_crash_tombstone(
        execute_orders,
        dumbmoney_control_refresh=command_feed_poll,
        dumbmoney_promotion_resolver=promotion_resolver,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Operate DOPEY Live Branch through official Robinhood Agentic MCP"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Disabled legacy switch; production execution requires the "
            "supervised DumbMoney Windows service"
        ),
    )
    parser.add_argument(
        "--dumbmoney-strict",
        action="store_true",
        help=(
            "Require complete DumbMoney authority inputs for read-only legacy preflight"
        ),
    )
    parser.add_argument(
        "--dumbmoney-envelope",
        type=Path,
        help="Opt in to DumbMoney authority with this signed CapitalEnvelopeV1",
    )
    parser.add_argument(
        "--dumbmoney-public-key",
        type=Path,
        help="Trusted DumbMoney Ed25519 public key (raw, hex, or base64url)",
    )
    parser.add_argument(
        "--dumbmoney-account-hash",
        help="Pinned lowercase SHA-256 of the dedicated Agentic account ID",
    )
    arguments = parser.parse_args()
    if arguments.execute:
        parser.error(
            "--execute is disabled in the legacy operator; use "
            "dopey_live.dumbmoney_windows_service"
        )
    dumbmoney_values = (
        arguments.dumbmoney_envelope,
        arguments.dumbmoney_public_key,
        arguments.dumbmoney_account_hash,
    )
    if any(value is not None for value in dumbmoney_values) and not all(
        value is not None for value in dumbmoney_values
    ):
        parser.error(
            "DumbMoney mode requires --dumbmoney-envelope, "
            "--dumbmoney-public-key, and --dumbmoney-account-hash together"
        )
    if arguments.dumbmoney_strict and not all(
        value is not None for value in dumbmoney_values
    ):
        parser.error(
            "--dumbmoney-strict requires the complete DumbMoney envelope, "
            "public key, and account hash"
        )
    authority = (
        DumbMoneyAuthorityContext.from_files(
            arguments.dumbmoney_envelope,
            arguments.dumbmoney_public_key,
            arguments.dumbmoney_account_hash,
        )
        if all(value is not None for value in dumbmoney_values)
        else None
    )
    result = _run_with_crash_tombstone(
        False,
        authority,
    )
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
