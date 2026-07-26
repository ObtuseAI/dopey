"""Indexed, content-addressed projection of the canonical trade-memory JSONL."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from dopey.protocols.identity import canonical_hash

from .trade_memory import MEMORY_VERSION, STRETCH_BUCKETS, _outcome_stats


TRADE_MEMORY_INDEX_VERSION: Final[str] = "dopey-trade-memory-sqlite-v2"
REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "family",
        "strategy",
        "direction",
        "symbol",
        "signal_date",
        "path_pnl",
        "trade_return_model_units",
        "win",
        "mfe",
        "mae",
        "exit_reason",
        "holding_steps",
        "stretch_bucket",
        "rvol_bucket",
    }
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_distinct_projection_paths(
    source_jsonl_path: Path,
    sqlite_path: Path,
) -> tuple[Path, Path]:
    source_resolved = source_jsonl_path.resolve(strict=True)
    sqlite_resolved = sqlite_path.resolve(strict=False)
    if source_resolved == sqlite_resolved:
        raise ValueError(
            "canonical trade-memory JSONL and SQLite projection paths alias: "
            f"source={source_jsonl_path}, sqlite={sqlite_path}, "
            f"resolved={source_resolved}"
        )
    if sqlite_path.exists():
        if not sqlite_path.is_file():
            raise IsADirectoryError(
                f"trade-memory SQLite projection path is not a file: path={sqlite_path}"
            )
        if os.path.samefile(source_resolved, sqlite_path):
            raise ValueError(
                "canonical trade-memory JSONL and SQLite projection refer to "
                "the same file: "
                f"source={source_jsonl_path}, sqlite={sqlite_path}"
            )
    return source_resolved, sqlite_resolved


def _optional_finite_float(
    value: object,
    field_name: str,
    line_number: int,
) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(
            "trade-memory numeric field has invalid type: "
            f"line={line_number}, field={field_name}, actual={type(value).__name__}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            f"trade-memory numeric field must be finite: line={line_number}, field={field_name}"
        )
    return number


def _required_string(
    record: Mapping[str, object],
    field_name: str,
    line_number: int,
) -> str:
    value = record.get(field_name)
    if not isinstance(value, str):
        raise TypeError(
            "trade-memory string field has invalid type: "
            f"line={line_number}, field={field_name}, actual={type(value).__name__}"
        )
    return value


def _validated_record(
    value: object,
    line_number: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"trade-memory record must be an object: line={line_number}")
    record = {str(key): item for key, item in value.items()}
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        raise ValueError(
            f"trade-memory record is incomplete: line={line_number}, missing={missing}"
        )
    path_pnl = _optional_finite_float(record["path_pnl"], "path_pnl", line_number)
    if path_pnl is None:
        raise ValueError(f"trade-memory path PnL cannot be null: line={line_number}")
    trade_return = _optional_finite_float(
        record["trade_return_model_units"],
        "trade_return_model_units",
        line_number,
    )
    if trade_return is None:
        raise ValueError(
            "trade-memory fractional model return cannot be null: "
            f"line={line_number}"
        )
    win = record["win"]
    if not isinstance(win, bool):
        raise TypeError(f"trade-memory win marker must be boolean: line={line_number}")
    holding_steps = record["holding_steps"]
    if (
        not isinstance(holding_steps, int)
        or isinstance(holding_steps, bool)
        or holding_steps < 0
    ):
        raise ValueError(
            f"trade-memory holding steps must be a non-negative integer: line={line_number}"
        )
    normalized: dict[str, Any] = {
        "family": _required_string(record, "family", line_number),
        "strategy": _required_string(record, "strategy", line_number),
        "direction": _required_string(record, "direction", line_number),
        "symbol": _required_string(record, "symbol", line_number),
        "signal_date": _required_string(record, "signal_date", line_number),
        "path_pnl": path_pnl,
        "trade_return_model_units": trade_return,
        "win": win,
        "mfe": _optional_finite_float(record.get("mfe"), "mfe", line_number),
        "mae": _optional_finite_float(record.get("mae"), "mae", line_number),
        "exit_reason": _required_string(record, "exit_reason", line_number),
        "holding_steps": holding_steps,
        "stretch": _optional_finite_float(
            record.get("stretch"), "stretch", line_number
        ),
        "stretch_bucket": _required_string(record, "stretch_bucket", line_number),
        "rvol": _optional_finite_float(record.get("rvol"), "rvol", line_number),
        "rvol_bucket": _required_string(record, "rvol_bucket", line_number),
        "trailing_5d_return": _optional_finite_float(
            record.get("trailing_5d_return"),
            "trailing_5d_return",
            line_number,
        ),
    }
    if not normalized["family"] or not normalized["symbol"]:
        raise ValueError(
            f"trade-memory family and symbol cannot be empty: line={line_number}"
        )
    return normalized


def _canonical_projection_record(
    value: object,
    line_number: int,
) -> tuple[dict[str, Any], str, str, str]:
    record = _validated_record(value, line_number)
    canonical_json = json.dumps(
        record,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    event_id = (
        "trade-memory-event:"
        + canonical_hash({"line": line_number, "hash": content_hash})[:24]
    )
    return record, canonical_json, content_hash, event_id


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = FULL;
        PRAGMA temp_store = MEMORY;
        CREATE TABLE memory_records (
            event_id TEXT PRIMARY KEY NOT NULL,
            source_line_number INTEGER UNIQUE NOT NULL,
            content_hash TEXT NOT NULL,
            family TEXT NOT NULL,
            strategy TEXT NOT NULL,
            direction TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            path_pnl REAL NOT NULL,
            trade_return_model_units REAL NOT NULL,
            win INTEGER NOT NULL CHECK (win IN (0, 1)),
            mfe REAL,
            mae REAL,
            exit_reason TEXT NOT NULL,
            holding_steps INTEGER NOT NULL,
            stretch REAL,
            stretch_bucket TEXT NOT NULL,
            rvol REAL,
            rvol_bucket TEXT NOT NULL,
            trailing_5d_return REAL,
            canonical_json TEXT NOT NULL
        );
        """
    )


