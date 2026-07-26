"""Streaming identity and integrity audit for cognitive JSONL ledgers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash


LEDGER_AUDIT_VERSION = "dopey-cognitive-ledger-audit-v1"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_cognitive_ledger(
    path: Path,
    identity_field: str,
) -> dict[str, Any]:
    if not identity_field:
        raise ValueError("cognitive ledger audit requires a non-empty identity field")
    if not path.is_file():
        raise FileNotFoundError(f"cognitive ledger is missing: path={path}")
    identity_hashes: dict[str, str] = {}
    row_count = 0
    identical_duplicate_count = 0
    conflicting_identity_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"cognitive ledger contains invalid JSON: path={path}, line={line_number}"
                ) from exc
            if not isinstance(decoded, dict):
                raise TypeError(
                    f"cognitive ledger entry must be an object: path={path}, line={line_number}"
                )
            identity = decoded.get(identity_field)
            if not isinstance(identity, str) or not identity:
                raise ValueError(
                    "cognitive ledger entry lacks the required identity: "
                    f"path={path}, line={line_number}, identity_field={identity_field}"
                )
            row_count += 1
            record_hash = canonical_hash(decoded)
            existing_hash = identity_hashes.get(identity)
            if existing_hash is None:
                identity_hashes[identity] = record_hash
            elif existing_hash == record_hash:
                identical_duplicate_count += 1
            else:
                conflicting_identity_ids.add(identity)
    body: dict[str, Any] = {
        "artifact_type": "cognitive_jsonl_ledger_audit",
        "audit_version": LEDGER_AUDIT_VERSION,
        "audit_status": (
            "blocked_conflicting_identity_records"
            if conflicting_identity_ids
            else "complete_identical_duplicates_detected"
            if identical_duplicate_count
            else "complete_unique"
        ),
        "path": str(path.resolve()),
        "source_sha256": _file_sha256(path),
        "identity_field": identity_field,
        "row_count": row_count,
        "unique_identity_count": len(identity_hashes),
        "identical_duplicate_count": identical_duplicate_count,
        "conflicting_identity_count": len(conflicting_identity_ids),
        "conflicting_identity_ids": sorted(conflicting_identity_ids),
        "ledger_rewritten": False,
        "historical_records_deleted": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "audit_hash": canonical_hash(body)}
