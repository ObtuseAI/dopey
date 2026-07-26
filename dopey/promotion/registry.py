"""Append-only autonomous research-activation decision registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def append_activation_decision(path: Path, decision: Mapping[str, Any]) -> bool:
    decision_hash = str(decision.get("decision_hash", "")).strip()
    if not decision_hash:
        raise ValueError("activation decision requires decision_hash")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_hashes: set[str] = set()
    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"activation registry contains invalid JSON: path={path}, line={line_number}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(
                    f"activation registry record must be an object: path={path}, line={line_number}"
                )
            existing_hashes.add(str(record.get("decision_hash", "")))
    if decision_hash in existing_hashes:
        return False
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(decision), sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
    return True
