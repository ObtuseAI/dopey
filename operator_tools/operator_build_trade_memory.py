"""OPERATOR TOOL - build the Trade Memory Graph index from the honest ledger.

Streams the verified backtest trade ledger, enriches each trade with
point-in-time spine conditions (stretch vs 20-day average, realized vol) at
its signal date, and persists a compact per-trade memory index plus a
family x condition summary. Retrieval (dopey.strategy_engineering.trade_memory)
reads the compact index without touching the 500MB ledger again.

Measure-only: the memory summarizes prior CONDITIONAL outcomes; it never
scores, sizes, or promotes. Paper-only, live-blocked.

Usage:  .venv\\Scripts\\python operator_tools\\operator_build_trade_memory.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey.strategy_engineering.trade_memory import (  # noqa: E402
    CORRUPTION_GUARD_VERSION,
    MEMORY_VERSION,
    OUTCOME_UNIT,
    STRETCH_BUCKETS,
    TradeMemoryCorruptionError,
    enrich_record,
)
from dopey.strategy_engineering.trade_memory_active import (  # noqa: E402
    ACTIVE_POINTER_NAME,
    publish_active_trade_memory_generation,
)
from dopey.strategy_engineering.trade_memory_sqlite import (  # noqa: E402
    build_trade_memory_sqlite,
    retrieve_similar_indexed,
    validate_trade_memory_sqlite_projection,
)
from dopey.strategy_engineering.swing_target_discovery import load_ohlcv_history  # noqa: E402
from dopey.protocols.identity import canonical_hash  # noqa: E402
from dopey_backtest.trade_records_recovery import (  # noqa: E402
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402

HISTORY_ROOT = REPO / "dopey_data" / "history" / "raw"
MEMORY_DIR = REPO / "artifacts" / "dopey" / "trade_memory"
INDEX_PATH = MEMORY_DIR / "trade_memory_index.jsonl"
SQLITE_PATH = MEMORY_DIR / "trade_memory_index.sqlite3"
INDEX_MANIFEST_PATH = MEMORY_DIR / "trade_memory_index_manifest.json"
SUMMARY_PATH = MEMORY_DIR / "trade_memory_summary.json"
GENERATIONS_DIR = MEMORY_DIR / "generations"


class TradeMemoryPacketPaths(NamedTuple):
    index_jsonl: Path
    sqlite: Path
    manifest: Path
    summary: Path


def _packet_paths(directory: Path) -> TradeMemoryPacketPaths:
    return TradeMemoryPacketPaths(
        index_jsonl=directory / INDEX_PATH.name,
        sqlite=directory / SQLITE_PATH.name,
        manifest=directory / INDEX_MANIFEST_PATH.name,
        summary=directory / SUMMARY_PATH.name,
    )


def _stable_packet_paths() -> TradeMemoryPacketPaths:
    return TradeMemoryPacketPaths(
        index_jsonl=INDEX_PATH,
        sqlite=SQLITE_PATH,
        manifest=INDEX_MANIFEST_PATH,
        summary=SUMMARY_PATH,
    )


def _require_distinct_packet_paths(
    paths: TradeMemoryPacketPaths,
    packet_name: str,
) -> None:
    resolved_paths: dict[Path, Path] = {
        path: path.resolve(strict=False) for path in paths
    }
    if len(set(resolved_paths.values())) != len(paths):
        raise ValueError(
            "trade-memory packet paths contain resolved aliases: "
            f"packet={packet_name}, paths="
            f"{ {str(path): str(resolved) for path, resolved in resolved_paths.items()} }"
        )
    existing_paths = [path for path in paths if path.exists()]
    for index, first_path in enumerate(existing_paths):
        if not first_path.is_file():
            raise IsADirectoryError(
                "trade-memory packet path is not a file: "
                f"packet={packet_name}, path={first_path}"
            )
        for second_path in existing_paths[index + 1 :]:
            if os.path.samefile(first_path, second_path):
                raise ValueError(
                    "trade-memory packet paths refer to the same file: "
                    f"packet={packet_name}, first={first_path}, "
                    f"second={second_path}"
                )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"trade-memory packet JSON is invalid: path={path}") from exc
    if not isinstance(value, Mapping):
        raise TypeError(
            "trade-memory packet JSON must contain an object: "
            f"path={path}, actual={type(value).__name__}"
        )
    return {str(key): item for key, item in value.items()}


def _durable_copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"trade-memory packet source is missing: path={source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle:
        with destination.open("xb") as destination_handle:
            shutil.copyfileobj(source_handle, destination_handle)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
    source_hash = _file_sha256(source)
    destination_hash = _file_sha256(destination)
    if source_hash != destination_hash:
        raise OSError(
            "trade-memory packet copy hash mismatch: "
            f"source={source}, destination={destination}, "
            f"source_sha256={source_hash}, destination_sha256={destination_hash}"
        )


def _replace_file(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _generation_id(generated_utc: datetime) -> str:
    timestamp = generated_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{uuid.uuid4().hex[:12]}"


@contextmanager
def _exclusive_build_lock(lock_path: Path) -> Iterator[None]:
    try:
        file_descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError as exc:
        raise RuntimeError(
            "trade-memory build is already locked; inspect the existing build "
            f"before retrying: lock_path={lock_path}"
        ) from exc
    try:
        lock_payload = json.dumps(
            {
                "pid": os.getpid(),
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        ).encode("utf-8")
        os.write(file_descriptor, lock_payload)
        os.fsync(file_descriptor)
        yield
    finally:
        os.close(file_descriptor)
        lock_path.unlink()


def _active_manifest(
    raw_manifest: Mapping[str, object],
    generation_id: str,
    generation_paths: TradeMemoryPacketPaths,
    stable_paths: TradeMemoryPacketPaths,
) -> dict[str, Any]:
    body = {
        str(key): value
        for key, value in raw_manifest.items()
        if str(key) != "manifest_hash"
    }
    body.update(
        {
            "generation_id": generation_id,
            "source_jsonl_path": str(stable_paths.index_jsonl.resolve()),
            "sqlite_path": str(stable_paths.sqlite.resolve()),
            "generation_source_jsonl_path": str(generation_paths.index_jsonl.resolve()),
            "generation_sqlite_path": str(generation_paths.sqlite.resolve()),
            "generation_manifest_path": str(generation_paths.manifest.resolve()),
            "generation_summary_path": str(generation_paths.summary.resolve()),
            "stable_files_are_active_generation_copies": True,
        }
    )
    return {**body, "manifest_hash": canonical_hash(body)}


def _summary(
    generated_utc: datetime,
    generation_id: str,
    source_trade_count: int,
    written: int,
    unique_economic_trade_count: int,
    quarantine_reason_counts: Mapping[str, int],
    quarantine_identity_sha256: str,
    families: Mapping[str, int],
    index_manifest: Mapping[str, object],
    per_family: Mapping[str, object],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "artifact_type": "trade_memory_summary",
        "memory_version": MEMORY_VERSION,
        "generation_id": generation_id,
        "generated_utc": generated_utc.isoformat(),
        "source_trade_count": source_trade_count,
        "indexed_trade_count": written,
        "unique_economic_trade_count": unique_economic_trade_count,
        "row_fanout_ratio": (
            round(written / unique_economic_trade_count, 6)
            if unique_economic_trade_count
            else None
        ),
        "corruption_guard_version": CORRUPTION_GUARD_VERSION,
        "quarantined_corrupt_trade_count": sum(
            quarantine_reason_counts.values()
        ),
        "quarantine_reason_counts": dict(
            sorted(quarantine_reason_counts.items())
        ),
        "quarantine_identity_sha256": quarantine_identity_sha256,
        "quarantined_rows_preserved_in_source_ledger": True,
        "outcome_unit": OUTCOME_UNIT,
        "family_counts": dict(sorted(families.items())),
        "indexed_projection": dict(index_manifest),
        "stretch_buckets": [name for name, _low, _high in STRETCH_BUCKETS],
        "per_family": dict(per_family),
        "canonical_jsonl_remains_source_of_truth": True,
        "stable_packet_published_only_after_full_validation": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "summary_hash": canonical_hash(body)}


def _validate_packet(paths: TradeMemoryPacketPaths) -> dict[str, Any]:
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(
                f"trade-memory packet is incomplete: missing_path={path}"
            )
    manifest = _load_json_object(paths.manifest)
    summary = _load_json_object(paths.summary)
    projection_validation = validate_trade_memory_sqlite_projection(
        paths.index_jsonl,
        paths.sqlite,
        manifest,
    )
    summary_hash = summary.get("summary_hash")
    if not isinstance(summary_hash, str) or not summary_hash:
        raise ValueError(f"trade-memory summary hash is missing: path={paths.summary}")
    summary_body = {
        key: value for key, value in summary.items() if key != "summary_hash"
    }
    actual_summary_hash = canonical_hash(summary_body)
    if summary_hash != actual_summary_hash:
        raise ValueError(
            "trade-memory summary hash mismatch: "
            f"path={paths.summary}, expected={summary_hash}, "
            f"actual={actual_summary_hash}"
        )
    if summary.get("indexed_projection") != manifest:
        raise ValueError(
            "trade-memory summary embeds a different projection manifest: "
            f"summary_path={paths.summary}, manifest_path={paths.manifest}"
        )
    expected_summary_values: dict[str, object] = {
        "artifact_type": "trade_memory_summary",
        "memory_version": MEMORY_VERSION,
        "generation_id": manifest.get("generation_id"),
        "indexed_trade_count": projection_validation["row_count"],
        "outcome_unit": OUTCOME_UNIT,
        "family_counts": projection_validation["family_counts"],
        "stretch_buckets": [name for name, _low, _high in STRETCH_BUCKETS],
        "canonical_jsonl_remains_source_of_truth": True,
        "stable_packet_published_only_after_full_validation": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    for field_name, expected_value in expected_summary_values.items():
        actual_value = summary.get(field_name)
        if actual_value != expected_value:
            raise ValueError(
                "trade-memory summary does not match validated packet: "
                f"field={field_name}, expected={expected_value}, "
                f"actual={actual_value}"
            )
    family_counts = projection_validation["family_counts"]
    stored_per_family = summary.get("per_family")
    if not isinstance(stored_per_family, Mapping):
        raise TypeError(
            "trade-memory summary per-family data must be an object: "
            f"path={paths.summary}, actual={type(stored_per_family).__name__}"
        )
    if set(stored_per_family) != set(family_counts):
        raise ValueError(
            "trade-memory summary family keys do not match indexed families: "
            f"stored={sorted(stored_per_family)}, "
            f"indexed={sorted(family_counts)}"
        )
    for family in sorted(family_counts):
        fresh_retrieval = retrieve_similar_indexed(
            paths.sqlite,
            family,
            None,
            None,
            None,
        )
        if stored_per_family[family] != fresh_retrieval:
            raise ValueError(
                "trade-memory summary retrieval does not match SQLite index: "
                f"family={family}, sqlite_path={paths.sqlite}"
            )
    return {
        **projection_validation,
        "generation_id": manifest.get("generation_id"),
        "summary_hash": summary_hash,
        "packet_validation": "passed",
    }


def _restore_replaced_files(
    replaced_paths: list[Path],
    backup_paths: Mapping[Path, Path | None],
) -> list[Exception]:
    rollback_errors: list[Exception] = []
    for destination in reversed(replaced_paths):
        backup_path = backup_paths[destination]
        try:
            if backup_path is None:
                destination.unlink(missing_ok=True)
            else:
                _replace_file(backup_path, destination)
        except Exception as exc:
            rollback_errors.append(exc)
    return rollback_errors


def _assert_packet_matches_prior_hashes(
    stable_paths: TradeMemoryPacketPaths,
    prior_hashes: Mapping[Path, str | None],
) -> None:
    for path in stable_paths:
        expected_hash = prior_hashes[path]
        if expected_hash is None:
            if path.exists():
                raise RuntimeError(
                    "trade-memory publication rollback left a new active file: "
                    f"path={path}"
                )
            continue
        if not path.is_file():
            raise RuntimeError(
                "trade-memory publication rollback did not restore active file: "
                f"path={path}"
            )
        actual_hash = _file_sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                "trade-memory publication rollback restored different bytes: "
                f"path={path}, expected_sha256={expected_hash}, "
                f"actual_sha256={actual_hash}"
            )


def _publish_stable_packet(
    generation_paths: TradeMemoryPacketPaths,
    stable_paths: TradeMemoryPacketPaths,
) -> dict[str, Any]:
    _require_distinct_packet_paths(generation_paths, "generation")
    _require_distinct_packet_paths(stable_paths, "stable")
    _validate_packet(generation_paths)
    stable_parent = stable_paths.index_jsonl.parent.resolve()
    if any(path.parent.resolve() != stable_parent for path in stable_paths):
        raise ValueError(
            "trade-memory stable packet files must share one directory: "
            f"paths={[str(path) for path in stable_paths]}"
        )
    stable_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=stable_parent,
        prefix=".trade-memory-publish-",
    ) as transaction_name:
        transaction_directory = Path(transaction_name)
        staged_paths = _packet_paths(transaction_directory / "new")
        backup_directory = transaction_directory / "prior"
        for source, staged in zip(generation_paths, staged_paths, strict=True):
            _durable_copy(source, staged)
        backup_paths: dict[Path, Path | None] = {}
        prior_hashes: dict[Path, str | None] = {}
        for stable_path in stable_paths:
            if stable_path.exists() and not stable_path.is_file():
                raise IsADirectoryError(
                    f"trade-memory active packet path is not a file: path={stable_path}"
                )
            if stable_path.is_file():
                backup_path = backup_directory / stable_path.name
                _durable_copy(stable_path, backup_path)
                backup_paths[stable_path] = backup_path
                prior_hashes[stable_path] = _file_sha256(stable_path)
            else:
                backup_paths[stable_path] = None
                prior_hashes[stable_path] = None
        replaced_paths: list[Path] = []
        try:
            for staged_path, stable_path in zip(
                staged_paths,
                stable_paths,
                strict=True,
            ):
                _replace_file(staged_path, stable_path)
                replaced_paths.append(stable_path)
            return _validate_packet(stable_paths)
        except Exception as publish_error:
            rollback_errors = _restore_replaced_files(
                replaced_paths,
                backup_paths,
            )
            try:
                _assert_packet_matches_prior_hashes(stable_paths, prior_hashes)
            except Exception as exc:
                rollback_errors.append(exc)
            if rollback_errors:
                raise ExceptionGroup(
                    "trade-memory publication failed and rollback was incomplete",
                    [publish_error, *rollback_errors],
                )
            raise


def _spine_lookup() -> dict[str, tuple[list[float], list[str]]]:
    bars_by_symbol = load_ohlcv_history(HISTORY_ROOT)
    lookup: dict[str, tuple[list[float], list[str]]] = {}
    for symbol, bars in bars_by_symbol.items():
        rows = sorted(bars, key=lambda b: str(b["date"]))
        lookup[symbol] = (
            [float(b["close"]) for b in rows],
            [str(b["date"]) for b in rows],
        )
    return lookup


def main() -> int:
    spine = _spine_lookup()
    resolution = resolve_default_backtest_trade_ledger()
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    GENERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    generated_utc = datetime.now(timezone.utc)
    generation_id = _generation_id(generated_utc)
    generation_directory = GENERATIONS_DIR / generation_id
    stable_paths = _stable_packet_paths()
    lock_path = MEMORY_DIR / ".trade_memory_build.lock"
    with _exclusive_build_lock(lock_path):
        if generation_directory.exists():
            raise FileExistsError(
                "trade-memory generation path already exists: "
                f"path={generation_directory}"
            )
        with tempfile.TemporaryDirectory(
            dir=MEMORY_DIR,
            prefix=f".trade-memory-generation-{generation_id}-",
        ) as staging_name:
            staging_directory = Path(staging_name)
            staging_paths = _packet_paths(staging_directory)
            generation_paths = _packet_paths(generation_directory)
            families: dict[str, int] = {}
            written = 0
            source_trade_count = 0
            unique_economic_trade_ids: set[str] = set()
            quarantine_reason_counts: dict[str, int] = {}
            quarantine_identity_digest = hashlib.sha256()
            with staging_paths.index_jsonl.open("x", encoding="utf-8") as handle:
                for record in iter_verified_trade_records(resolution):
                    source_trade_count += 1
                    try:
                        enriched = enrich_record(record, spine)
                    except TradeMemoryCorruptionError as error:
                        quarantine_reason_counts[error.reason_code] = (
                            quarantine_reason_counts.get(error.reason_code, 0)
                            + 1
                        )
                        quarantine_identity = canonical_hash(
                            {
                                "trade_id": record.get("trade_id"),
                                "record_hash": record.get("record_hash"),
                                "symbol": record.get("symbol"),
                                "signal_date": record.get("signal_date"),
                                "reason_code": error.reason_code,
                            }
                        )
                        quarantine_identity_digest.update(
                            f"{quarantine_identity}\n".encode("utf-8")
                        )
                        continue
                    if enriched is None:
                        continue
                    economic_trade_id = canonical_hash(
                        {
                            "symbol": record.get("symbol"),
                            "entry_date": record.get("entry_date"),
                            "exit_date": record.get("exit_date"),
                            "candidate_strategy": record.get(
                                "candidate_strategy"
                            ),
                            "entry_premium": record.get("entry_premium"),
                            "exit_premium": record.get("exit_premium"),
                        }
                    )
                    unique_economic_trade_ids.add(economic_trade_id)
                    handle.write(json.dumps(enriched, sort_keys=True) + "\n")
                    family = str(enriched["family"])
                    families[family] = families.get(family, 0) + 1
                    written += 1
                handle.flush()
                os.fsync(handle.fileno())
            raw_manifest = build_trade_memory_sqlite(
                staging_paths.index_jsonl,
                staging_paths.sqlite,
            )
            index_manifest = _active_manifest(
                raw_manifest,
                generation_id,
                generation_paths,
                stable_paths,
            )
            write_json_atomic(staging_paths.manifest, index_manifest)
            per_family = {
                family: retrieve_similar_indexed(
                    staging_paths.sqlite,
                    family,
                    None,
                    None,
                    None,
                )
                for family in sorted(families)
            }
            summary = _summary(
                generated_utc,
                generation_id,
                source_trade_count,
                written,
                len(unique_economic_trade_ids),
                quarantine_reason_counts,
                quarantine_identity_digest.hexdigest(),
                families,
                index_manifest,
                per_family,
            )
            write_json_atomic(staging_paths.summary, summary)
            _validate_packet(staging_paths)
            _replace_file(staging_directory, generation_directory)
            publication_validation = _publish_stable_packet(
                generation_paths,
                stable_paths,
            )
            active_pointer = publish_active_trade_memory_generation(
                MEMORY_DIR,
                generation_directory,
            )
    print(
        json.dumps(
            {
                "indexed_trade_count": written,
                "source_trade_count": source_trade_count,
                "unique_economic_trade_count": len(
                    unique_economic_trade_ids
                ),
                "quarantined_corrupt_trade_count": sum(
                    quarantine_reason_counts.values()
                ),
                "quarantine_reason_counts": dict(
                    sorted(quarantine_reason_counts.items())
                ),
                "families": dict(sorted(families.items())),
                "generation_id": generation_id,
                "generation_directory": str(generation_directory),
                "index_path": str(INDEX_PATH),
                "sqlite_path": str(SQLITE_PATH),
                "index_manifest_path": str(INDEX_MANIFEST_PATH),
                "summary_path": str(SUMMARY_PATH),
                "active_pointer_path": str(MEMORY_DIR / ACTIVE_POINTER_NAME),
                "active_pointer_hash": active_pointer["pointer_hash"],
                "packet_validation": publication_validation["packet_validation"],
                "indexed_parity": publication_validation["indexed_parity"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
