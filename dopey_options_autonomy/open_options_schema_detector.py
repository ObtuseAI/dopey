"""Detect open options chain/quote schemas."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import stable_hash


REQUIRED_OPTIONS_FIELDS = ("underlying_symbol", "contract_symbol", "expiration_date", "strike", "option_type", "bid", "ask")
ALIASES = {
    "snapshot_date": {"snapshot_date", "timestamp", "date"},
    "underlying_symbol": {"underlying_symbol", "underlying", "symbol"},
    "contract_symbol": {"contract_symbol", "option_symbol", "contract"},
    "expiration_date": {"expiration_date", "expiry", "expiration"},
    "strike": {"strike", "strike_price"},
    "option_type": {"option_type", "type", "right", "put_call"},
    "bid": {"bid"},
    "ask": {"ask"},
    "last": {"last", "last_price", "close"},
    "volume": {"volume", "vol"},
    "open_interest": {"open_interest", "oi"},
    "implied_volatility": {"implied_volatility", "iv"},
}


def detect_open_options_schema(path: Path) -> dict[str, Any]:
    header = _header(path)
    lower_to_original = {column.lower().strip(): column for column in header}
    mapping: dict[str, str] = {}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            if alias in lower_to_original:
                mapping[target] = lower_to_original[alias]
                break
    missing = [field for field in REQUIRED_OPTIONS_FIELDS if field not in mapping]
    if "snapshot_date" not in mapping:
        missing.append("snapshot_date")
    record = {
        "artifact_type": "open_options_schema_detection_results",
        "path": str(path),
        "detected_columns": header,
        "column_mapping": mapping,
        "schema_status": "schema_detected" if not missing else "schema_rejected",
        "missing_required_columns": sorted(set(missing)),
        "paper_only": True,
        "live_blocked": True,
    }
    record["schema_hash"] = stable_hash(record)
    return record


def _header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        try:
            return next(csv.reader(handle))
        except StopIteration:
            return []

