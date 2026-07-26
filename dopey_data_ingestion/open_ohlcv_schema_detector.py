"""Detect OHLCV schemas for quarantined open files."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import REQUIRED_OHLCV_COLUMNS, stable_hash


ALIASES = {
    "date": {"date", "timestamp", "snapshot_date"},
    "symbol": {"symbol", "ticker", "underlying_symbol"},
    "open": {"open", "o"},
    "high": {"high", "h"},
    "low": {"low", "l"},
    "close": {"close", "c", "last"},
    "adjusted_close": {"adjusted_close", "adj_close", "adjclose", "close"},
    "volume": {"volume", "vol"},
}


def detect_open_ohlcv_schema(path: Path) -> dict[str, Any]:
    header = _header(path)
    mapping = {}
    lower_to_original = {column.lower().strip(): column for column in header}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            if alias in lower_to_original:
                mapping[target] = lower_to_original[alias]
                break
    missing = [column for column in REQUIRED_OHLCV_COLUMNS[:8] if column not in mapping]
    record = {
        "artifact_type": "open_ohlcv_schema_detection_results",
        "path": str(path),
        "detected_columns": header,
        "column_mapping": mapping,
        "schema_status": "schema_detected" if not missing else "schema_rejected",
        "missing_required_columns": missing,
        "paper_only": True,
        "live_blocked": True,
    }
    record["schema_hash"] = stable_hash(record)
    return record


def _header(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            return []

