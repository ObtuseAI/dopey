"""Local-only staging folder and manifest contracts for manually acquired data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ingestion_plan_models import DATA_INGESTION_PLAN_VERSION, LocalStagingContract


REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_DATA_ROOT = REPO_ROOT / "dopey_data" / "real"
RAW_ROOT = REAL_DATA_ROOT / "raw"
MANIFEST_DIR = REAL_DATA_ROOT / "manifests"
VALIDATED_DIR = REAL_DATA_ROOT / "validated"
TEMPLATE_DIR = REAL_DATA_ROOT / "templates"
REAL_DATA_MANIFEST_PATH = MANIFEST_DIR / "real_data_manifest.json"
REAL_DATA_MANIFEST_TEMPLATE_PATH = MANIFEST_DIR / "real_data_manifest.template.json"

RAW_FOLDER_CONTRACTS: dict[str, str] = {
    "daily_ohlcv": "dopey_data/real/raw/daily_ohlcv/",
    "corporate_actions": "dopey_data/real/raw/corporate_actions/",
    "historical_options_chain": "dopey_data/real/raw/options_chain/",
    "historical_options_quotes": "dopey_data/real/raw/options_quotes/",
    "fundamentals": "dopey_data/real/raw/fundamentals/",
    "earnings_calendar": "dopey_data/real/raw/earnings_calendar/",
    "market_context": "dopey_data/real/raw/market_context/",
    "benchmark_and_universe_metadata": "dopey_data/real/raw/universe_metadata/",
}
REQUIRED_MANIFEST_FIELDS: list[str] = [
    "manifest_id",
    "created_at",
    "dataset_family",
    "provider_name",
    "provider_terms_reviewed",
    "license_status",
    "redistribution_allowed",
    "local_file_paths",
    "file_hashes",
    "row_counts",
    "symbol_counts",
    "date_ranges",
    "schema_version",
    "ingested_by",
    "manual_operator_note",
    "not_broker_data",
    "not_credentials",
    "not_live_data",
    "not_network_fetched_by_dopey",
    "paper_only",
    "live_blocked",
]


def build_local_staging_contract(create_folders: bool) -> LocalStagingContract:
    if create_folders:
        create_local_staging_folders()
        write_manifest_template()
    return LocalStagingContract(
        artifact_type="local_staging_contract",
        ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
        contract_id="dopey-real-data-local-staging-contract-v1",
        raw_folder_contracts=RAW_FOLDER_CONTRACTS,
        manifest_path="dopey_data/real/manifests/real_data_manifest.json",
        validated_folder="dopey_data/real/validated/",
        template_folder="dopey_data/real/templates/",
        required_manifest_fields=REQUIRED_MANIFEST_FIELDS,
        folder_contracts_created=create_folders,
        sample_manifest_template_created=create_folders,
        real_data_files_present=real_data_files_present(),
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        staging_hash="",
    )


def create_local_staging_folders() -> None:
    for relative_path in RAW_FOLDER_CONTRACTS.values():
        (REPO_ROOT / relative_path).mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATED_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


def write_manifest_template() -> Path:
    record = manifest_template_record()
    REAL_DATA_MANIFEST_TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REAL_DATA_MANIFEST_TEMPLATE_PATH.write_text(
        json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return REAL_DATA_MANIFEST_TEMPLATE_PATH


def manifest_template_record() -> dict[str, Any]:
    return {
        "manifest_id": "TEMPLATE_ONLY_NOT_REAL_DATA",
        "created_at": "TEMPLATE_ONLY",
        "dataset_family": "TEMPLATE_ONLY",
        "provider_name": "TEMPLATE_ONLY",
        "provider_terms_reviewed": False,
        "license_status": "unknown",
        "redistribution_allowed": False,
        "local_file_paths": [],
        "file_hashes": {},
        "row_counts": {},
        "symbol_counts": {},
        "date_ranges": {},
        "schema_version": "dopey-real-data-schema-template-v1",
        "ingested_by": "manual_operator_required",
        "manual_operator_note": "Template only. This is not evidence and not ingested data.",
        "not_broker_data": True,
        "not_credentials": True,
        "not_live_data": True,
        "not_network_fetched_by_dopey": True,
        "paper_only": True,
        "live_blocked": True,
        "template_only": True,
        "sample_only": True,
        "not_real_data": True,
        "real_data_ingested": False,
    }


def real_data_files_present() -> bool:
    for relative_path in RAW_FOLDER_CONTRACTS.values():
        folder = REPO_ROOT / relative_path
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                return True
    return False


def local_staging_contract_record(create_folders: bool) -> dict[str, Any]:
    return build_local_staging_contract(create_folders).to_dict()
