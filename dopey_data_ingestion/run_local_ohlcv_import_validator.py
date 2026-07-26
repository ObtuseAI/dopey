"""CLI artifact writer for the local OHLCV import validator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_ohlcv_import_fix_advisor import build_local_ohlcv_fix_advice
from .local_ohlcv_import_validator import required_manifest_template_fields, validate_local_ohlcv_import
from .local_staging_contract import REPO_ROOT
from .manual_ohlcv_import_fix_engine import write_manual_ohlcv_import_fix_plan


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "local_ohlcv_import"
LOCAL_OHLCV_IMPORT_INPUT_PATH = ARTIFACT_DIR / "local_ohlcv_import_input.json"
LOCAL_OHLCV_FILE_INVENTORY_PATH = ARTIFACT_DIR / "local_ohlcv_file_inventory.jsonl"
LOCAL_OHLCV_SCHEMA_RESULTS_PATH = ARTIFACT_DIR / "local_ohlcv_schema_results.jsonl"
LOCAL_OHLCV_QUALITY_RESULTS_PATH = ARTIFACT_DIR / "local_ohlcv_quality_results.jsonl"
LOCAL_OHLCV_LICENSE_PROVENANCE_RESULTS_PATH = ARTIFACT_DIR / "local_ohlcv_license_provenance_results.jsonl"
LOCAL_OHLCV_IMPORT_DECISION_PATH = ARTIFACT_DIR / "local_ohlcv_import_decision.json"
LOCAL_OHLCV_IMPORT_SUMMARY_PATH = ARTIFACT_DIR / "local_ohlcv_import_summary.json"
LOCAL_OHLCV_IMPORT_PROOF_PATH = ARTIFACT_DIR / "local_ohlcv_import_proof.jsonl"
LOCAL_OHLCV_IMPORT_FIX_ADVICE_PATH = ARTIFACT_DIR / "local_ohlcv_import_fix_advice.json"
MANIFEST_TEMPLATE_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "real_data_manifest.template.json"


def run_local_ohlcv_import_validator() -> dict[str, Any]:
    _write_manifest_template()
    result = validate_local_ohlcv_import()
    fix_advice = build_local_ohlcv_fix_advice(result)
    _write_json(LOCAL_OHLCV_IMPORT_INPUT_PATH, result["input"])
    _write_jsonl(LOCAL_OHLCV_FILE_INVENTORY_PATH, result["inventory"])
    _write_jsonl(LOCAL_OHLCV_SCHEMA_RESULTS_PATH, result["schema_results"])
    _write_jsonl(LOCAL_OHLCV_QUALITY_RESULTS_PATH, result["quality_results"])
    _write_jsonl(LOCAL_OHLCV_LICENSE_PROVENANCE_RESULTS_PATH, result["license_provenance_results"])
    _write_json(LOCAL_OHLCV_IMPORT_DECISION_PATH, result["decision"])
    _write_json(LOCAL_OHLCV_IMPORT_FIX_ADVICE_PATH, fix_advice)
    _write_json(LOCAL_OHLCV_IMPORT_SUMMARY_PATH, {**result["summary"], "fix_advice_status": fix_advice["fix_advice_status"], "artifact_paths": artifact_paths()})
    _write_jsonl(LOCAL_OHLCV_IMPORT_PROOF_PATH, result["proof"])
    write_manual_ohlcv_import_fix_plan()
    return {**result["summary"], "fix_advice_status": fix_advice["fix_advice_status"], "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "local_ohlcv_import_input": str(LOCAL_OHLCV_IMPORT_INPUT_PATH),
        "local_ohlcv_file_inventory": str(LOCAL_OHLCV_FILE_INVENTORY_PATH),
        "local_ohlcv_schema_results": str(LOCAL_OHLCV_SCHEMA_RESULTS_PATH),
        "local_ohlcv_quality_results": str(LOCAL_OHLCV_QUALITY_RESULTS_PATH),
        "local_ohlcv_license_provenance_results": str(LOCAL_OHLCV_LICENSE_PROVENANCE_RESULTS_PATH),
        "local_ohlcv_import_decision": str(LOCAL_OHLCV_IMPORT_DECISION_PATH),
        "local_ohlcv_import_summary": str(LOCAL_OHLCV_IMPORT_SUMMARY_PATH),
        "local_ohlcv_import_fix_advice": str(LOCAL_OHLCV_IMPORT_FIX_ADVICE_PATH),
        "local_ohlcv_import_proof": str(LOCAL_OHLCV_IMPORT_PROOF_PATH),
    }


def _write_manifest_template() -> Path:
    record = {
        "manifest_id": "OPERATOR_FILLED_REAL_DATA_MANIFEST",
        "created_at": "REQUIRED_ISO_8601",
        "dataset_family": "daily_ohlcv",
        "provider_name": "REQUIRED_LICENSED_PROVIDER_NAME",
        "provider_terms_reviewed": False,
        "license_status": "unknown",
        "redistribution_allowed": False,
        "local_file_paths": [],
        "file_hashes": {},
        "row_counts": {},
        "symbol_counts": {},
        "date_ranges": {},
        "schema_version": "dopey-real-data-schema-contract-v1",
        "ingested_by": "manual_operator",
        "manual_operator_note": "Fill this template only after manually staging licensed local files. Do not include credentials.",
        "source": "REQUIRED_SOURCE_OR_EXPORT_NAME",
        "source_url_or_name": "REQUIRED_OPERATOR_RECORDED_SOURCE_WITHOUT_CREDENTIALS",
        "manual_download_date": "REQUIRED_IF_OPERATOR_DOWNLOADED",
        "free_public_data_candidate": False,
        "redistribution_status_review_note": "Record uncertainty as manual_review_required.",
        "commercial_use_status_review_note": "Record uncertainty as manual_review_required.",
        "provenance_review_status": "manual_review_required",
        "not_broker_data": True,
        "not_credentials": True,
        "not_live_data": True,
        "not_network_fetched_by_dopey": True,
        "paper_only": True,
        "live_blocked": True,
        "required_fields": required_manifest_template_fields(),
    }
    MANIFEST_TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_TEMPLATE_PATH.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return MANIFEST_TEMPLATE_PATH


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_local_ohlcv_import_validator()
    print(json.dumps({
        "local_ohlcv_status": result["local_ohlcv_status"],
        "valid_real_dataset": result["valid_real_dataset"],
        "real_data_imported": result["real_data_imported"],
        "history_spine_upgrade_allowed": result["history_spine_upgrade_allowed"],
        "summary_path": str(LOCAL_OHLCV_IMPORT_SUMMARY_PATH),
        "fix_advice_status": result["fix_advice_status"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
