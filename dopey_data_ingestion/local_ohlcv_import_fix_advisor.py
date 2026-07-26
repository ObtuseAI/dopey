"""Actionable local OHLCV import fix advice without importing real data."""
from __future__ import annotations

from typing import Any

from .local_ohlcv_import_models import LOCAL_OHLCV_IMPORT_VERSION, LocalOhlcvImportFixAdvice


def build_local_ohlcv_fix_advice(validation_result: dict[str, Any]) -> dict[str, Any]:
    decision = validation_result["decision"]
    status = str(decision["local_ohlcv_status"])
    import_decision = str(decision["local_ohlcv_import_decision"])
    groups = {
        "schema_errors": _schema_advice(validation_result["schema_results"]),
        "quality_errors": _quality_advice(validation_result["quality_results"]),
        "license_provenance_errors": _license_advice(validation_result["license_provenance_results"]),
        "sample_template_contamination": _sample_advice(validation_result["quality_results"]),
        "credential_token_contamination": _credential_advice(validation_result["quality_results"]),
        "manifest_hash_errors": _manifest_hash_advice(validation_result["license_provenance_results"]),
    }
    if status == "missing_local_ohlcv_files":
        advice_status = "manual_staging_required"
        groups["manual_staging_required"] = [
            "Stage operator-supplied licensed OHLCV CSV or JSONL under dopey_data/real/raw/daily_ohlcv/ or market_context/.",
            "Fill dopey_data/real/manifests/real_data_manifest.json with source, license, provenance, row counts, symbol counts, date ranges, and sha256 hashes.",
            "Mark uncertain license or provenance as manual_review_required; do not treat free data as evidence without review.",
        ]
    elif status == "local_ohlcv_validation_pass":
        advice_status = "no_fix_required"
    elif status == "terminal_block":
        advice_status = "terminal_block_fix_required"
    else:
        advice_status = "manual_review_or_fix_required"
    return LocalOhlcvImportFixAdvice(
        artifact_type="local_ohlcv_import_fix_advice",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        local_ohlcv_status=status,
        local_ohlcv_import_decision=import_decision,
        fix_advice_status=advice_status,
        advice_groups=groups,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        advice_hash="",
    ).to_dict()


def _schema_advice(records: list[dict[str, Any]]) -> list[str]:
    missing = sorted({column for record in records for column in record.get("missing_columns", [])})
    malformed = any(int(record.get("malformed_rows", 0)) > 0 for record in records)
    messages = [f"Add required column `{column}` to the staged file." for column in missing]
    if malformed:
        messages.append("Fix malformed CSV/JSONL rows before retrying validation.")
    return messages


def _quality_advice(records: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for record in records:
        if not record.get("positive_ohlc", True):
            messages.append("Fix nonpositive open/high/low/close values.")
        if not record.get("high_low_consistent", True):
            messages.append("Fix rows where high/low are inconsistent with open/close.")
        if not record.get("adjusted_close_positive", True):
            messages.append("Fix missing or nonpositive adjusted_close values.")
        if not record.get("volume_nonnegative", True):
            messages.append("Fix negative volume values.")
        if int(record.get("duplicate_symbol_date_count", 0)) > 0:
            messages.append("Remove duplicate date/symbol rows.")
        if int(record.get("future_date_count", 0)) > 0:
            messages.append("Remove future-dated rows.")
        if int(record.get("source_field_missing_count", 0)) > 0:
            messages.append("Record source in the file or manifest.")
    return sorted(set(messages))


def _license_advice(records: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for record in records:
        if record.get("status") == "blocked_missing_manifest":
            messages.append("Create a non-template real_data_manifest.json after staging local files.")
        if not record.get("provider_name_present", False):
            messages.append("Record provider_name in real_data_manifest.json.")
        if not record.get("source_present", False):
            messages.append("Record source/provenance in real_data_manifest.json.")
        if not record.get("license_status_accepted", False):
            messages.append("Use a reviewed license_status that permits internal research use.")
        if not record.get("provider_terms_reviewed", False):
            messages.append("Set provider_terms_reviewed=true only after manual terms review.")
        for missing in record.get("manifest_missing_required_fields", []):
            messages.append(f"Add required manifest field `{missing}`.")
    return sorted(set(messages))


def _sample_advice(records: list[dict[str, Any]]) -> list[str]:
    contaminated = any(
        int(record.get("sample_only_row_count", 0)) > 0
        or int(record.get("fake_symbol_count", 0)) > 0
        or int(record.get("not_real_data_row_count", 0)) > 0
        for record in records
    )
    return ["Remove sample_only, not_real_data, and SAMPLE_ONLY rows from real raw folders."] if contaminated else []


def _credential_advice(records: list[dict[str, Any]]) -> list[str]:
    contaminated = any(record.get("credential_token_found", False) or record.get("broker_live_order_scheduler_real_sizing_found", False) for record in records)
    return ["Remove credentials, API keys, tokens, broker/live/order/scheduler, and real-sizing markers from staged files."] if contaminated else []


def _manifest_hash_advice(records: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for record in records:
        if not record.get("file_hash_recorded", False):
            messages.append("Record each staged file sha256 in real_data_manifest.json file_hashes.")
        if record.get("file_hash_recorded", False) and not record.get("file_hash_matches_manifest", False):
            messages.append("Resolve manifest/file sha256 mismatch before retrying.")
        if record.get("manifest_template_only", False):
            messages.append("Replace template-only manifest values with reviewed source, license, and provenance details.")
    return sorted(set(messages))
