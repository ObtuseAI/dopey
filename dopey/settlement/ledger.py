"""Strict loader for the append-only vNext prediction ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_prediction_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"settlement prediction ledger is missing: path={path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                "settlement prediction ledger contains invalid JSON: "
                f"path={path}, line_number={line_number}"
            ) from error
        if not isinstance(value, dict):
            raise TypeError(
                "settlement prediction ledger entry must be an object: "
                f"path={path}, line_number={line_number}"
            )
        records.append(value)
    return records