def _finalize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX idx_trade_memory_family
            ON memory_records (family);
        CREATE INDEX idx_trade_memory_family_conditions
            ON memory_records (family, strategy, stretch_bucket, rvol_bucket);
        CREATE INDEX idx_trade_memory_symbol_date
            ON memory_records (symbol, signal_date);
        CREATE INDEX idx_trade_memory_content_hash
            ON memory_records (content_hash);
        ANALYZE;
        """
    )


def _read_manifest_body(manifest: Mapping[str, object]) -> dict[str, object]:
    manifest_hash = manifest.get("manifest_hash")
    if not isinstance(manifest_hash, str) or not manifest_hash:
        raise ValueError("trade-memory projection manifest hash is missing")
    body = {
        str(key): value
        for key, value in manifest.items()
        if str(key) != "manifest_hash"
    }
    actual_hash = canonical_hash(body)
    if actual_hash != manifest_hash:
        raise ValueError(
            "trade-memory projection manifest hash mismatch: "
            f"expected={manifest_hash}, actual={actual_hash}"
        )
    return body


def validate_trade_memory_sqlite_projection(
    source_jsonl_path: Path,
    sqlite_path: Path,
    manifest: Mapping[str, object],
) -> dict[str, Any]:
    if not source_jsonl_path.is_file():
        raise FileNotFoundError(
            f"canonical trade-memory JSONL is missing: path={source_jsonl_path}"
        )
    if not sqlite_path.is_file():
        raise FileNotFoundError(
            f"trade-memory SQLite projection is missing: path={sqlite_path}"
        )
    _require_distinct_projection_paths(source_jsonl_path, sqlite_path)
    body = _read_manifest_body(manifest)
    source_sha256 = _file_sha256(source_jsonl_path)
    sqlite_sha256 = _file_sha256(sqlite_path)
    connection = sqlite3.connect(
        f"{sqlite_path.resolve(strict=True).as_uri()}?mode=ro",
        uri=True,
    )
    row_count = 0
    content_hash_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    try:
        connection.execute("PRAGMA query_only = ON")
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        if integrity_rows != [("ok",)]:
            raise ValueError(
                "trade-memory SQLite integrity check failed: "
                f"path={sqlite_path}, result={integrity_rows}"
            )
        indexed_rows = iter(
            connection.execute(
                """
                SELECT source_line_number, event_id, content_hash, canonical_json, family
                FROM memory_records
                ORDER BY source_line_number
                """
            )
        )
        with source_jsonl_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    decoded = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "canonical trade-memory JSONL contains invalid JSON: "
                        f"path={source_jsonl_path}, line={line_number}"
                    ) from exc
                record, canonical_json, content_hash, event_id = (
                    _canonical_projection_record(decoded, line_number)
                )
                indexed_row = next(indexed_rows, None)
                expected_row = (
                    line_number,
                    event_id,
                    content_hash,
                    canonical_json,
                    record["family"],
                )
                if indexed_row != expected_row:
                    raise ValueError(
                        "trade-memory SQLite row does not match canonical JSONL: "
                        f"path={sqlite_path}, line={line_number}, "
                        f"expected={expected_row}, actual={indexed_row}"
                    )
                row_count += 1
                content_hash_counts[content_hash] = (
                    content_hash_counts.get(content_hash, 0) + 1
                )
                family = str(record["family"])
                family_counts[family] = family_counts.get(family, 0) + 1
        extra_row = next(indexed_rows, None)
        if extra_row is not None:
            raise ValueError(
                "trade-memory SQLite contains rows absent from canonical JSONL: "
                f"path={sqlite_path}, first_extra_row={extra_row}"
            )
    finally:
        connection.close()
    source_sha256_after = _file_sha256(source_jsonl_path)
    if source_sha256_after != source_sha256:
        raise RuntimeError(
            "canonical trade-memory JSONL changed during projection validation: "
            f"path={source_jsonl_path}, before={source_sha256}, "
            f"after={source_sha256_after}"
        )
    duplicate_content_row_count = sum(
        count - 1 for count in content_hash_counts.values() if count > 1
    )
    expected_manifest_values: dict[str, object] = {
        "artifact_type": "trade_memory_sqlite_projection_manifest",
        "index_version": TRADE_MEMORY_INDEX_VERSION,
        "memory_version": MEMORY_VERSION,
        "source_jsonl_sha256": source_sha256,
        "sqlite_sha256": sqlite_sha256,
        "row_count": row_count,
        "unique_content_hash_count": len(content_hash_counts),
        "duplicate_content_row_count": duplicate_content_row_count,
        "family_counts": dict(sorted(family_counts.items())),
        "identity_policy": "source_line_number_plus_canonical_content_hash",
        "canonical_jsonl_remains_source_of_truth": True,
        "sqlite_is_rebuildable_derived_index": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    for field_name, expected_value in expected_manifest_values.items():
        actual_value = body.get(field_name)
        if actual_value != expected_value:
            raise ValueError(
                "trade-memory projection manifest does not match validated data: "
                f"field={field_name}, expected={expected_value}, actual={actual_value}"
            )
    return {
        "row_count": row_count,
        "unique_content_hash_count": len(content_hash_counts),
        "duplicate_content_row_count": duplicate_content_row_count,
        "family_counts": dict(sorted(family_counts.items())),
        "source_jsonl_sha256": source_sha256,
        "sqlite_sha256": sqlite_sha256,
        "integrity_check": "ok",
        "indexed_parity": True,
        "duplicate_events_preserved": True,
    }


def build_trade_memory_sqlite(
    source_jsonl_path: Path,
    sqlite_path: Path,
) -> dict[str, Any]:
    if not source_jsonl_path.is_file():
        raise FileNotFoundError(
            f"canonical trade-memory JSONL is missing: path={source_jsonl_path}"
        )
    source_resolved, sqlite_resolved = _require_distinct_projection_paths(
        source_jsonl_path,
        sqlite_path,
    )
    source_sha256 = _file_sha256(source_jsonl_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=sqlite_path.parent,
        prefix=f".{sqlite_path.name}.",
        suffix=".tmp",
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    row_count = 0
    content_hash_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            _initialize_schema(connection)
            with source_jsonl_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        decoded = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            "canonical trade-memory JSONL contains invalid JSON: "
                            f"path={source_jsonl_path}, line={line_number}"
                        ) from exc
                    record, canonical_json, content_hash, event_id = (
                        _canonical_projection_record(decoded, line_number)
                    )
                    connection.execute(
                        """
                        INSERT INTO memory_records (
                            event_id, source_line_number, content_hash, family, strategy,
                            direction, symbol, signal_date, path_pnl,
                            trade_return_model_units, win, mfe, mae, exit_reason,
                            holding_steps, stretch, stretch_bucket, rvol, rvol_bucket,
                            trailing_5d_return, canonical_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            line_number,
                            content_hash,
                            record["family"],
                            record["strategy"],
                            record["direction"],
                            record["symbol"],
                            record["signal_date"],
                            record["path_pnl"],
                            record["trade_return_model_units"],
                            int(record["win"]),
                            record["mfe"],
                            record["mae"],
                            record["exit_reason"],
                            record["holding_steps"],
                            record["stretch"],
                            record["stretch_bucket"],
                            record["rvol"],
                            record["rvol_bucket"],
                            record["trailing_5d_return"],
                            canonical_json,
                        ),
                    )
                    row_count += 1
                    content_hash_counts[content_hash] = (
                        content_hash_counts.get(content_hash, 0) + 1
                    )
                    family = str(record["family"])
                    family_counts[family] = family_counts.get(family, 0) + 1
            _finalize_schema(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        source_sha256_after = _file_sha256(source_jsonl_path)
        if source_sha256_after != source_sha256:
            raise RuntimeError(
                "canonical trade-memory JSONL changed during SQLite build: "
                f"path={source_jsonl_path}, before={source_sha256}, "
                f"after={source_sha256_after}"
            )
        duplicate_content_row_count = sum(
            count - 1 for count in content_hash_counts.values() if count > 1
        )
        body: dict[str, Any] = {
            "artifact_type": "trade_memory_sqlite_projection_manifest",
            "index_version": TRADE_MEMORY_INDEX_VERSION,
            "memory_version": MEMORY_VERSION,
            "source_jsonl_path": str(source_resolved),
            "source_jsonl_sha256": source_sha256,
            "sqlite_path": str(sqlite_resolved),
            "sqlite_sha256": _file_sha256(temporary_path),
            "row_count": row_count,
            "unique_content_hash_count": len(content_hash_counts),
            "duplicate_content_row_count": duplicate_content_row_count,
            "family_counts": dict(sorted(family_counts.items())),
            "identity_policy": "source_line_number_plus_canonical_content_hash",
            "canonical_jsonl_remains_source_of_truth": True,
            "sqlite_is_rebuildable_derived_index": True,
            "not_edge_evidence": True,
            "promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
        manifest = {**body, "manifest_hash": canonical_hash(body)}
        validate_trade_memory_sqlite_projection(
            source_jsonl_path,
            temporary_path,
            manifest,
        )
        os.replace(temporary_path, sqlite_path)
        return manifest
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _query_records(
    connection: sqlite3.Connection,
    family: str,
    strategy: str | None,
    stretch_bucket: str | None,
    rvol_bucket: str | None,
) -> list[dict[str, Any]]:
    clauses = ["family = ?"]
    values: list[object] = [family]
    if strategy is not None:
        clauses.append("strategy = ?")
        values.append(strategy)
    if stretch_bucket is not None:
        clauses.append("stretch_bucket = ?")
        values.append(stretch_bucket)
    if rvol_bucket is not None:
        clauses.append("rvol_bucket = ?")
        values.append(rvol_bucket)
    rows = connection.execute(
        "SELECT trade_return_model_units, win, mae "
        "FROM memory_records WHERE " + " AND ".join(clauses),
        values,
    ).fetchall()
    return [
        {
            "trade_return_model_units": float(row[0]),
            "win": bool(row[1]),
            "mae": None if row[2] is None else float(row[2]),
        }
        for row in rows
    ]


def retrieve_similar_indexed(
    sqlite_path: Path,
    family: str,
    stretch_bucket: str | None,
    rvol_bucket: str | None,
    strategy: str | None,
) -> dict[str, Any]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(
            f"trade-memory SQLite index is missing: path={sqlite_path}"
        )
    connection = sqlite3.connect(sqlite_path)
    try:
        connection.execute("PRAGMA query_only = ON")
        family_records = _query_records(
            connection,
            family,
            strategy,
            None,
            None,
        )
        matched = _query_records(
            connection,
            family,
            strategy,
            stretch_bucket,
            rvol_bucket,
        )
        conditional = {
            name: _outcome_stats(
                _query_records(connection, family, strategy, name, None)
            )
            for name, _low, _high in STRETCH_BUCKETS
        }
    finally:
        connection.close()
    return {
        "family": family,
        "strategy_filter": strategy,
        "matched_conditions": {
            "stretch_bucket": stretch_bucket,
            "rvol_bucket": rvol_bucket,
        },
        "family_total": _outcome_stats(family_records),
        "matched": _outcome_stats(matched),
        "conditional_by_stretch": {
            name: statistics
            for name, statistics in conditional.items()
            if statistics["count"] > 0
        },
        "retrieval_backend": TRADE_MEMORY_INDEX_VERSION,
        "canonical_jsonl_remains_source_of_truth": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }
