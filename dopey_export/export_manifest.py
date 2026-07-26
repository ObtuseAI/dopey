"""Manifest hashing and JSON/JSONL helpers for DOPEY exports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .export_models import ExportArtifact, ExportManifest


DETERMINISTIC_CREATED_AT_UTC = "1970-01-01T00:00:00Z"


def sha256_file(path: Path | str) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def canonical_export_hash(record: dict) -> str:
    stripped = {key: value for key, value in record.items() if key != "reproducibility_hash"}
    return reproducibility_hash(stripped)


def raw_json_hash(record: dict) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def manifest_bundle_hash(artifacts: list[ExportArtifact]) -> str:
    payload = [
        {
            "relative_export_path": artifact.relative_export_path,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "record_count": artifact.record_count,
        }
        for artifact in sorted(artifacts, key=lambda item: item.relative_export_path)
    ]
    return reproducibility_hash({"artifacts": payload})


def with_reproducibility_hash(record: dict) -> dict:
    output = dict(record)
    output["reproducibility_hash"] = canonical_export_hash(output)
    return output


def build_export_manifest(
    manifest_id: str,
    bundle_id: str,
    profile: str,
    artifacts: list[ExportArtifact],
    safety_state: dict,
) -> ExportManifest:
    required = [artifact for artifact in artifacts if artifact.required]
    optional = [artifact for artifact in artifacts if not artifact.required]
    seed = ExportManifest(
        manifest_id=manifest_id,
        bundle_id=bundle_id,
        created_at_utc=DETERMINISTIC_CREATED_AT_UTC,
        profile=profile,
        artifact_count=len(artifacts),
        required_artifacts_present=len(required),
        optional_artifacts_present=len(optional),
        total_size_bytes=sum(artifact.size_bytes for artifact in artifacts),
        bundle_sha256=manifest_bundle_hash(artifacts),
        artifacts=artifacts,
        safety_state=safety_state,
        reproducibility_hash="",
    )
    hashed = with_reproducibility_hash(seed.to_dict())
    return ExportManifest(
        manifest_id=seed.manifest_id,
        bundle_id=seed.bundle_id,
        created_at_utc=seed.created_at_utc,
        profile=seed.profile,
        artifact_count=seed.artifact_count,
        required_artifacts_present=seed.required_artifacts_present,
        optional_artifacts_present=seed.optional_artifacts_present,
        total_size_bytes=seed.total_size_bytes,
        bundle_sha256=seed.bundle_sha256,
        artifacts=artifacts,
        safety_state=safety_state,
        reproducibility_hash=hashed["reproducibility_hash"],
    )


def write_json(path: Path | str, record: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def append_jsonl(path: Path | str, record: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return target
