"""Build the hash-verified, paper-only artifact seed used by integration tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, TypedDict


class SeedSource(TypedDict):
    relative_path: str
    mode: Literal["full_file", "latest_jsonl_record", "sanitized_json"]


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts"
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures"
ARCHIVE_PATH = FIXTURE_ROOT / "runtime_artifact_seed_v1.zip"
MANIFEST_PATH = FIXTURE_ROOT / "runtime_artifact_seed_v1_manifest.json"
SEED_VERSION = "dopey-runtime-artifact-seed-v1"

SEALED_BOOLEAN_FIELDS: dict[str, bool] = {
    "broker_connection_enabled": False,
    "broker_connection_used": False,
    "credentials_created": False,
    "credentials_present": False,
    "env_created": False,
    "live_blocked": True,
    "live_trading_enabled": False,
    "paper_only": True,
    "real_order_enabled": False,
    "real_orders_placed": False,
}
PROHIBITED_WORKSTATION_TOKENS: tuple[str, ...] = (
    "c:\\users\\",
    "//frankenstein/",
    "\\\\frankenstein\\",
)
SANITIZED_JSON_FIELDS: dict[str, tuple[str, ...]] = {
    "public_signal_research_breakthrough_v4_validation_summary.json": ("handoff_results",),
    "public_signal_research_breakthrough_v5_summary.json": ("shared_copy_target_root",),
    "public_signal_research_breakthrough_v6_summary.json": ("shared_copy_target_root",),
}


def _full_file_source(relative_path: str) -> SeedSource:
    return {"relative_path": relative_path, "mode": "full_file"}

BASE_SEED_SOURCES: tuple[SeedSource, ...] = (
    {
        "relative_path": "dopey/signal_research/public_signal_research_breakthrough_v1_summary.json",
        "mode": "full_file",
    },
    {
        "relative_path": "dopey/signal_research/research_breakthrough_gate_v1_summary.json",
        "mode": "full_file",
    },
    {
        "relative_path": "dopey/signal_research/research_tournament_leaderboard_v1.jsonl",
        "mode": "full_file",
    },
    {
        "relative_path": "dopey/signal_research/failed_champion_family_quarantine_v1.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/signal_research/failed_champion_family_quarantine_v1_summary.json",
        "mode": "full_file",
    },
    {
        "relative_path": "dopey/champion_repair/public_champion_artifact_guard_v1_summary.json",
        "mode": "full_file",
    },
    {"relative_path": "dopey/tournaments/dopey_tournament.jsonl", "mode": "latest_jsonl_record"},
    {"relative_path": "dopey/mutations/mutation_registry.jsonl", "mode": "latest_jsonl_record"},
    {
        "relative_path": "dopey/failure_feedback/failure_feedback_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/failure_modes/failure_mode_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/ensemble_allocator/ensemble_allocation_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {"relative_path": "dopey/iv_surface/iv_surface_registry.jsonl", "mode": "latest_jsonl_record"},
    {"relative_path": "dopey/macro_events/macro_event_registry.jsonl", "mode": "latest_jsonl_record"},
    {
        "relative_path": "dopey/champion_registry/champion_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/walk_forward_consistency/consistency_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/regime_holdout_corpus_v2/corpus_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/fundamental_fixtures/fundamental_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/meta_governor/meta_governor_registry.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/meta_governor/meta_governor_decisions.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/meta_governor/meta_governor_proof.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/incident_response/incident_rehearsal_summary.json",
        "mode": "full_file",
    },
    {"relative_path": "dopey/lifecycle/lifecycle_summary.json", "mode": "full_file"},
    {
        "relative_path": "dopey/audit/evidence_replay_audit_proof.jsonl",
        "mode": "latest_jsonl_record",
    },
    {"relative_path": "dopey/exports/export_safety_scan.jsonl", "mode": "latest_jsonl_record"},
    {
        "relative_path": "dopey/export_reviews/export_review_proof.jsonl",
        "mode": "latest_jsonl_record",
    },
)

CHECKPOINT_RELATIVE_PATHS: tuple[str, ...] = (
    "dopey/signal_research_v2/public_signal_research_breakthrough_v2_summary.json",
    "dopey/signal_research_v2/research_breakthrough_gate_v2_summary.json",
    "dopey/signal_research_v2/research_candidate_generator_v2_summary.json",
    "dopey/signal_research_v2/research_mutation_queue_v2.jsonl",
    "dopey/signal_research_v2/research_mutation_queue_v2_summary.json",
    "dopey/signal_research_v2/research_tournament_v2_summary.json",
    "dopey/signal_research_v3/public_signal_research_breakthrough_v3_summary.json",
    "dopey/signal_research_v3/research_breakthrough_gate_v3_summary.json",
    "dopey/signal_research_v3/research_candidate_generator_v3_summary.json",
    "dopey/signal_research_v3/research_mutation_queue_v3.jsonl",
    "dopey/signal_research_v3/research_mutation_queue_v3_summary.json",
    "dopey/signal_research_v3/research_path_trades_v3.jsonl",
    "dopey/signal_research_v3/research_tournament_holdout_scores_v3.jsonl",
    "dopey/signal_research_v3/research_tournament_regime_scores_v3.jsonl",
    "dopey/signal_research_v3/research_tournament_v3_summary.json",
    "dopey/signal_research_v3/research_breakthrough_rejections_v3.jsonl",
    "dopey/signal_research_v3/research_watchlist_candidates_v3.jsonl",
    "dopey/signal_research_v3/stable_family_template_repair_v3_summary.json",
    "dopey/signal_research_v4/public_signal_research_breakthrough_v4_summary.json",
    "dopey/signal_research_v4/research_breakthrough_gate_v4_summary.json",
    "dopey/signal_research_v4/research_mutation_queue_v4_summary.json",
    "dopey/signal_research_v4/research_tournament_v4_summary.json",
    "dopey/scoreboard/public_signal_research_scoreboard_v4.json",
    "dopey/live_gate/public_signal_research_live_gate_status_v4.json",
    "dopey/signal_research_v5/public_signal_research_breakthrough_v5_timeout_records.jsonl",
    "dopey/signal_research_v5/public_signal_research_breakthrough_v5_validation_summary.json",
    "dopey/signal_research_v5/public_signal_research_expensive_lane_summary_v5.json",
    "dopey/signal_research_v5/research_breakthrough_gate_v5_summary.json",
    "dopey/signal_research_v5/research_mutation_queue_v5.jsonl",
    "dopey/signal_research_v5/research_mutation_queue_v5_summary.json",
    "dopey/signal_research_v5/research_watchlist_candidates_v5.jsonl",
    "dopey/scoreboard/public_signal_research_scoreboard_v5.json",
    "dopey/live_gate/public_signal_research_live_gate_status_v5.json",
    "dopey/signal_research_v6/public_signal_research_breakthrough_v6_timeout_records.jsonl",
    "dopey/signal_research_v6/public_signal_research_breakthrough_v6_validation_summary.json",
    "dopey/signal_research_v6/research_breakthrough_gate_v6_summary.json",
    "dopey/signal_research_v6/research_mutation_queue_v6.jsonl",
    "dopey/signal_research_v6/research_mutation_queue_v6_summary.json",
    "dopey/signal_research_v6/research_watchlist_candidates_v6.jsonl",
    "dopey/scoreboard/public_signal_research_scoreboard_v6.json",
    "dopey/live_gate/public_signal_research_live_gate_status_v6.json",
)

SEED_SOURCES: tuple[SeedSource, ...] = BASE_SEED_SOURCES + tuple(
    _full_file_source(relative_path) for relative_path in CHECKPOINT_RELATIVE_PATHS
) + (
    {
        "relative_path": "dopey/signal_research_v3/research_no_trade_filter_records_v3.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/signal_research_v3/research_signal_candidates_v3.jsonl",
        "mode": "latest_jsonl_record",
    },
    {
        "relative_path": "dopey/signal_research_v4/public_signal_research_breakthrough_v4_validation_summary.json",
        "mode": "sanitized_json",
    },
    {
        "relative_path": "dopey/signal_research_v5/public_signal_research_breakthrough_v5_summary.json",
        "mode": "sanitized_json",
    },
    {
        "relative_path": "dopey/signal_research_v6/public_signal_research_breakthrough_v6_summary.json",
        "mode": "sanitized_json",
    },
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_json_object(payload: bytes, source: Path) -> None:
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"test artifact seed source must contain a JSON object: source={source}")


def _validate_record_safety(value: object, source: Path) -> None:
    if isinstance(value, dict):
        for field_name, expected_value in SEALED_BOOLEAN_FIELDS.items():
            if field_name in value and value[field_name] is not expected_value:
                raise ValueError(
                    "test artifact seed source violates a sealed research-only field: "
                    f"source={source}, field={field_name}, expected={expected_value}, actual={value[field_name]}"
                )
        for nested_value in value.values():
            _validate_record_safety(nested_value, source)
        return
    if isinstance(value, list):
        for nested_value in value:
            _validate_record_safety(nested_value, source)


def _validate_seed_payload(payload: bytes, source: Path) -> None:
    text = payload.decode("utf-8-sig")
    normalized = text.lower()
    for token in PROHIBITED_WORKSTATION_TOKENS:
        if token in normalized:
            raise ValueError(
                "test artifact seed source contains a workstation-specific path: "
                f"source={source}, token={token}"
            )
    if source.suffix == ".json":
        _validate_record_safety(json.loads(text), source)
        return
    if source.suffix == ".jsonl":
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "test artifact seed source contains invalid JSONL: "
                    f"source={source}, line={line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise TypeError(
                    "test artifact seed JSONL record must be an object: "
                    f"source={source}, line={line_number}"
                )
            _validate_record_safety(record, source)


def _read_stable_file(source: Path) -> bytes:
    before = source.stat()
    payload = source.read_bytes()
    after = source.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RuntimeError(f"test artifact seed source changed while it was read: source={source}")
    return payload


def _read_latest_jsonl_record(source: Path) -> bytes:
    before = source.stat()
    latest = b""
    with source.open("rb") as handle:
        for line in handle:
            if line.strip():
                latest = line.rstrip(b"\r\n")
    after = source.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RuntimeError(f"test artifact JSONL source changed while it was read: source={source}")
    if not latest:
        raise ValueError(f"test artifact JSONL source has no records: source={source}")
    _require_json_object(latest, source)
    return latest + b"\n"


def _read_sanitized_json(source: Path) -> bytes:
    source_payload = _read_stable_file(source)
    value = json.loads(source_payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"sanitized checkpoint source must be a JSON object: source={source}")
    fields = SANITIZED_JSON_FIELDS.get(source.name)
    if fields is None:
        raise ValueError(f"sanitized checkpoint source has no declared field policy: source={source}")
    sanitized = dict(value)
    for field_name in fields:
        if field_name not in sanitized:
            raise ValueError(
                "sanitized checkpoint source is missing a declared workstation field: "
                f"source={source}, field={field_name}"
            )
        del sanitized[field_name]
    sanitized["fixture_only"] = True
    sanitized["not_forward_evidence"] = True
    sanitized["sanitized_fields"] = list(fields)
    sanitized.pop("summary_hash", None)
    unsigned = json.dumps(sanitized, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    sanitized["summary_hash"] = _sha256(unsigned)
    return json.dumps(sanitized, sort_keys=True, ensure_ascii=True, indent=2).encode("utf-8") + b"\n"


def _source_payload(source: Path, mode: str) -> bytes:
    if not source.exists():
        raise FileNotFoundError(f"test artifact seed source is missing: source={source}")
    if mode == "full_file":
        payload = _read_stable_file(source)
        if source.suffix == ".json":
            _require_json_object(payload, source)
        _validate_seed_payload(payload, source)
        return payload
    if mode == "latest_jsonl_record":
        payload = _read_latest_jsonl_record(source)
        _validate_seed_payload(payload, source)
        return payload
    if mode == "sanitized_json":
        payload = _read_sanitized_json(source)
        _validate_seed_payload(payload, source)
        return payload
    raise ValueError(f"test artifact seed source mode is unsupported: source={source}, mode={mode}")


def _archive_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_test_artifact_seed(source_artifact_root: Path) -> dict[str, Any]:
    payloads: dict[str, bytes] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for spec in sorted(SEED_SOURCES, key=lambda value: value["relative_path"]):
        relative = spec["relative_path"]
        source = source_artifact_root / Path(relative)
        payload = _source_payload(source, spec["mode"])
        archive_name = f"artifacts/{relative}"
        payloads[archive_name] = payload
        metadata[archive_name] = {
            "bytes": len(payload),
            "sha256": _sha256(payload),
            "source_mode": spec["mode"],
            "source_relative_path": f"artifacts/{relative}",
        }

    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_archive = ARCHIVE_PATH.with_suffix(f"{ARCHIVE_PATH.suffix}.tmp")
    with zipfile.ZipFile(
        temporary_archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for name in sorted(payloads):
            archive.writestr(_archive_info(name), payloads[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    os.replace(temporary_archive, ARCHIVE_PATH)

    archive_payload = ARCHIVE_PATH.read_bytes()
    manifest: dict[str, Any] = {
        "seed_version": SEED_VERSION,
        "artifact_count": len(metadata),
        "archive_path": "tests/fixtures/runtime_artifact_seed_v1.zip",
        "archive_bytes": len(archive_payload),
        "archive_sha256": _sha256(archive_payload),
        "files": metadata,
        "evidence_policy": (
            "derived paper-research outputs from historical public-market observations are preserved only "
            "as isolated integration-test inputs; they are not current state or forward evidence"
        ),
        "derived_historical_public_market_test_fixture": True,
        "raw_provider_market_data_included": False,
        "broker_account_or_order_history_included": False,
        "operational_runtime_state": False,
        "paper_only": True,
        "live_blocked": True,
    }
    temporary_manifest = MANIFEST_PATH.with_suffix(f"{MANIFEST_PATH.suffix}.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_manifest, MANIFEST_PATH)
    return manifest


def verify_test_artifact_seed() -> dict[str, Any]:
    if not MANIFEST_PATH.exists() or not ARCHIVE_PATH.exists():
        raise FileNotFoundError(
            "test artifact seed requires both archive and manifest: "
            f"archive={ARCHIVE_PATH}, manifest={MANIFEST_PATH}"
        )
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"test artifact seed manifest must be an object: path={MANIFEST_PATH}")
    if value.get("seed_version") != SEED_VERSION:
        raise ValueError(
            "test artifact seed version mismatch: "
            f"expected={SEED_VERSION}, actual={value.get('seed_version')}"
        )
    if value.get("paper_only") is not True or value.get("live_blocked") is not True:
        raise ValueError(f"test artifact seed violates the research-only boundary: path={MANIFEST_PATH}")
    expected_boundary = {
        "derived_historical_public_market_test_fixture": True,
        "raw_provider_market_data_included": False,
        "broker_account_or_order_history_included": False,
        "operational_runtime_state": False,
    }
    boundary_mismatches = {
        field_name: {"expected": expected_value, "actual": value.get(field_name)}
        for field_name, expected_value in expected_boundary.items()
        if value.get(field_name) is not expected_value
    }
    if boundary_mismatches:
        raise ValueError(
            "test artifact seed boundary metadata is invalid: "
            f"path={MANIFEST_PATH}, mismatches={boundary_mismatches}"
        )
    archive_payload = ARCHIVE_PATH.read_bytes()
    actual_archive_hash = _sha256(archive_payload)
    expected_archive_hash = str(value.get("archive_sha256", ""))
    if actual_archive_hash != expected_archive_hash:
        raise ValueError(
            "test artifact seed archive hash mismatch: "
            f"expected={expected_archive_hash}, actual={actual_archive_hash}, path={ARCHIVE_PATH}"
        )
    files = value.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"test artifact seed manifest files map is empty: path={MANIFEST_PATH}")
    expected_names = set(str(name) for name in files)
    with zipfile.ZipFile(ARCHIVE_PATH, "r") as archive:
        archive_names = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
        if archive_names != expected_names:
            raise ValueError(
                "test artifact seed archive entries differ from the manifest: "
                f"missing={sorted(expected_names - archive_names)}, extra={sorted(archive_names - expected_names)}"
            )
        for name in sorted(archive_names):
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "artifacts":
                raise ValueError(f"test artifact seed contains an unsafe archive path: name={name}")
            metadata = files[name]
            if not isinstance(metadata, dict):
                raise TypeError(f"test artifact seed metadata must be an object: name={name}")
            payload = archive.read(name)
            _validate_seed_payload(payload, Path(name))
            actual_hash = _sha256(payload)
            expected_hash = str(metadata.get("sha256", ""))
            if actual_hash != expected_hash or len(payload) != int(metadata.get("bytes", -1)):
                raise ValueError(
                    "test artifact seed entry identity mismatch: "
                    f"name={name}, expected_hash={expected_hash}, actual_hash={actual_hash}, "
                    f"expected_bytes={metadata.get('bytes')}, actual_bytes={len(payload)}"
                )
    if int(value.get("artifact_count", -1)) != len(expected_names):
        raise ValueError(
            "test artifact seed artifact count mismatch: "
            f"manifest_count={value.get('artifact_count')}, actual_count={len(expected_names)}"
        )
    return value


def main(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--source-repository-root", type=Path)
    parsed = parser.parse_args(arguments)
    source_repository_root = parsed.source_repository_root or REPOSITORY_ROOT
    manifest = (
        verify_test_artifact_seed()
        if parsed.verify_only
        else build_test_artifact_seed(source_repository_root / "artifacts")
    )
    print(json.dumps(manifest, sort_keys=True, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
