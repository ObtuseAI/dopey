"""Combine local OHLCV validation evidence into an import decision."""
from __future__ import annotations

from typing import Any

from .local_ohlcv_import_models import LOCAL_OHLCV_IMPORT_VERSION, LocalOhlcvImportDecision, stable_local_ohlcv_hash


def decide_local_ohlcv_import(
    inventory_records: list[dict[str, Any]],
    schema_results: list[dict[str, Any]],
    quality_results: list[dict[str, Any]],
    license_provenance_results: list[dict[str, Any]],
) -> LocalOhlcvImportDecision:
    real_files_present = bool(inventory_records)
    reasons: list[str] = []
    if not real_files_present:
        return _decision("missing_local_ohlcv_files", False, False, False, False, ["missing_local_ohlcv_files"])
    schema_failed = any(record.get("schema_pass") is not True for record in schema_results)
    quality_failed = any(record.get("status") == "quality_fail" for record in quality_results)
    terminal_quality = any(record.get("status") == "terminal_block" for record in quality_results)
    terminal_license = any(record.get("status") == "terminal_block" for record in license_provenance_results)
    missing_license = any(record.get("status") == "blocked_missing_license" for record in license_provenance_results)
    missing_provenance = any(record.get("status") == "blocked_missing_provenance" for record in license_provenance_results)
    manual_review = any(record.get("status") == "manual_review_required" for record in license_provenance_results)
    sample_contamination = any(int(record.get("sample_only_row_count", 0)) > 0 or int(record.get("fake_symbol_count", 0)) > 0 for record in quality_results)
    token_contamination = any(record.get("credential_token_found") is True for record in quality_results)
    live_marker = any(record.get("broker_live_order_scheduler_real_sizing_found") is True for record in quality_results)
    if terminal_quality or terminal_license or token_contamination or live_marker:
        reasons.extend(["terminal_block"])
        if token_contamination:
            reasons.append("credential_or_token_contamination")
        if live_marker:
            reasons.append("broker_live_order_scheduler_real_sizing_contamination")
        return _decision("terminal_block", False, False, True, real_files_present, reasons)
    if sample_contamination:
        reasons.append("sample_template_contamination")
        return _decision("local_ohlcv_validation_fail", False, False, False, real_files_present, reasons)
    if schema_failed:
        reasons.append("schema_errors")
        return _decision("local_ohlcv_validation_fail", False, False, False, real_files_present, reasons)
    if quality_failed:
        reasons.append("quality_errors")
        return _decision("local_ohlcv_validation_fail", False, False, False, real_files_present, reasons)
    if missing_license:
        reasons.append("missing_license")
        return _decision("local_ohlcv_validation_fail", False, False, False, real_files_present, reasons)
    if missing_provenance:
        reasons.append("missing_provenance")
        return _decision("local_ohlcv_validation_fail", False, False, False, real_files_present, reasons)
    if manual_review:
        reasons.append("manual_review_required")
        return _decision("manual_review_required", False, False, False, real_files_present, reasons)
    return _decision("local_ohlcv_validation_pass", True, True, False, real_files_present, ["local_ohlcv_validation_pass"])


def build_local_ohlcv_import_summary(
    input_record: dict[str, Any],
    inventory_records: list[dict[str, Any]],
    schema_results: list[dict[str, Any]],
    quality_results: list[dict[str, Any]],
    license_provenance_results: list[dict[str, Any]],
    decision_record: dict[str, Any],
) -> dict[str, Any]:
    row_count = sum(int(record.get("row_count", 0)) for record in inventory_records)
    symbol_count = len({symbol for record in quality_results for symbol in record.get("symbol_coverage", [])})
    summary = {
        "artifact_type": "local_ohlcv_import_summary",
        "validator_version": LOCAL_OHLCV_IMPORT_VERSION,
        "local_ohlcv_status": decision_record["local_ohlcv_status"],
        "local_ohlcv_import_decision": decision_record["local_ohlcv_import_decision"],
        "real_data_files_present": bool(decision_record["real_data_files_present"]),
        "valid_real_dataset": bool(decision_record["valid_real_dataset"]),
        "real_data_imported": False,
        "real_data_validated": bool(decision_record["valid_real_dataset"]),
        "real_history_used": bool(decision_record["real_history_used"]),
        "history_spine_upgrade_allowed": bool(decision_record["history_spine_upgrade_allowed"]),
        "file_count": len(inventory_records),
        "row_count": row_count,
        "symbol_count": symbol_count,
        "schema_result_count": len(schema_results),
        "quality_result_count": len(quality_results),
        "license_provenance_result_count": len(license_provenance_results),
        "terminal_block_count": 1 if decision_record["terminal_block"] else 0,
        "manual_review_required": bool(decision_record["manual_review_required"]),
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "live_data_used": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_live_data": True,
        "not_broker_data": True,
        "not_strategy_promotion": True,
        "not_real_data_ingested": True,
        "input_hash": input_record["input_hash"],
        "next_recommended_target": "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1",
    }
    summary["summary_hash"] = stable_local_ohlcv_hash(summary)
    return summary


def _decision(
    status: str,
    valid: bool,
    history_allowed: bool,
    terminal: bool,
    real_files_present: bool,
    reason_codes: list[str],
) -> LocalOhlcvImportDecision:
    return LocalOhlcvImportDecision(
        artifact_type="local_ohlcv_import_decision",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        decision_id="local-ohlcv-import-decision-v1",
        local_ohlcv_status=status,
        valid_real_dataset=valid,
        real_data_imported=False,
        history_spine_upgrade_allowed=history_allowed,
        terminal_block=terminal,
        manual_review_required=status == "manual_review_required",
        real_data_files_present=real_files_present,
        reason_codes=reason_codes,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        decision_hash="",
    )
