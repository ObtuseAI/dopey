"""Fast, hash-pinned validation for one requested history symbol."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash
from dopey_data.history_store import (
    HISTORY_MANIFEST_PATH,
    file_sha256,
    load_history_bars_from_file,
    load_history_manifest,
    resolve_history_data_file_path,
)
from dopey_equity_swing.market_structure import Bar, normalize_history_bars


def _validate_bar(symbol: str, row: dict[str, Any], row_number: int, source_path: Path) -> None:
    row_symbol = str(row.get("symbol", "")).upper()
    if row_symbol != symbol:
        raise ValueError(
            "history row symbol does not match requested symbol: "
            f"path={source_path}, row_number={row_number}, expected={symbol}, actual={row_symbol}"
        )
    open_value = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    adjusted_close = float(row.get("adjusted_close", close))
    volume = int(row["volume"])
    if min(open_value, high, low, close, adjusted_close) <= 0.0:
        raise ValueError(
            "history row contains nonpositive price: "
            f"path={source_path}, row_number={row_number}, symbol={symbol}"
        )
    if high < max(open_value, close, low) or low > min(open_value, close, high):
        raise ValueError(
            "history row violates OHLC bounds: "
            f"path={source_path}, row_number={row_number}, symbol={symbol}"
        )
    if volume < 0:
        raise ValueError(
            "history row contains negative volume: "
            f"path={source_path}, row_number={row_number}, symbol={symbol}"
        )
    source = str(row.get("source", "")).lower()
    if any(term in source for term in ("fixture", "synthetic", "placeholder", "sample")):
        raise ValueError(
            "history row declares a non-real source: "
            f"path={source_path}, row_number={row_number}, symbol={symbol}, source={source}"
        )


def load_validated_symbol_history(
    symbol: str,
    manifest_path: Path,
) -> tuple[list[Bar], dict[str, Any]]:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol history adapter requires a non-empty symbol")
    manifest = load_history_manifest(manifest_path)
    allowed_manifest_statuses = {"valid_real_dataset", "operator_staged_real_dataset"}
    if manifest.dataset_status not in allowed_manifest_statuses:
        raise ValueError(
            "symbol history adapter requires a governed real dataset manifest: "
            f"dataset_status={manifest.dataset_status}, manifest_path={manifest_path}"
        )
    if manifest.paper_only is not True or manifest.live_blocked is not True:
        raise ValueError(
            "history manifest violates research-only boundary: "
            f"manifest_path={manifest_path}"
        )
    if manifest.generated_real_data or manifest.network_fetch_performed or manifest.credential_required:
        raise ValueError(
            "history manifest violates local real-data provenance rules: "
            f"generated_real_data={manifest.generated_real_data}, "
            f"network_fetch_performed={manifest.network_fetch_performed}, "
            f"credential_required={manifest.credential_required}, manifest_path={manifest_path}"
        )
    matches = [
        file_ref
        for file_ref in manifest.data_files
        if normalized_symbol in {candidate.upper() for candidate in file_ref.symbols}
    ]
    if len(matches) != 1:
        raise ValueError(
            "history manifest must identify exactly one file for the requested symbol: "
            f"symbol={normalized_symbol}, match_count={len(matches)}, manifest_path={manifest_path}"
        )
    file_ref = matches[0]
    source_path = resolve_history_data_file_path(manifest_path, manifest, file_ref)
    if not source_path.exists():
        raise FileNotFoundError(
            "hash-pinned symbol history file is missing: "
            f"symbol={normalized_symbol}, path={source_path}"
        )
    actual_hash = file_sha256(source_path)
    if not file_ref.sha256 or actual_hash.lower() != file_ref.sha256.lower():
        raise ValueError(
            "hash-pinned symbol history file does not match the manifest: "
            f"symbol={normalized_symbol}, path={source_path}, expected_hash={file_ref.sha256}, actual_hash={actual_hash}"
        )
    bars = load_history_bars_from_file(source_path, file_ref.format)
    if len(bars) != file_ref.row_count:
        raise ValueError(
            "symbol history row count does not match the manifest: "
            f"symbol={normalized_symbol}, path={source_path}, expected_rows={file_ref.row_count}, actual_rows={len(bars)}"
        )
    raw_rows = [bar.to_dict() for bar in bars]
    for row_number, row in enumerate(raw_rows, start=2):
        _validate_bar(normalized_symbol, row, row_number, source_path)
    dates = [str(row["date"]) for row in raw_rows]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError(
            "symbol history dates must be unique and sorted: "
            f"symbol={normalized_symbol}, path={source_path}"
        )
    normalized_bars = normalize_history_bars(raw_rows)
    proof_body: dict[str, Any] = {
        "artifact_type": "validated_symbol_history_proof",
        "symbol": normalized_symbol,
        "manifest_dataset_status": manifest.dataset_status,
        "symbol_validation_status": "valid_real_symbol_dataset",
        "manifest_path": str(manifest_path),
        "source_path": str(source_path),
        "source": file_ref.source,
        "format": file_ref.format,
        "expected_sha256": file_ref.sha256,
        "actual_sha256": actual_hash,
        "row_count": len(normalized_bars),
        "first_date": normalized_bars[0]["date"] if normalized_bars else "",
        "last_date": normalized_bars[-1]["date"] if normalized_bars else "",
        "validation_scope": "requested_symbol_file_plus_manifest_contract",
        "network_fetch_performed": False,
        "credential_required": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return normalized_bars, {**proof_body, "reproducibility_hash": canonical_hash(proof_body)}


def load_default_validated_symbol_history(symbol: str) -> tuple[list[Bar], dict[str, Any]]:
    return load_validated_symbol_history(symbol, HISTORY_MANIFEST_PATH)
