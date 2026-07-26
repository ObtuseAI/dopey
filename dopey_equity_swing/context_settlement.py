"""Bounded, resumable settlement for immutable external-context decisions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast

from dopey_data.history_models import HistoryBar, normalize_history_symbol
from dopey_data.history_store import (
    file_sha256,
    load_history_bars_from_file,
    load_history_manifest,
    resolve_history_data_file_path,
)

from .context_outcomes import (
    append_outcome_records,
    build_matured_context_outcomes,
    load_jsonl_records,
)


CONTEXT_SETTLEMENT_VERSION = "dopey-context-settlement-v2"


def settle_context_decisions(
    decision_ledger_path: Path,
    outcome_ledger_path: Path,
    manifest_path: Path,
    validation_path: Path,
    cursor_path: Path,
    latest_operation_path: Path,
    batch_size: int,
) -> dict[str, object]:
    """Resolve one rotating batch while using the outcome ledger as immutable truth."""

    if batch_size < 1:
        raise ValueError(f"context settlement batch_size must be positive: batch_size={batch_size}")
    decisions = load_jsonl_records(decision_ledger_path, "decision_id")
    outcomes_before = load_jsonl_records(outcome_ledger_path, "decision_id")
    resolved_before = {str(record["decision_id"]) for record in outcomes_before}
    unresolved = sorted(
        (decision for decision in decisions if str(decision["decision_id"]) not in resolved_before),
        key=lambda decision: (str(decision.get("market_as_of", "")), str(decision["decision_id"])),
    )
    prior_cursor = _read_optional_json_object(cursor_path)
    selected = select_rotating_batch(
        unresolved,
        str(prior_cursor.get("last_examined_decision_id", "")),
        batch_size,
    )
    selected_symbols = sorted({normalize_history_symbol(str(decision["symbol"])) for decision in selected})
    histories, history_evidence = load_validated_symbol_histories(
        manifest_path,
        validation_path,
        selected_symbols,
    )
    resolution_as_of = str(history_evidence["validated_dataset_end_date"])
    matured = build_matured_context_outcomes(selected, histories, resolved_before, resolution_as_of)
    appended_count = append_outcome_records(outcome_ledger_path, matured)
    outcomes_after = load_jsonl_records(outcome_ledger_path, "decision_id")
    resolved_after = {str(record["decision_id"]) for record in outcomes_after}
    unresolved_after = sorted(
        str(decision["decision_id"])
        for decision in decisions
        if str(decision["decision_id"]) not in resolved_after
    )
    last_examined = str(selected[-1]["decision_id"]) if selected else str(prior_cursor.get("last_examined_decision_id", ""))
    cursor_record: dict[str, object] = {
        "artifact_type": "external_context_settlement_cursor",
        "settlement_version": CONTEXT_SETTLEMENT_VERSION,
        "decision_ledger_hash": _file_content_hash(decision_ledger_path),
        "outcome_ledger_hash": _file_content_hash(outcome_ledger_path),
        "last_examined_decision_id": last_examined,
        "next_pending_decision_id": _next_pending_id(unresolved_after, last_examined),
        "pending_decision_ids": unresolved_after,
        "pending_count": len(unresolved_after),
        "batch_size": batch_size,
        "paper_only": True,
        "live_blocked": True,
    }
    cursor_record["cursor_hash"] = _stable_hash(cursor_record)
    _write_json_atomic(cursor_path, cursor_record)

    operation: dict[str, object] = {
        "artifact_type": "external_context_outcome_update",
        "settlement_version": CONTEXT_SETTLEMENT_VERSION,
        "operation_status": "complete",
        "outcome_status": "updated" if appended_count else "no_matured_decisions",
        "decision_count": len(decisions),
        "previously_resolved_count": len(resolved_before),
        "selected_decision_count": len(selected),
        "selected_decision_ids": [str(decision["decision_id"]) for decision in selected],
        "newly_resolved_count": appended_count,
        "resolved_count_after": len(resolved_after),
        "unresolved_count_after": len(unresolved_after),
        "resolution_as_of": resolution_as_of,
        "history_evidence": history_evidence,
        "cursor_path": str(cursor_path),
        "cursor_hash": str(cursor_record["cursor_hash"]),
        "decision_ledger_immutable": True,
        "synthetic_outcomes_used": False,
        "paper_only": True,
        "live_blocked": True,
    }
    operation["operation_hash"] = _stable_hash(operation)
    _write_json_atomic(latest_operation_path, operation)
    return operation


def select_rotating_batch(
    unresolved_decisions: Sequence[dict[str, Any]],
    last_examined_decision_id: str,
    batch_size: int,
) -> list[dict[str, Any]]:
    """Select a bounded round-robin batch so pending rows cannot starve later rows."""

    if batch_size < 1:
        raise ValueError(f"context settlement batch_size must be positive: batch_size={batch_size}")
    records = list(unresolved_decisions)
    if not records:
        return []
    identifiers = [str(record["decision_id"]) for record in records]
    start_index = identifiers.index(last_examined_decision_id) + 1 if last_examined_decision_id in identifiers else 0
    rotated = records[start_index:] + records[:start_index]
    return rotated[:batch_size]


def load_validated_symbol_histories(
    manifest_path: Path,
    validation_path: Path,
    requested_symbols: Sequence[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, object]]:
    """Load only requested, hash-pinned files from a previously validated real dataset."""

    manifest = load_history_manifest(manifest_path)
    validation = _read_required_json_object(validation_path)
    validation_status = str(validation.get("dataset_status", ""))
    if validation_status != "valid_real_dataset":
        raise ValueError(
            "context settlement requires a valid real history validation artifact: "
            f"path={validation_path}, status={validation_status}"
        )
    manifest_hash = str(manifest.manifest_reproducibility_hash)
    validated_manifest_hash = str(validation.get("manifest_reproducibility_hash", ""))
    if not manifest_hash or manifest_hash != validated_manifest_hash:
        raise ValueError(
            "context settlement history manifest does not match its validation artifact: "
            f"manifest_hash={manifest_hash}, validated_manifest_hash={validated_manifest_hash}"
        )
    normalized_symbols = sorted({normalize_history_symbol(symbol) for symbol in requested_symbols if symbol})
    if not normalized_symbols:
        return {}, {
            "dataset_status": validation_status,
            "validated_manifest_hash": validated_manifest_hash,
            "validated_dataset_end_date": str(validation.get("end_date", "")),
            "requested_symbol_count": 0,
            "loaded_symbol_count": 0,
            "loaded_row_count": 0,
            "selected_file_hashes": {},
            "selective_hash_validation": True,
        }
    refs_by_symbol: dict[str, list[object]] = {symbol: [] for symbol in normalized_symbols}
    for file_ref in manifest.data_files:
        ref_symbols = {normalize_history_symbol(symbol) for symbol in file_ref.symbols}
        for symbol in normalized_symbols:
            if symbol in ref_symbols:
                refs_by_symbol[symbol].append(file_ref)
    missing_symbols = [symbol for symbol, refs in refs_by_symbol.items() if not refs]
    if missing_symbols:
        raise FileNotFoundError(
            "context settlement has no hash-pinned history file for requested symbols: "
            f"symbols={missing_symbols}, manifest={manifest_path}"
        )

    histories: dict[str, list[dict[str, Any]]] = {}
    selected_file_hashes: dict[str, str] = {}
    for symbol in normalized_symbols:
        bars: list[HistoryBar] = []
        for untyped_ref in refs_by_symbol[symbol]:
            file_ref = cast(Any, untyped_ref)
            path = resolve_history_data_file_path(manifest_path, manifest, file_ref)
            if not path.is_file():
                raise FileNotFoundError(
                    f"context settlement history file is missing: symbol={symbol}, path={path}"
                )
            actual_hash = file_sha256(path)
            expected_hash = str(file_ref.sha256).lower()
            if not expected_hash or actual_hash.lower() != expected_hash:
                raise ValueError(
                    "context settlement history file hash mismatch: "
                    f"symbol={symbol}, path={path}, expected={expected_hash}, actual={actual_hash}"
                )
            selected_file_hashes[str(path)] = actual_hash
            bars.extend(load_history_bars_from_file(path, str(file_ref.format)))
        validated_bars = _validate_loaded_symbol_bars(symbol, bars)
        histories[symbol] = [bar.to_dict() for bar in validated_bars]

    evidence: dict[str, object] = {
        "dataset_status": validation_status,
        "validated_manifest_hash": validated_manifest_hash,
        "validated_dataset_end_date": str(validation.get("end_date", "")),
        "requested_symbol_count": len(normalized_symbols),
        "loaded_symbol_count": len(histories),
        "loaded_row_count": sum(len(rows) for rows in histories.values()),
        "selected_file_hashes": dict(sorted(selected_file_hashes.items())),
        "selective_hash_validation": True,
    }
    return histories, evidence


def _validate_loaded_symbol_bars(symbol: str, bars: Iterable[HistoryBar]) -> list[HistoryBar]:
    selected: list[HistoryBar] = []
    seen_dates: set[str] = set()
    for bar in bars:
        if normalize_history_symbol(bar.symbol) != symbol:
            continue
        if bar.date in seen_dates:
            raise ValueError(f"duplicate context settlement history date: symbol={symbol}, date={bar.date}")
        if min(bar.open, bar.high, bar.low, bar.close, bar.adjusted_close) <= 0.0:
            raise ValueError(f"nonpositive context settlement OHLC value: symbol={symbol}, date={bar.date}")
        if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
            raise ValueError(f"invalid context settlement OHLC ordering: symbol={symbol}, date={bar.date}")
        if bar.volume < 0:
            raise ValueError(f"negative context settlement volume: symbol={symbol}, date={bar.date}")
        seen_dates.add(bar.date)
        selected.append(bar)
    if not selected:
        raise ValueError(f"context settlement history file contains no rows for symbol={symbol}")
    return sorted(selected, key=lambda bar: bar.date)


def _next_pending_id(pending_ids: Sequence[str], last_examined_decision_id: str) -> str:
    if not pending_ids:
        return ""
    if last_examined_decision_id not in pending_ids:
        return pending_ids[0]
    index = pending_ids.index(last_examined_decision_id)
    return pending_ids[(index + 1) % len(pending_ids)]


def _read_optional_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return _read_required_json_object(path)


def _read_required_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"required JSON artifact is missing: path={path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise TypeError(f"required JSON artifact must be an object: path={path}")
    return cast(dict[str, object], parsed)


def _file_content_hash(path: Path) -> str:
    if not path.exists():
        return hashlib.sha256(b"").hexdigest()
    return file_sha256(path)


def _stable_hash(record: Mapping[str, object]) -> str:
    value = {key: item for key, item in record.items() if not key.endswith("_hash")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(record), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
