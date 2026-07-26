"""Crash-safe active-generation resolution for trade-memory evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from dopey.protocols.identity import canonical_hash
from dopey_research_pipeline.artifact_io import write_json_atomic

from .trade_memory import MEMORY_VERSION

ACTIVE_POINTER_VERSION = "dopey-trade-memory-active-pointer-v1"
ACTIVE_POINTER_NAME = "active_generation.json"


class ActiveTradeMemoryPacket(NamedTuple):
    """Validated paths for one immutable trade-memory generation."""

    index_jsonl: Path
    sqlite: Path
    manifest: Path
    summary: Path


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"invalid trade-memory JSON artifact: path={path}, error={error}"
        ) from error
    if not isinstance(value, dict):
        raise TypeError(
            "trade-memory JSON artifact must be an object: "
            f"path={path}, actual={type(value).__name__}"
        )
    return value


def _validated_generation_directory(
    memory_directory: Path,
    relative_generation_directory: object,
) -> Path:
    if (
        not isinstance(relative_generation_directory, str)
        or not relative_generation_directory
    ):
        raise ValueError("active trade-memory pointer lacks generation_directory")
    relative_path = Path(relative_generation_directory)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(
            "active trade-memory generation path must be contained and relative: "
            f"value={relative_generation_directory}"
        )
    resolved_memory = memory_directory.resolve(strict=True)
    resolved_generation = (resolved_memory / relative_path).resolve(strict=True)
    try:
        resolved_generation.relative_to(resolved_memory)
    except ValueError as error:
        raise ValueError(
            "active trade-memory generation escapes memory directory: "
            f"memory_directory={resolved_memory}, "
            f"generation_directory={resolved_generation}"
        ) from error
    if not resolved_generation.is_dir():
        raise NotADirectoryError(
            "active trade-memory generation is not a directory: "
            f"path={resolved_generation}"
        )
    return resolved_generation


def _validate_hash_field(
    record: Mapping[str, object],
    hash_field: str,
    artifact_path: Path,
) -> None:
    expected_hash = record.get(hash_field)
    if not isinstance(expected_hash, str) or not expected_hash:
        raise ValueError(
            "trade-memory artifact hash is missing: "
            f"path={artifact_path}, hash_field={hash_field}"
        )
    body = {key: value for key, value in record.items() if key != hash_field}
    actual_hash = canonical_hash(body)
    if actual_hash != expected_hash:
        raise ValueError(
            "trade-memory artifact hash mismatch: "
            f"path={artifact_path}, hash_field={hash_field}, "
            f"expected={expected_hash}, actual={actual_hash}"
        )


def resolve_active_trade_memory_packet(
    memory_directory: Path,
) -> ActiveTradeMemoryPacket:
    """Resolve and validate the immutable generation selected by one pointer."""

    pointer_path = memory_directory / ACTIVE_POINTER_NAME
    pointer = _load_json_object(pointer_path)
    if pointer.get("pointer_version") != ACTIVE_POINTER_VERSION:
        raise ValueError(
            "incompatible trade-memory active pointer version: "
            f"path={pointer_path}, observed={pointer.get('pointer_version')}"
        )
    _validate_hash_field(pointer, "pointer_hash", pointer_path)
    generation_directory = _validated_generation_directory(
        memory_directory,
        pointer.get("generation_directory"),
    )
    packet = ActiveTradeMemoryPacket(
        index_jsonl=generation_directory / "trade_memory_index.jsonl",
        sqlite=generation_directory / "trade_memory_index.sqlite3",
        manifest=generation_directory / "trade_memory_index_manifest.json",
        summary=generation_directory / "trade_memory_summary.json",
    )
    missing = [str(path) for path in packet if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "active trade-memory generation is incomplete: "
            f"missing_paths={missing}"
        )
    summary = _load_json_object(packet.summary)
    manifest = _load_json_object(packet.manifest)
    _validate_hash_field(summary, "summary_hash", packet.summary)
    _validate_hash_field(manifest, "manifest_hash", packet.manifest)
    expected_generation_id = pointer.get("generation_id")
    if (
        not isinstance(expected_generation_id, str)
        or expected_generation_id != generation_directory.name
        or summary.get("generation_id") != expected_generation_id
        or manifest.get("generation_id") != expected_generation_id
    ):
        raise ValueError(
            "active trade-memory generation identity mismatch: "
            f"pointer={expected_generation_id}, "
            f"directory={generation_directory.name}, "
            f"summary={summary.get('generation_id')}, "
            f"manifest={manifest.get('generation_id')}"
        )
    if summary.get("memory_version") != MEMORY_VERSION:
        raise ValueError(
            "active trade-memory generation has incompatible memory version: "
            f"expected={MEMORY_VERSION}, observed={summary.get('memory_version')}"
        )
    if pointer.get("summary_hash") != summary.get("summary_hash"):
        raise ValueError(
            "active trade-memory pointer summary hash mismatch: "
            f"pointer={pointer.get('summary_hash')}, "
            f"summary={summary.get('summary_hash')}"
        )
    if pointer.get("manifest_hash") != manifest.get("manifest_hash"):
        raise ValueError(
            "active trade-memory pointer manifest hash mismatch: "
            f"pointer={pointer.get('manifest_hash')}, "
            f"manifest={manifest.get('manifest_hash')}"
        )
    return packet


def publish_active_trade_memory_generation(
    memory_directory: Path,
    generation_directory: Path,
) -> dict[str, object]:
    """Atomically select an already complete and internally hashed generation."""

    resolved_memory = memory_directory.resolve(strict=True)
    resolved_generation = generation_directory.resolve(strict=True)
    try:
        relative_generation = resolved_generation.relative_to(resolved_memory)
    except ValueError as error:
        raise ValueError(
            "trade-memory generation must be inside its memory directory: "
            f"memory_directory={resolved_memory}, "
            f"generation_directory={resolved_generation}"
        ) from error
    summary_path = resolved_generation / "trade_memory_summary.json"
    manifest_path = resolved_generation / "trade_memory_index_manifest.json"
    summary = _load_json_object(summary_path)
    manifest = _load_json_object(manifest_path)
    _validate_hash_field(summary, "summary_hash", summary_path)
    _validate_hash_field(manifest, "manifest_hash", manifest_path)
    generation_id = resolved_generation.name
    if (
        summary.get("generation_id") != generation_id
        or manifest.get("generation_id") != generation_id
    ):
        raise ValueError(
            "trade-memory generation identity does not match directory: "
            f"directory={generation_id}, "
            f"summary={summary.get('generation_id')}, "
            f"manifest={manifest.get('generation_id')}"
        )
    body: dict[str, object] = {
        "artifact_type": "trade_memory_active_generation_pointer",
        "pointer_version": ACTIVE_POINTER_VERSION,
        "generation_id": generation_id,
        "generation_directory": relative_generation.as_posix(),
        "memory_version": summary.get("memory_version"),
        "summary_hash": summary.get("summary_hash"),
        "manifest_hash": manifest.get("manifest_hash"),
        "generated_utc": summary.get("generated_utc"),
        "stable_aliases_are_compatibility_copies": True,
        "consumers_must_resolve_this_pointer": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    pointer = {**body, "pointer_hash": canonical_hash(body)}
    write_json_atomic(memory_directory / ACTIVE_POINTER_NAME, pointer)
    resolved = resolve_active_trade_memory_packet(memory_directory)
    if resolved.summary.resolve() != summary_path.resolve():
        raise RuntimeError(
            "published trade-memory pointer resolved a different generation: "
            f"expected={summary_path}, actual={resolved.summary}"
        )
    return pointer


def load_active_trade_memory_summary(
    memory_directory: Path,
) -> dict[str, object]:
    """Load the hashed summary selected by the atomic active pointer."""

    packet = resolve_active_trade_memory_packet(memory_directory)
    return _load_json_object(packet.summary)
