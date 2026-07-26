"""Fail-closed validation for operator-staged local research datasets."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_aware_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "governed dataset timestamp is not ISO-8601: "
            f"field={field_name}, value={value}"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(
            "governed dataset timestamp requires a timezone: "
            f"field={field_name}, value={value}"
        )
    return parsed


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_governed_manifest(manifest_path: Path, event_time: str) -> dict[str, Any]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"governed dataset manifest is missing: path={manifest_path}")
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"governed dataset manifest must be an object: path={manifest_path}")
    required_flags = {
        "paper_only": True,
        "live_blocked": True,
        "not_real_data": False,
        "template_only": False,
        "not_broker_data": True,
        "not_credentials": True,
        "provider_terms_reviewed": True,
    }
    violations = {
        field: {"required": expected, "actual": value.get(field)}
        for field, expected in required_flags.items()
        if value.get(field) is not expected
    }
    license_status = str(value.get("license_status", ""))
    if not license_status.startswith("reviewed_"):
        violations["license_status"] = {
            "required": "reviewed_*",
            "actual": license_status,
        }
    if violations:
        raise ValueError(
            "operator-staged dataset violates research governance: "
            f"manifest_path={manifest_path}, violations={violations}"
        )
    created_at = str(value.get("created_at", ""))
    if not created_at:
        raise ValueError(f"governed dataset manifest lacks created_at: path={manifest_path}")
    if parse_aware_timestamp(created_at, "created_at") > parse_aware_timestamp(event_time, "event_time"):
        raise ValueError(
            "governed dataset manifest was created after the research event: "
            f"manifest_path={manifest_path}, created_at={created_at}, event_time={event_time}"
        )
    file_hashes = value.get("file_hashes")
    row_counts = value.get("row_counts")
    if not isinstance(file_hashes, dict) or not isinstance(row_counts, dict):
        raise TypeError(
            "governed dataset manifest requires file_hashes and row_counts objects: "
            f"manifest_path={manifest_path}"
        )
    return value


def resolve_manifest_file(manifest_path: Path, file_reference: str) -> Path:
    candidate = Path(file_reference)
    if candidate.is_absolute():
        return candidate
    repository_root = manifest_path.resolve().parents[3]
    return repository_root / candidate


def read_validated_csv(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    file_reference: str,
    required_columns: Sequence[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    file_hashes = manifest.get("file_hashes", {})
    row_counts = manifest.get("row_counts", {})
    expected_hash = str(file_hashes.get(file_reference, "")) if isinstance(file_hashes, Mapping) else ""
    expected_rows_raw = row_counts.get(file_reference) if isinstance(row_counts, Mapping) else None
    if not expected_hash or expected_rows_raw is None:
        raise ValueError(
            "dataset file is not hash-and-row pinned by its manifest: "
            f"manifest_path={manifest_path}, file_reference={file_reference}"
        )
    source_path = resolve_manifest_file(manifest_path, file_reference)
    if not source_path.exists():
        raise FileNotFoundError(
            "manifest-pinned dataset file is missing: "
            f"manifest_path={manifest_path}, source_path={source_path}"
        )
    actual_hash = file_sha256(source_path)
    if actual_hash.lower() != expected_hash.lower():
        raise ValueError(
            "manifest-pinned dataset hash mismatch: "
            f"source_path={source_path}, expected_hash={expected_hash}, actual_hash={actual_hash}"
        )
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        missing = sorted(set(required_columns) - set(columns))
        if missing:
            raise ValueError(
                "manifest-pinned dataset lacks required columns: "
                f"source_path={source_path}, missing_columns={missing}, columns={columns}"
            )
        rows = [dict(row) for row in reader]
    expected_rows = int(expected_rows_raw)
    if len(rows) != expected_rows:
        raise ValueError(
            "manifest-pinned dataset row count mismatch: "
            f"source_path={source_path}, expected_rows={expected_rows}, actual_rows={len(rows)}"
        )
    proof = {
        "manifest_path": str(manifest_path),
        "manifest_id": str(manifest.get("manifest_id", "")),
        "manifest_created_at": str(manifest.get("created_at", "")),
        "source_path": str(source_path),
        "file_reference": file_reference,
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "row_count": len(rows),
        "source": str(manifest.get("per_file_sources", {}).get(file_reference, "")),
        "paper_only": True,
        "live_blocked": True,
    }
    return rows, proof
