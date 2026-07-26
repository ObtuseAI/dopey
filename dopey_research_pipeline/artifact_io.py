"""Crash-safe artifact IO: atomic writes and guarded reads for stateful files.

Every stateful artifact (the forward-walk ledger above all) must survive a
process death mid-write. Pattern: write to a sibling temp file, fsync, then
os.replace() onto the final path (atomic on Windows and POSIX). For files
whose loss would destroy accumulated evidence, keep a .bak of the previous
good version and fall back to it on a corrupt read - never silently start
from empty.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, record: dict[str, Any], keep_backup: bool = False) -> None:
    _atomic_write_text(path, json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", keep_backup)


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]], keep_backup: bool = False) -> None:
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    _atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""), keep_backup)


def write_jsonl_atomic_streaming(
    path: Path, records: Iterable[dict[str, Any]], keep_backup: bool = False
) -> int:
    """Atomically replace a JSONL artifact, streaming one record at a time.

    For large artifacts (the honest backtester's trade ledger is >500MB at the
    full universe) the list-join variant above materializes the entire payload
    as strings first - a >1GB transient spike - and a plain truncate-write can
    be torn by a mid-write kill (the 2026-07-21 ledger-corruption incident
    class). This variant keeps memory bounded to one record and keeps the
    temp+fsync+os.replace atomicity. Returns the record count written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if keep_backup and path.exists():
        os.replace(path, _backup_path(path))
    temp = path.with_name(path.name + ".tmp")
    written = 0
    with temp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            written += 1
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    return written


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one journal line; append is effectively atomic for line-sized writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def read_json_guarded(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Read a JSON dict; on corruption fall back to .bak. Returns (record, source).

    source is one of: 'primary', 'backup', 'missing'. Raises ValueError when both
    the primary and its backup exist but neither parses - losing state silently
    is worse than failing loudly.
    """
    backup = _backup_path(path)
    if not path.exists() and not backup.exists():
        return None, "missing"
    for candidate, label in ((path, "primary"), (backup, "backup")):
        if not candidate.exists():
            continue
        try:
            parsed = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed, label
    raise ValueError(f"corrupt_stateful_artifact_and_backup:{path.name}")


def _atomic_write_text(path: Path, text: str, keep_backup: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if keep_backup and path.exists():
        os.replace(path, _backup_path(path))
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")
