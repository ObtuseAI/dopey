"""Canonical tamper-evident ledgers for experiment, proof, and forward evidence."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

from .identity import JsonValue, canonical_hash, require_utc_iso


GENESIS_HASH = "0" * 64
REQUIRED_PAYLOAD_FIELDS = frozenset({"event_time", "code_version", "data_hash", "experiment_id"})
LedgerKind = Literal["experiment", "proof", "forward"]
CANONICAL_LEDGER_PATHS: Mapping[LedgerKind, Path] = MappingProxyType(
    {
        "experiment": Path("EXPERIMENT_REGISTRY.jsonl"),
        "proof": Path("PROOF_LEDGER.jsonl"),
        "forward": Path("shadow_trading/FORWARD_EVIDENCE.jsonl"),
    }
)


def _pid_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise RuntimeError(
                "SystemRoot is required to verify a Windows ledger lock owner"
            )
        tasklist = Path(system_root) / "System32" / "tasklist.exe"
        completed = subprocess.run(
            [str(tasklist), "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Windows process-liveness check failed: "
                f"pid={process_id}, return_code={completed.returncode}, stderr={completed.stderr[-2_000:]}"
            )
        rows = list(csv.reader(completed.stdout.splitlines()))
        return any(len(row) >= 2 and row[1].strip() == str(process_id) for row in rows)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def ledger_anchor_path(path: Path) -> Path:
    return path.with_suffix(f"{path.suffix}.head.json")


def _validate_required_identity(record: dict[str, JsonValue], path: Path) -> None:
    missing_payload = sorted(field for field in REQUIRED_PAYLOAD_FIELDS if not record.get(field))
    if missing_payload:
        raise ValueError(
            f"ledger record lacks evidence identity: path={path}, missing={missing_payload}"
        )
    for field_name in ("code_version", "experiment_id"):
        if not isinstance(record[field_name], str) or not record[field_name]:
            raise ValueError(
                f"ledger identity field must be a non-empty string: path={path}, field={field_name}"
            )
    require_utc_iso(str(record["event_time"]))
    data_hash = record["data_hash"]
    if not isinstance(data_hash, str) or len(data_hash) != 64 or any(
        character not in "0123456789abcdef" for character in data_hash
    ):
        raise ValueError(f"ledger data_hash is invalid: path={path}")


def _verify_ledger_anchor(path: Path, records: list[dict[str, JsonValue]]) -> None:
    anchor_path = ledger_anchor_path(path)
    if not records and not anchor_path.exists():
        return
    if not anchor_path.exists():
        raise ValueError(f"ledger head anchor is missing: path={path}")
    decoded = json.loads(anchor_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"ledger head anchor must be a mapping: path={anchor_path}")
    anchor = cast(dict[str, JsonValue], decoded)
    observed_anchor_hash = anchor.get("anchor_hash")
    anchor_body = {key: value for key, value in anchor.items() if key != "anchor_hash"}
    if observed_anchor_hash != canonical_hash(anchor_body):
        raise ValueError(f"ledger head anchor hash mismatch: path={anchor_path}")
    expected_count = len(records)
    expected_head = str(records[-1]["entry_hash"]) if records else GENESIS_HASH
    if anchor.get("record_count") != expected_count or anchor.get("head_hash") != expected_head:
        anchor_count = anchor.get("record_count")
        anchor_head = anchor.get("head_hash")
        prefix_head: str | None = None
        if isinstance(anchor_count, int) and not isinstance(anchor_count, bool):
            if 0 < anchor_count <= expected_count:
                prefix_head = str(records[anchor_count - 1]["entry_hash"])
            elif anchor_count == 0:
                prefix_head = GENESIS_HASH
        if prefix_head is not None and anchor_head == prefix_head:
            # A crash between the record append and the anchor write leaves the
            # anchor pinned to a valid earlier prefix. Re-pin it to the current
            # head instead of wedging every future append. Truncation (anchor
            # ahead of the ledger) and prefix forgery still raise below.
            _write_ledger_anchor(path, expected_count, expected_head)
            return
        raise ValueError(
            "ledger truncation or replacement detected: "
            f"path={path}, expected_count={anchor.get('record_count')}, observed_count={expected_count}"
        )


def _write_ledger_anchor(path: Path, record_count: int, head_hash: str) -> None:
    body: dict[str, JsonValue] = {
        "ledger_file": path.name,
        "record_count": record_count,
        "head_hash": head_hash,
    }
    anchor = {**body, "anchor_hash": canonical_hash(body)}
    anchor_path = ledger_anchor_path(path)
    temporary_path = anchor_path.with_suffix(f"{anchor_path.suffix}.{os.getpid()}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(anchor, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, anchor_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _load_records(path: Path) -> list[dict[str, JsonValue]]:
    if not path.exists():
        return []
    records: list[dict[str, JsonValue]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        decoded = json.loads(line)
        if not isinstance(decoded, dict):
            raise ValueError(f"ledger record must be a mapping: path={path}, line={line_number}")
        records.append(cast(dict[str, JsonValue], decoded))
    return records


def verify_hash_chained_ledger(path: Path) -> tuple[dict[str, JsonValue], ...]:
    records = _load_records(path)
    previous_hash = GENESIS_HASH
    seen_ids: set[str] = set()
    for expected_sequence, record in enumerate(records, start=1):
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"ledger record lacks record_id: path={path}, sequence={expected_sequence}")
        if record_id in seen_ids:
            raise ValueError(f"duplicate immutable record_id: path={path}, record_id={record_id}")
        seen_ids.add(record_id)
        _validate_required_identity(record, path)
        if record.get("sequence") != expected_sequence:
            raise ValueError(
                "ledger sequence mismatch: "
                f"path={path}, expected={expected_sequence}, observed={record.get('sequence')}"
            )
        if record.get("previous_hash") != previous_hash:
            raise ValueError(
                "ledger chain is broken: "
                f"path={path}, sequence={expected_sequence}, expected_previous_hash={previous_hash}"
            )
        observed_hash = record.get("entry_hash")
        body = {key: value for key, value in record.items() if key != "entry_hash"}
        expected_hash = canonical_hash(body)
        if observed_hash != expected_hash:
            raise ValueError(
                "ledger entry hash mismatch: "
                f"path={path}, sequence={expected_sequence}, expected={expected_hash}, observed={observed_hash}"
            )
        previous_hash = expected_hash
    _verify_ledger_anchor(path, records)
    return tuple(records)


def _append_hash_chained_record(
    path: Path,
    record_id: str,
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    if not record_id:
        raise ValueError("record_id cannot be empty")
    reserved_fields = {"record_id", "entry_hash", "previous_hash", "sequence"}
    supplied_reserved_fields = sorted(reserved_fields.intersection(payload))
    if supplied_reserved_fields:
        raise ValueError("ledger payload cannot supply protected chain fields")
    _validate_required_identity(payload, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    descriptor: int | None = None
    lock_acquired = False
    try:
        for attempt in range(2):
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as error:
                lock_content = lock_path.read_text(encoding="ascii").strip()
                if lock_content:
                    try:
                        lock_pid = int(lock_content)
                    except ValueError as parse_error:
                        raise RuntimeError(
                            f"ledger lock is unreadable and was preserved: lock={lock_path}"
                        ) from parse_error
                    if _pid_running(lock_pid):
                        raise RuntimeError(
                            f"ledger append already in progress: lock={lock_path}, pid={lock_pid}"
                        ) from error
                # A crashed appender leaves its lock behind (empty under the old
                # protocol, or a dead pid under the new one); reclaim it once.
                if attempt == 0:
                    lock_path.unlink(missing_ok=True)
                    continue
                raise RuntimeError(
                    f"failed to acquire ledger lock after stale-lock recovery: lock={lock_path}"
                ) from error
            lock_acquired = True
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            break
        records = verify_hash_chained_ledger(path)
        if any(record.get("record_id") == record_id for record in records):
            raise ValueError(f"immutable record_id already exists: path={path}, record_id={record_id}")
        previous_hash = str(records[-1]["entry_hash"]) if records else GENESIS_HASH
        body: dict[str, JsonValue] = {
            **payload,
            "record_id": record_id,
            "sequence": len(records) + 1,
            "previous_hash": previous_hash,
        }
        record = {**body, "entry_hash": canonical_hash(body)}
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _write_ledger_anchor(path, len(records) + 1, str(record["entry_hash"]))
        verify_hash_chained_ledger(path)
        return record
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if lock_acquired and lock_path.exists():
            lock_path.unlink()


def append_canonical_ascendancy_record(
    repository_root: Path,
    ledger_kind: LedgerKind,
    record_id: str,
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Ascendancy repository root is not a directory: path={root}")
    relative_path = CANONICAL_LEDGER_PATHS.get(ledger_kind)
    if relative_path is None:
        raise ValueError(f"unsupported canonical Ascendancy ledger kind: ledger_kind={ledger_kind}")
    ledger_path = (root / relative_path).resolve(strict=False)
    try:
        ledger_path.relative_to(root)
    except ValueError as error:
        raise PermissionError(
            "canonical Ascendancy ledger resolves outside the repository: "
            f"ledger_kind={ledger_kind}, path={ledger_path}"
        ) from error
    return _append_hash_chained_record(ledger_path, record_id, payload)
