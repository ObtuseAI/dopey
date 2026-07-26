"""Validate manually staged local OHLCV files without importing them."""
from __future__ import annotations

from typing import Any

from .local_ohlcv_file_inventory import load_manifest_record, read_staged_local_ohlcv_files, sample_row_is_blocked
from .local_ohlcv_import_decision import build_local_ohlcv_import_summary, decide_local_ohlcv_import
from .local_ohlcv_import_models import LOCAL_OHLCV_IMPORT_VERSION, LocalOhlcvImportInput, LocalOhlcvImportProofRecord
from .local_ohlcv_license_provenance_validator import required_manifest_template_fields, validate_license_provenance_records
from .local_ohlcv_quality_validator import validate_quality_records
from .local_ohlcv_schema_validator import validate_schema_records
from .local_staging_contract import REPO_ROOT


DAILY_OHLCV_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "daily_ohlcv"
MARKET_CONTEXT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "market_context"
CORPORATE_ACTIONS_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "corporate_actions"
REAL_DATA_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "real_data_manifest.json"


def validate_local_ohlcv_import() -> dict[str, Any]:
    input_record = _input_record().to_dict()
    parsed_files = read_staged_local_ohlcv_files()
    manifest = load_manifest_record(REAL_DATA_MANIFEST_PATH)
    inventory = _inventory_records(parsed_files, manifest)
    schema_results = validate_schema_records(parsed_files)
    quality_results = validate_quality_records(parsed_files, manifest)
    license_results = validate_license_provenance_records(parsed_files)
    decision = decide_local_ohlcv_import(inventory, schema_results, quality_results, license_results).to_dict()
    summary = build_local_ohlcv_import_summary(input_record, inventory, schema_results, quality_results, license_results, decision)
    proof = [_proof(decision).to_dict()]
    return {
        "input": input_record,
        "inventory": inventory,
        "schema_results": schema_results,
        "quality_results": quality_results,
        "license_provenance_results": license_results,
        "decision": decision,
        "summary": summary,
        "proof": proof,
    }


def _schema_result(path: Any, dataset_family: str, rows: list[dict[str, str]]) -> Any:
    from pathlib import Path

    from .local_ohlcv_file_inventory import LocalOhlcvParsedFile
    from .local_ohlcv_schema_validator import validate_parsed_schema

    target = Path(path)
    text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    headers = list(rows[0].keys()) if rows else []
    parsed = LocalOhlcvParsedFile(path=target, dataset_family=dataset_family, rows=rows, header_columns=headers, malformed_rows=0, text=text)
    return validate_parsed_schema(parsed)


def _quality_result(path: Any, dataset_family: str, rows: list[dict[str, str]]) -> Any:
    from pathlib import Path

    from .local_ohlcv_file_inventory import LocalOhlcvParsedFile
    from .local_ohlcv_quality_validator import validate_parsed_quality

    target = Path(path)
    text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    headers = list(rows[0].keys()) if rows else []
    parsed = LocalOhlcvParsedFile(path=target, dataset_family=dataset_family, rows=rows, header_columns=headers, malformed_rows=0, text=text)
    return validate_parsed_quality(parsed, {})


def _input_record() -> LocalOhlcvImportInput:
    return LocalOhlcvImportInput(
        artifact_type="local_ohlcv_import_input",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        input_id="local-ohlcv-import-input-v1",
        daily_ohlcv_folder="dopey_data/real/raw/daily_ohlcv/",
        market_context_folder="dopey_data/real/raw/market_context/",
        corporate_actions_folder="dopey_data/real/raw/corporate_actions/",
        manifest_path="dopey_data/real/manifests/real_data_manifest.json",
        network_fetch_performed=False,
        broker_connection_used=False,
        credentials_created=False,
        env_created=False,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        input_hash="",
    )


def _inventory_records(parsed_files: list[Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    from .local_ohlcv_file_inventory import build_inventory_records

    return [record.to_dict() for record in build_inventory_records(manifest)] if parsed_files else []


def _proof(decision: dict[str, Any]) -> LocalOhlcvImportProofRecord:
    return LocalOhlcvImportProofRecord(
        artifact_type="local_ohlcv_import_proof",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        proof_id="local-ohlcv-import-proof-v1",
        local_ohlcv_status=str(decision["local_ohlcv_status"]),
        valid_real_dataset=bool(decision["valid_real_dataset"]),
        real_data_imported=False,
        history_spine_upgrade_allowed=bool(decision["history_spine_upgrade_allowed"]),
        network_fetch_performed=False,
        broker_connection_used=False,
        credentials_created=False,
        env_created=False,
        no_scheduler=True,
        no_real_sizing=True,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        proof_hash="",
    )
