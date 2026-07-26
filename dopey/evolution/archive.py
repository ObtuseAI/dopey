"""Append-only archive for candidates and evaluation decisions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def append_archive_record(path: Path, record: Mapping[str, Any]) -> dict[str, str]:
    record_id = str(record.get("evaluation_id", record.get("candidate_id", "")))
    content_hash = str(
        record.get("content_hash", record.get("reproducibility_hash", ""))
    )
    if not record_id or not content_hash:
        raise ValueError("evolution archive record requires identity and content hash")
    existing: dict[str, str] = {}
    if path.exists():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"evolution archive contains invalid JSON: path={path}, line={line_number}"
                ) from exc
            identity = str(value.get("evaluation_id", value.get("candidate_id", "")))
            existing[identity] = str(
                value.get("content_hash", value.get("reproducibility_hash", ""))
            )
    if record_id in existing:
        if existing[record_id] != content_hash:
            raise ValueError(
                f"evolution archive identity conflict: record_id={record_id}, path={path}"
            )
        return {
            "append_status": "already_present_identical",
            "record_id": record_id,
            "path": str(path),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=True) + "\n")
    return {"append_status": "appended", "record_id": record_id, "path": str(path)}
