"""Strict append-only storage shared by all vNext memory families."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from dopey.protocols.identity import canonical_hash


MEMORY_ARTIFACT_TYPE: Final[str] = "dopey_research_memory_record"
MEMORY_VERSION: Final[str] = "dopey-memory-v1"
MEMORY_RECORD_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "append_only",
        "artifact_type",
        "causal_parent_id",
        "content_hash",
        "live_blocked",
        "memory_id",
        "memory_kind",
        "memory_version",
        "not_trade_authority",
        "observed_at",
        "paper_only",
        "payload",
        "schema_version",
        "source_ids",
    }
)
MEMORY_BOUNDARY_FIELDS: Final[tuple[str, ...]] = (
    "append_only",
    "not_trade_authority",
    "paper_only",
    "live_blocked",
)


class MemoryKind(StrEnum):
    OBSERVATION = "observation"
    EPISODE = "episode"
    SETTLEMENT = "settlement"
    FAILURE = "failure"
    CALIBRATION = "calibration"
    STRATEGY = "strategy"
    THEORY = "theory"


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"memory timestamp is not valid ISO-8601: observed_at={value}"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(f"memory timestamp requires a timezone: observed_at={value}")


def build_memory_record(
    kind: MemoryKind,
    payload: Mapping[str, Any],
    observed_at: str,
    causal_parent_id: str,
    source_ids: Sequence[str],
    schema_version: str,
) -> dict[str, Any]:
    if not isinstance(kind, MemoryKind):
        raise TypeError(
            f"memory kind must be a MemoryKind value: actual={type(kind).__name__}"
        )
    if not isinstance(payload, Mapping):
        raise TypeError(
            f"memory payload must be a mapping: actual={type(payload).__name__}"
        )
    if not isinstance(observed_at, str):
        raise TypeError(
            f"memory timestamp must be a string: actual={type(observed_at).__name__}"
        )
    if not isinstance(causal_parent_id, str):
        raise TypeError(
            "memory causal parent identity must be a string: "
            f"actual={type(causal_parent_id).__name__}"
        )
    if isinstance(source_ids, (str, bytes)) or not isinstance(source_ids, Sequence):
        raise TypeError(
            "memory source identities must be a sequence of strings: "
            f"actual={type(source_ids).__name__}"
        )
    if any(not isinstance(source_id, str) for source_id in source_ids):
        raise TypeError("memory source identities must contain only strings")
    if any(not source_id for source_id in source_ids):
        raise ValueError("memory source identities cannot contain empty values")
    if not isinstance(schema_version, str):
        raise TypeError(
            "memory schema version must be a string: "
            f"memory_kind={kind.value}, actual={type(schema_version).__name__}"
        )
    _validate_timestamp(observed_at)
    if not payload:
        raise ValueError(f"memory payload cannot be empty: memory_kind={kind.value}")
    if not schema_version.strip():
        raise ValueError(
            f"memory schema version cannot be empty: memory_kind={kind.value}"
        )
    normalized_sources = sorted(set(source_ids))
    body: dict[str, Any] = {
        "artifact_type": MEMORY_ARTIFACT_TYPE,
        "memory_version": MEMORY_VERSION,
        "memory_kind": kind.value,
        "schema_version": schema_version,
        "observed_at": observed_at,
        "causal_parent_id": causal_parent_id,
        "source_ids": normalized_sources,
        "payload": dict(payload),
        "append_only": True,
        "paper_only": True,
        "live_blocked": True,
        "not_trade_authority": True,
    }
    content_hash = canonical_hash(body)
    return {
        **body,
        "memory_id": f"memory:{kind.value}:{content_hash[:24]}",
        "content_hash": content_hash,
    }


def _validate_record(record: Mapping[str, Any], path: Path, line_number: int) -> None:
    observed_fields = set(record)
    missing = sorted(MEMORY_RECORD_FIELDS - observed_fields)
    unexpected = sorted(str(field) for field in observed_fields - MEMORY_RECORD_FIELDS)
    if missing or unexpected:
        raise ValueError(
            "memory record envelope differs from the exact schema: "
            f"path={path}, line_number={line_number}, "
            f"missing={missing}, unexpected={unexpected}"
        )
    if record["artifact_type"] != MEMORY_ARTIFACT_TYPE:
        raise ValueError(
            "memory record artifact type is unsupported: "
            f"path={path}, line_number={line_number}, "
            f"expected={MEMORY_ARTIFACT_TYPE}, observed={record['artifact_type']}"
        )
    if record["memory_version"] != MEMORY_VERSION:
        raise ValueError(
            "memory record version is unsupported: "
            f"path={path}, line_number={line_number}, "
            f"expected={MEMORY_VERSION}, observed={record['memory_version']}"
        )
    invalid_boundary_fields = [
        field_name
        for field_name in MEMORY_BOUNDARY_FIELDS
        if record[field_name] is not True
    ]
    if invalid_boundary_fields:
        raise ValueError(
            "memory record violates the canonical research-only boundary: "
            f"path={path}, line_number={line_number}, "
            f"invalid_fields={invalid_boundary_fields}"
        )
    memory_kind = record["memory_kind"]
    if not isinstance(memory_kind, str):
        raise TypeError(
            "memory record kind must be a string: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(memory_kind).__name__}"
        )
    try:
        kind = MemoryKind(memory_kind)
    except ValueError as exc:
        raise ValueError(
            "memory record contains an unsupported kind: "
            f"path={path}, line_number={line_number}, memory_kind={memory_kind}"
        ) from exc
    schema_version = record["schema_version"]
    if not isinstance(schema_version, str):
        raise TypeError(
            "memory schema version must be a string: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(schema_version).__name__}"
        )
    if not schema_version.strip():
        raise ValueError(
            "memory schema version cannot be empty: "
            f"path={path}, line_number={line_number}, memory_kind={kind.value}"
        )
    observed_at = record["observed_at"]
    if not isinstance(observed_at, str):
        raise TypeError(
            "memory timestamp must be a string: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(observed_at).__name__}"
        )
    _validate_timestamp(observed_at)
    causal_parent_id = record["causal_parent_id"]
    if not isinstance(causal_parent_id, str):
        raise TypeError(
            "memory causal parent identity must be a string: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(causal_parent_id).__name__}"
        )
    source_ids = record["source_ids"]
    if not isinstance(source_ids, list):
        raise TypeError(
            "memory source identities must be a list: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(source_ids).__name__}"
        )
    if any(not isinstance(source_id, str) for source_id in source_ids):
        raise TypeError(
            "memory source identities must contain only strings: "
            f"path={path}, line_number={line_number}"
        )
    if any(not source_id for source_id in source_ids):
        raise ValueError(
            "memory source identities cannot contain empty values: "
            f"path={path}, line_number={line_number}"
        )
    if source_ids != sorted(set(source_ids)):
        raise ValueError(
            "memory source identities must be sorted and unique: "
            f"path={path}, line_number={line_number}, source_ids={source_ids}"
        )
    payload = record["payload"]
    if not isinstance(payload, dict):
        raise TypeError(
            "memory payload must be an object: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(payload).__name__}"
        )
    if not payload:
        raise ValueError(
            "memory payload cannot be empty: "
            f"path={path}, line_number={line_number}, memory_kind={kind.value}"
        )
    memory_id = record["memory_id"]
    if not isinstance(memory_id, str):
        raise TypeError(
            "memory identity must be a string: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(memory_id).__name__}"
        )
    content_hash = record["content_hash"]
    if not isinstance(content_hash, str):
        raise TypeError(
            "memory content hash must be a string: "
            f"path={path}, line_number={line_number}, "
            f"actual={type(content_hash).__name__}"
        )
    body = {
        str(key): value
        for key, value in record.items()
        if key not in {"memory_id", "content_hash"}
    }
    expected_hash = canonical_hash(body)
    if content_hash != expected_hash:
        raise ValueError(
            "memory record content hash mismatch: "
            f"path={path}, line_number={line_number}, "
            f"expected={expected_hash}, observed={content_hash}"
        )
    expected_memory_id = f"memory:{kind.value}:{expected_hash[:24]}"
    if memory_id != expected_memory_id:
        raise ValueError(
            "memory record identity is not bound to its content: "
            f"path={path}, line_number={line_number}, "
            f"expected={expected_memory_id}, observed={memory_id}"
        )


def load_memory_records(path: Path, kind: MemoryKind | None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw_content = path.read_bytes()
    try:
        text = raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"memory ledger is not valid UTF-8: path={path}") from exc
    records: list[dict[str, Any]] = []
    lines = text.splitlines()
    last_content_line = max(
        (line_number for line_number, line in enumerate(lines, start=1) if line.strip()),
        default=0,
    )
    unterminated_tail = bool(raw_content) and not raw_content.endswith(b"\n")
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            if line_number == last_content_line and unterminated_tail:
                # A crash mid-append leaves a torn final line; truncate the tail
                # instead of permanently bricking the ledger. Interior corruption
                # and newline-terminated corruption still raise below.
                break
            raise ValueError(
                "memory ledger contains invalid JSON: "
                f"path={path}, line_number={line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise TypeError(
                "memory ledger entry must be an object: "
                f"path={path}, line_number={line_number}"
            )
        _validate_record(value, path, line_number)
        if kind is None or value["memory_kind"] == kind.value:
            records.append(value)
    return records


def _repair_unterminated_tail(path: Path) -> None:
    """Repair an unterminated final record before appending another record."""
    if not path.exists():
        return
    content = path.read_bytes()
    if not content or content.endswith(b"\n"):
        return
    last_newline = content.rfind(b"\n")
    tail = content[last_newline + 1 :] if last_newline >= 0 else content
    try:
        json.loads(tail.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        with path.open("r+b") as handle:
            handle.truncate(last_newline + 1 if last_newline >= 0 else 0)
            handle.flush()
            os.fsync(handle.fileno())
        return
    with path.open("ab") as handle:
        handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_memory_record(path: Path, record: Mapping[str, Any]) -> dict[str, str]:
    _validate_record(record, path, 0)
    records = load_memory_records(path, None)
    memory_id = str(record["memory_id"])
    content_hash = str(record["content_hash"])
    matches = [existing for existing in records if existing["memory_id"] == memory_id]
    if matches:
        existing_hash = str(matches[0]["content_hash"])
        if existing_hash != content_hash:
            raise ValueError(
                "memory identity conflict: "
                f"path={path}, memory_id={memory_id}, existing_hash={existing_hash}, new_hash={content_hash}"
            )
        return {
            "append_status": "already_present_identical",
            "memory_id": memory_id,
            "path": str(path),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    _repair_unterminated_tail(path)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {"append_status": "appended", "memory_id": memory_id, "path": str(path)}
