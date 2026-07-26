"""Research-strategy memory writer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .ledger import MemoryKind, append_memory_record, build_memory_record


def append_strategy(
    path: Path,
    payload: Mapping[str, Any],
    observed_at: str,
    causal_parent_id: str,
    settlement_ids: Sequence[str],
) -> dict[str, str]:
    record = build_memory_record(
        MemoryKind.STRATEGY,
        payload,
        observed_at,
        causal_parent_id,
        settlement_ids,
        "dopey-strategy-memory-v1",
    )
    return append_memory_record(path, record)
