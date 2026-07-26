"""Generate draft manifest records from local staged files only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_ohlcv_file_inventory import (
    dataset_family_for_path,
    list_staged_local_ohlcv_paths,
    parse_date,
    read_local_ohlcv_file,
    repo_relative_path,
    sha256_file,
)
from .local_ohlcv_license_provenance_validator import required_manifest_template_fields
from .local_staging_contract import REPO_ROOT
from .manual_ohlcv_staging_models import (
    MANUAL_OHLCV_STAGING_VERSION,
    ManualOhlcvHashRecord,
    ManualOhlcvManifestDraft,
    stable_manual_ohlcv_hash,
)


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "manual_ohlcv_staging"
MANIFEST_DIR = REPO_ROOT / "dopey_data" / "real" / "manifests"
MANUAL_OHLCV_HASH_RECORDS_PATH = ARTIFACT_DIR / "manual_ohlcv_hash_records.jsonl"
MANUAL_OHLCV_MANIFEST_DRAFT_PATH = ARTIFACT_DIR / "manual_ohlcv_manifest_draft.json"
LOCAL_REAL_DATA_MANIFEST_DRAFT_PATH = MANIFEST_DIR / "real_data_manifest.draft.json"
LOCAL_REAL_DATA_MANIFEST_PATH = MANIFEST_DIR / "real_data_manifest.json"


def build_manual_ohlcv_manifest_draft() -> dict[str, Any]:
    paths = list_staged_local_ohlcv_paths()
    hash_records = [build_hash_record(path).to_dict() for path in paths]
    local_paths = [record["local_file_path"] for record in hash_records]
    status = "manual_staging_required" if not hash_records else "manifest_draft_ready"
    draft = ManualOhlcvManifestDraft(
        artifact_type="manual_ohlcv_manifest_draft",
        staging_version=MANUAL_OHLCV_STAGING_VERSION,
        draft_id="manual-ohlcv-manifest-draft-v1",
        draft_status=status,
        real_data_files_present=bool(hash_records),
        hash_record_count=len(hash_records),
        provider_terms_reviewed=False,
        license_status="unknown",
        redistribution_allowed=False,
        local_file_paths=local_paths,
        file_hashes={record["local_file_path"]: record["sha256"] for record in hash_records},
        row_counts={record["local_file_path"]: int(record["row_count"]) for record in hash_records},
        symbol_counts={record["local_file_path"]: int(record["symbol_count"]) for record in hash_records},
        date_ranges={record["local_file_path"]: record["date_range"] for record in hash_records},
        operator_required_fields=_operator_required_fields(),
        manifest_draft_is_import_approval=False,
        manifest_draft_is_evidence=False,
        not_broker_data=True,
        not_credentials=True,
        not_live_data=True,
        not_network_fetched_by_dopey=True,
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        not_strategy_promotion=True,
        draft_hash="",
    ).to_dict()
    manifest_payload = {
        **draft,
        "manifest_id": "DRAFT_OPERATOR_MUST_COMPLETE_NOT_EVIDENCE",
        "created_at": "DRAFT_OPERATOR_MUST_FILL_ISO_8601",
        "dataset_family": "manual_local_ohlcv_staging",
        "provider_name": "OPERATOR_MUST_FILL_REVIEWED_PROVIDER",
        "schema_version": "dopey-real-data-schema-contract-v1",
        "ingested_by": "manual_operator",
        "manual_operator_note": "Draft generated from local files only. This is not import approval and not evidence.",
        "source_urls_or_reference_names": [],
        "download_or_export_dates": {},
        "final_manifest_required_path": "dopey_data/real/manifests/real_data_manifest.json",
    }
    manifest_payload["draft_manifest_hash"] = stable_manual_ohlcv_hash(manifest_payload)
    return {"draft": draft, "hash_records": hash_records, "manifest_payload": manifest_payload}


def build_hash_record(path: Path) -> ManualOhlcvHashRecord:
    dataset_family = dataset_family_for_path(path)
    parsed = read_local_ohlcv_file(path, dataset_family)
    dates = sorted(
        parsed_date.isoformat()
        for parsed_date in (parse_date(row.get("date", "")) for row in parsed.rows)
        if parsed_date is not None
    )
    symbols = sorted({row.get("symbol", "").strip().upper() for row in parsed.rows if row.get("symbol", "").strip()})
    sources = sorted({row.get("source", "").strip() for row in parsed.rows if row.get("source", "").strip()})
    relative = repo_relative_path(path)
    return ManualOhlcvHashRecord(
        artifact_type="manual_ohlcv_hash_records",
        staging_version=MANUAL_OHLCV_STAGING_VERSION,
        file_id=f"manual-hash-{stable_manual_ohlcv_hash({'path': relative, 'sha256': sha256_file(path)})[:12]}",
        local_file_path=relative,
        dataset_family=dataset_family,
        file_extension=path.suffix.lower(),
        byte_size=path.stat().st_size,
        sha256=sha256_file(path),
        row_count=len(parsed.rows),
        symbol_count=len(symbols),
        date_range={"start": dates[0], "end": dates[-1]} if dates else {},
        source_values=sources,
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        not_strategy_promotion=True,
        hash_record_hash="",
    )


def write_manual_ohlcv_manifest_draft() -> dict[str, Any]:
    result = build_manual_ohlcv_manifest_draft()
    _write_jsonl(MANUAL_OHLCV_HASH_RECORDS_PATH, result["hash_records"])
    _write_json(MANUAL_OHLCV_MANIFEST_DRAFT_PATH, result["manifest_payload"])
    _write_json(LOCAL_REAL_DATA_MANIFEST_DRAFT_PATH, result["manifest_payload"])
    return {
        **result["draft"],
        "artifact_paths": {
            "manual_ohlcv_hash_records": str(MANUAL_OHLCV_HASH_RECORDS_PATH),
            "manual_ohlcv_manifest_draft": str(MANUAL_OHLCV_MANIFEST_DRAFT_PATH),
            "local_real_data_manifest_draft": str(LOCAL_REAL_DATA_MANIFEST_DRAFT_PATH),
            "final_manifest_preserved": str(LOCAL_REAL_DATA_MANIFEST_PATH),
        },
    }


def _operator_required_fields() -> list[str]:
    return [
        *required_manifest_template_fields(),
        "source_urls_or_reference_names",
        "download_or_export_dates",
    ]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
