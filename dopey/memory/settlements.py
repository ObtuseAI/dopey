"""Forward-settlement memory writer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .ledger import MemoryKind, append_memory_record, build_memory_record


def append_settlement(
    path: Path,
    payload: Mapping[str, Any],
    observed_at: str,
    prediction_id: str,
    evidence_ids: Sequence[str],
) -> dict[str, str]:
    record = build_memory_record(
        MemoryKind.SETTLEMENT,
        payload,
        observed_at,
        prediction_id,
        evidence_ids,
        "dopey-settlement-memory-v1",
    )
    return append_memory_record(path, record)
