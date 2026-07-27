"""Hash-chained Live Branch and paper-twin accounting."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final, Iterator


LEDGER_SCHEMA: Final[str] = "dopey-live-branch-ledger-v1"
GENESIS_HASH: Final[str] = "0" * 64
OPERATOR_RECONCILIATION_CONFIRMATION: Final[str] = (
    "I_VERIFIED_THIS_INTENT_IN_OFFICIAL_BROKER_HISTORY"
)
OPERATOR_LOCK_RECOVERY_CONFIRMATION: Final[str] = (
    "I_VERIFIED_NO_LIVE_LEDGER_WRITER_IS_RUNNING"
)
MINIMUM_STALE_LOCK_AGE: Final[timedelta] = timedelta(minutes=15)


class LiveBranchLedgerError(RuntimeError):
    """Raised when the append-only Live Branch ledger is invalid."""


def artifact_root(repository_root: Path) -> Path:
    return repository_root.resolve() / "artifacts" / "dopey" / "live_branch"


def ledger_path(repository_root: Path) -> Path:
    return artifact_root(repository_root) / "live_branch_ledger.jsonl"


def paper_twin_path(repository_root: Path) -> Path:
    return artifact_root(repository_root) / "paper_twin_ledger.jsonl"


def latest_cycle_path(repository_root: Path) -> Path:
    return artifact_root(repository_root) / "latest_cycle.json"


def _stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def read_ledger(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        return ()
    records: list[dict[str, Any]] = []
    previous_hash = GENESIS_HASH
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as error:
            raise LiveBranchLedgerError(
                f"Invalid ledger JSON: path={path}, line={line_number}, error={error}"
            ) from error
        if not isinstance(record, dict):
            raise LiveBranchLedgerError(
                f"Ledger row must be an object: path={path}, line={line_number}"
            )
        record_hash = str(record.get("record_hash", ""))
        hash_payload = dict(record)
        hash_payload.pop("record_hash", None)
        if (
            record.get("previous_hash") != previous_hash
            or _stable_hash(hash_payload) != record_hash
        ):
            raise LiveBranchLedgerError(
                f"Ledger hash chain mismatch: path={path}, line={line_number}"
            )
        records.append(record)
        previous_hash = record_hash
    return tuple(records)


@contextmanager
def _exclusive_ledger_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise LiveBranchLedgerError(
            f"Ledger is locked by another writer or requires operator recovery: path={path}, lock={lock_path}"
        ) from error
    try:
        lock_payload = json.dumps(
            {
                "ledger_path": str(path.resolve()),
                "process_id": os.getpid(),
                "locked_utc": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        ).encode("utf-8")
        os.write(descriptor, lock_payload)
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError as error:
            raise LiveBranchLedgerError(
                f"Ledger lock disappeared during write: path={path}, lock={lock_path}"
            ) from error


def _append_record_unlocked(
    path: Path,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    existing = read_ledger(path)
    previous_hash = str(existing[-1]["record_hash"]) if existing else GENESIS_HASH
    record = {
        "schema_version": LEDGER_SCHEMA,
        "event_type": event_type,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "previous_hash": previous_hash,
        "payload": payload,
    }
    record["record_hash"] = _stable_hash(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def append_record(
    path: Path, event_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    with _exclusive_ledger_lock(path):
        return _append_record_unlocked(path, event_type, payload)


def _process_is_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    try:
        os.kill(process_id, 0)
    except (OSError, OverflowError):
        return False
    return True


def recover_stale_ledger_lock_after_operator_verification(
    repository_root: Path,
    ledger_name: str,
    operator_confirmation: str,
    now_utc: datetime,
) -> dict[str, Any]:
    if operator_confirmation != OPERATOR_LOCK_RECOVERY_CONFIRMATION:
        raise LiveBranchLedgerError(
            "Live Branch ledger lock recovery requires exact operator confirmation"
        )
    if now_utc.tzinfo is None:
        raise LiveBranchLedgerError(
            "Live Branch ledger lock recovery requires a timezone-aware timestamp"
        )
    paths = {
        "live": ledger_path(repository_root),
        "paper-twin": paper_twin_path(repository_root),
    }
    if ledger_name not in paths:
        raise LiveBranchLedgerError(
            f"Unsupported Live Branch ledger lock name: ledger_name={ledger_name!r}"
        )
    path = paths[ledger_name]
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    if not lock_path.is_file():
        raise LiveBranchLedgerError(
            f"Live Branch ledger lock does not exist: lock={lock_path}"
        )
    try:
        lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LiveBranchLedgerError(
            f"Live Branch ledger lock is unreadable and was preserved: lock={lock_path}"
        ) from error
    if not isinstance(lock_payload, dict):
        raise LiveBranchLedgerError(
            f"Live Branch ledger lock must be an object: lock={lock_path}"
        )
    try:
        process_id = int(lock_payload.get("process_id", 0))
        locked_utc = datetime.fromisoformat(
            str(lock_payload.get("locked_utc", "")).replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as error:
        raise LiveBranchLedgerError(
            f"Live Branch ledger lock identity is invalid and was preserved: lock={lock_path}"
        ) from error
    if locked_utc.tzinfo is None:
        raise LiveBranchLedgerError(
            f"Live Branch ledger lock timestamp must be timezone-aware: lock={lock_path}"
        )
    if str(lock_payload.get("ledger_path", "")) != str(path.resolve()):
        raise LiveBranchLedgerError(
            "Live Branch ledger lock path binding is invalid and was preserved: "
            f"lock={lock_path}, ledger={path}"
        )
    age = now_utc.astimezone(timezone.utc) - locked_utc.astimezone(timezone.utc)
    if age < timedelta(0):
        raise LiveBranchLedgerError(
            f"Live Branch ledger lock is future-dated: lock={lock_path}, age={age}"
        )
    if age < MINIMUM_STALE_LOCK_AGE:
        raise LiveBranchLedgerError(
            "Live Branch ledger lock is too recent for operator recovery: "
            f"lock={lock_path}, age={age}, minimum_age={MINIMUM_STALE_LOCK_AGE}"
        )
    if _process_is_running(process_id):
        raise LiveBranchLedgerError(
            "Live Branch ledger lock owner PID is still running; recovery refused: "
            f"lock={lock_path}, process_id={process_id}"
        )
    read_ledger(path)
    recovered_at = now_utc.astimezone(timezone.utc)
    archive_path = lock_path.with_name(
        f"{lock_path.name}.recovered.{recovered_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    os.replace(lock_path, archive_path)
    try:
        return append_record(
            path,
            "ledger_lock_recovered_after_operator_verification",
            {
                "ledger_name": ledger_name,
                "stale_lock_process_id": process_id,
                "stale_lock_locked_utc": locked_utc.astimezone(
                    timezone.utc
                ).isoformat(),
                "stale_lock_age_seconds": round(age.total_seconds(), 3),
                "stale_lock_payload_hash": _stable_hash(lock_payload),
                "archived_lock_path": str(archive_path),
                "operator_confirmation": operator_confirmation,
                "broker_connection_used": False,
            },
        )
    except (OSError, LiveBranchLedgerError):
        if not lock_path.exists() and archive_path.exists():
            os.replace(archive_path, lock_path)
        raise


def _intent_submission_is_unresolved(
    records: tuple[dict[str, Any], ...],
    intent_id: str,
) -> bool:
    unresolved = False
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("intent_id") != intent_id:
            continue
        event_type = str(record.get("event_type", ""))
        if event_type in {
            "live_order_submission_reserved",
            "live_order_submission_started",
            "live_order_submission_ambiguous",
        }:
            unresolved = True
        elif event_type == "live_order_result":
            unresolved = payload.get("placed") is True
    return unresolved


def intent_already_submitted(repository_root: Path, intent_id: str) -> bool:
    return _intent_submission_is_unresolved(
        read_ledger(ledger_path(repository_root)),
        intent_id,
    )


def reserve_intent(
    repository_root: Path,
    intent_id: str,
    payload: dict[str, Any],
) -> bool:
    path = ledger_path(repository_root)
    with _exclusive_ledger_lock(path):
        records = read_ledger(path)
        if _intent_submission_is_unresolved(records, intent_id):
            return False
        _append_record_unlocked(
            path,
            "live_order_submission_reserved",
            {"intent_id": intent_id, **payload},
        )
    return True


def activate_dumbmoney_fence(
    repository_root: Path,
    envelope_id: str,
    event_id: str,
    body_digest: str,
    fencing_generation: int,
    policy_epoch: int,
) -> dict[str, Any]:
    """Persist the highest signed fund-control generation under the ledger lock.

    The existing local process and ledger locks prevent concurrent writers on
    one host. This monotonic fence additionally rejects a stale control-plane
    process even after it reacquires a local lock.
    """
    if fencing_generation <= 0 or policy_epoch <= 0:
        raise LiveBranchLedgerError(
            "DumbMoney fence generation and policy epoch must be positive"
        )
    for label, digest in (
        ("envelope_id", envelope_id),
        ("event_id", event_id),
        ("body_digest", body_digest),
    ):
        if not isinstance(digest, str) or len(digest) != 64 or digest.lower() != digest:
            raise LiveBranchLedgerError(
                f"DumbMoney fence {label} must be lowercase SHA-256 hex"
            )
        try:
            bytes.fromhex(digest)
        except ValueError as error:
            raise LiveBranchLedgerError(
                f"DumbMoney fence {label} must be lowercase SHA-256 hex"
            ) from error
    path = ledger_path(repository_root)
    with _exclusive_ledger_lock(path):
        records = read_ledger(path)
        latest: dict[str, Any] | None = None
        for record in records:
            if record.get("event_type") != "dumbmoney_fence_activated":
                continue
            payload = record.get("payload")
            if isinstance(payload, dict):
                latest = payload
        if latest is not None:
            latest_generation = int(latest.get("fencing_generation", 0))
            latest_epoch = int(latest.get("policy_epoch", 0))
            latest_envelope = str(latest.get("envelope_id", ""))
            latest_event = str(latest.get("event_id", ""))
            latest_body_digest = str(latest.get("body_digest", ""))
            if fencing_generation < latest_generation:
                raise LiveBranchLedgerError(
                    "DumbMoney CapitalEnvelopeV1 is fenced by a newer generation"
                )
            if policy_epoch < latest_epoch:
                raise LiveBranchLedgerError(
                    "DumbMoney CapitalEnvelopeV1 is fenced by a newer policy epoch"
                )
            if fencing_generation == latest_generation:
                if (
                    envelope_id != latest_envelope
                    or event_id != latest_event
                    or body_digest != latest_body_digest
                    or policy_epoch != latest_epoch
                ):
                    raise LiveBranchLedgerError(
                        "DumbMoney fence generation was reused with different authority"
                    )
                return dict(latest)
        payload = {
            "envelope_id": envelope_id,
            "event_id": event_id,
            "body_digest": body_digest,
            "fencing_generation": fencing_generation,
            "policy_epoch": policy_epoch,
        }
        _append_record_unlocked(path, "dumbmoney_fence_activated", payload)
        return payload


def assert_current_dumbmoney_fence(
    repository_root: Path,
    envelope_id: str,
    event_id: str,
    body_digest: str,
    fencing_generation: int,
    policy_epoch: int,
) -> None:
    path = ledger_path(repository_root)
    with _exclusive_ledger_lock(path):
        latest: dict[str, Any] | None = None
        for record in read_ledger(path):
            if record.get("event_type") != "dumbmoney_fence_activated":
                continue
            payload = record.get("payload")
            if isinstance(payload, dict):
                latest = payload
    expected = (
        envelope_id,
        event_id,
        body_digest,
        fencing_generation,
        policy_epoch,
    )
    observed = (
        str(latest.get("envelope_id", "")) if latest else "",
        str(latest.get("event_id", "")) if latest else "",
        str(latest.get("body_digest", "")) if latest else "",
        int(latest.get("fencing_generation", 0)) if latest else 0,
        int(latest.get("policy_epoch", 0)) if latest else 0,
    )
    if observed != expected:
        raise LiveBranchLedgerError(
            "DumbMoney authority is no longer the active execution fence: "
            f"expected={expected}, observed={observed}"
        )


def _unresolved_submission_payload(
    records: tuple[dict[str, Any], ...],
    intent_id: str,
) -> dict[str, Any] | None:
    unresolved_payload: dict[str, Any] | None = None
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("intent_id") != intent_id:
            continue
        event_type = str(record.get("event_type", ""))
        if event_type in {
            "live_order_submission_reserved",
            "live_order_submission_started",
            "live_order_submission_ambiguous",
        }:
            unresolved_payload = dict(payload)
        elif event_type == "live_order_result":
            unresolved_payload = None
    return unresolved_payload


def reconcile_submission_after_operator_verification(
    repository_root: Path,
    intent_id: str,
    placed: bool,
    order_id: str,
    status: str,
    filled_quantity: float,
    average_fill_price: float,
    broker_evidence_reference: str,
    operator_confirmation: str,
) -> dict[str, Any]:
    if operator_confirmation != OPERATOR_RECONCILIATION_CONFIRMATION:
        raise LiveBranchLedgerError(
            "Live Branch reconciliation requires exact operator confirmation"
        )
    if not intent_id.strip():
        raise LiveBranchLedgerError("Live Branch reconciliation intent_id is required")
    if not broker_evidence_reference.strip():
        raise LiveBranchLedgerError(
            "Live Branch reconciliation requires a broker evidence reference"
        )
    if placed and not order_id.strip():
        raise LiveBranchLedgerError(
            "Placed Live Branch reconciliation requires the broker order_id"
        )
    if not placed and order_id.strip():
        raise LiveBranchLedgerError(
            "Verified non-placement must not claim a broker order_id"
        )
    if not status.strip():
        raise LiveBranchLedgerError(
            "Live Branch reconciliation requires an observed broker status"
        )
    if (
        not math.isfinite(filled_quantity)
        or not math.isfinite(average_fill_price)
        or filled_quantity < 0.0
        or average_fill_price < 0.0
    ):
        raise LiveBranchLedgerError(
            "Live Branch reconciliation fill quantity and price must be nonnegative"
        )
    path = ledger_path(repository_root)
    with _exclusive_ledger_lock(path):
        records = read_ledger(path)
        unresolved = _unresolved_submission_payload(records, intent_id)
        if unresolved is None:
            raise LiveBranchLedgerError(
                "Live Branch reconciliation target is not an unresolved submission: "
                f"intent_id={intent_id}"
            )
        raw_intent = unresolved.get("intent")
        intent = dict(raw_intent) if isinstance(raw_intent, dict) else {}
        payload = {
            "intent_id": intent_id,
            "instrument": unresolved.get("instrument", intent.get("instrument", "")),
            "symbol": unresolved.get("symbol", intent.get("symbol", "")),
            "side": unresolved.get("side", intent.get("side", "")),
            "market_date": unresolved.get("market_date", ""),
            "intent": intent,
            "placed": placed,
            "order_id": order_id,
            "status": status,
            "filled_quantity": filled_quantity,
            "average_fill_price": average_fill_price,
            "operator_reconciled": True,
            "broker_evidence_reference": broker_evidence_reference,
            "automatic_broker_inference_used": False,
        }
        return _append_record_unlocked(path, "live_order_result", payload)


def latest_open_date(repository_root: Path, symbol: str, instrument: str) -> str:
    open_date = ""
    for record in read_ledger(ledger_path(repository_root)):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("symbol") != symbol or payload.get("instrument") != instrument:
            continue
        if (
            record.get("event_type") == "live_order_result"
            and payload.get("placed") is True
        ):
            if payload.get("side") == "buy":
                open_date = str(payload.get("market_date", ""))
            elif payload.get("side") == "sell":
                open_date = ""
    return open_date


def write_latest_cycle(repository_root: Path, payload: dict[str, Any]) -> Path:
    path = latest_cycle_path(repository_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(encoded)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)
    return path
