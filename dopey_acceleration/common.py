"""Shared typed IO for the research acceleration control plane."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey" / "acceleration"


def read_optional_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON artifact: path={path}, error={error}") from error
    if not isinstance(parsed, dict):
        raise TypeError(f"JSON artifact must be an object: path={path}, actual={type(parsed).__name__}")
    return parsed, "available"


def write_json_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    payload = (
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )
    try:
        with temp.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def stable_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stamped(record: dict[str, Any]) -> dict[str, Any]:
    output = dict(record)
    output["reproducibility_hash"] = stable_hash(output)
    return output
