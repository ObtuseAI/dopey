"""Strict hash-pinned intraday adapter; never synthesizes missing bars."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.chronos.clocks import ClockStamp
from dopey.protocols.identity import canonical_hash
from dopey_equity_swing.market_structure import Bar

from .evidence import build_timeframe_measurements
from .foundry import ALL_TECHNICAL_SPECS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_validated_intraday_history(
    symbol: str,
    manifest_path: Path,
) -> tuple[list[Bar], dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"intraday manifest is missing: path={manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError(f"intraday manifest must be an object: path={manifest_path}")
    normalized_symbol = symbol.strip().upper()
    if manifest.get("dataset_status") != "valid_real_intraday_dataset":
        raise ValueError(
            "intraday manifest is not validated real data: "
            f"path={manifest_path}, dataset_status={manifest.get('dataset_status')}"
        )
    if manifest.get("paper_only") is not True or manifest.get("live_blocked") is not True:
        raise ValueError(f"intraday manifest violates research-only boundary: path={manifest_path}")
    if str(manifest.get("symbol", "")).upper() != normalized_symbol:
        raise ValueError(
            "intraday manifest symbol mismatch: "
            f"path={manifest_path}, expected={normalized_symbol}, actual={manifest.get('symbol')}"
        )
    source = str(manifest.get("source", "")).lower()
    if any(term in source for term in ("fixture", "synthetic", "placeholder", "sample")):
        raise ValueError(f"intraday manifest source is not real evidence: path={manifest_path}, source={source}")
    data_path = Path(str(manifest["path"]))
    if not data_path.is_absolute():
        data_path = manifest_path.parent / data_path
    if not data_path.exists():
        raise FileNotFoundError(f"intraday data file is missing: path={data_path}")
    actual_hash = _sha256(data_path)
    expected_hash = str(manifest.get("sha256", ""))
    if not expected_hash or actual_hash.lower() != expected_hash.lower():
        raise ValueError(
            "intraday data hash does not match manifest: "
            f"path={data_path}, expected_hash={expected_hash}, actual_hash={actual_hash}"
        )
    rows: list[Bar] = []
    with data_path.open("r", encoding="utf-8", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            timestamp = str(row.get("timestamp", row.get("date", "")))
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError(
                    "intraday timestamp requires timezone: "
                    f"path={data_path}, row_number={row_number}, timestamp={timestamp}"
                )
            row_symbol = str(row.get("symbol", normalized_symbol)).upper()
            if row_symbol != normalized_symbol:
                raise ValueError(
                    "intraday row symbol mismatch: "
                    f"path={data_path}, row_number={row_number}, expected={normalized_symbol}, actual={row_symbol}"
                )
            open_value = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = int(float(row["volume"]))
            if min(open_value, high, low, close) <= 0.0 or volume < 0 or high < max(open_value, close) or low > min(open_value, close):
                raise ValueError(f"intraday row violates OHLCV constraints: path={data_path}, row_number={row_number}")
            rows.append(
                {
                    "date": timestamp,
                    "symbol": normalized_symbol,
                    "open": open_value,
                    "high": high,
                    "low": low,
                    "close": close,
                    "adjusted_close": close,
                    "volume": volume,
                    "source": source,
                }
            )
    timestamps = [str(row["date"]) for row in rows]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError(f"intraday timestamps must be unique and sorted: path={data_path}")
    expected_rows = int(manifest.get("row_count", 0) or 0)
    if expected_rows != len(rows):
        raise ValueError(
            "intraday row count does not match manifest: "
            f"path={data_path}, expected_rows={expected_rows}, actual_rows={len(rows)}"
        )
    proof_body: dict[str, Any] = {
        "artifact_type": "validated_intraday_history_proof",
        "symbol": normalized_symbol,
        "bar_interval": str(manifest.get("bar_interval", "")),
        "source_path": str(data_path),
        "source": source,
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "row_count": len(rows),
        "first_timestamp": timestamps[0] if timestamps else "",
        "last_timestamp": timestamps[-1] if timestamps else "",
        "network_fetch_performed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return rows, {**proof_body, "reproducibility_hash": canonical_hash(proof_body)}


def build_intraday_technical_evidence(
    symbol: str,
    rows: list[Bar],
    bar_interval: str,
    clock: ClockStamp,
) -> dict[str, Any]:
    if not rows:
        raise ValueError(f"intraday technical evidence requires rows: symbol={symbol}")
    measurements = build_timeframe_measurements(symbol, "intraday", rows, clock, ALL_TECHNICAL_SPECS)
    body: dict[str, Any] = {
        "artifact_type": "intraday_technical_evidence",
        "intraday_evidence_version": "dopey-intraday-technical-v1",
        "symbol": symbol,
        "bar_interval": bar_interval,
        "as_of": str(rows[-1]["date"]),
        "indicator_count": len(ALL_TECHNICAL_SPECS),
        "measurement_count": len(measurements),
        "measurements": measurements,
        "intraday_status": "complete_validated_real_intraday_history",
        "paper_only": True,
        "live_blocked": True,
        "not_trade_decision": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
