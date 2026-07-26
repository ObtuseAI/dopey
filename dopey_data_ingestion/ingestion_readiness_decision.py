"""Import-readiness decision rules for local real-data planning."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .ingestion_plan_models import DATA_INGESTION_PLAN_VERSION, ImportReadinessDecision, IngestionPlanQualityFlag
from .local_staging_contract import RAW_FOLDER_CONTRACTS, REAL_DATA_MANIFEST_PATH, REPO_ROOT


TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"access[_-]?token", re.IGNORECASE),
    re.compile(r"secret[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
)
FORBIDDEN_LIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"broker", re.IGNORECASE),
    re.compile(r"live[_ -]?order", re.IGNORECASE),
    re.compile(r"place[_ -]?order", re.IGNORECASE),
    re.compile(r"scheduler|daemon", re.IGNORECASE),
    re.compile(r"buying[_ -]?power|account[_ -]?balance|real[_ -]?sizing", re.IGNORECASE),
)


def decide_import_readiness(
    dataset_requirements: list[dict[str, Any]],
    provider_candidates: list[dict[str, Any]],
    local_staging_contract: dict[str, Any],
    schema_contracts: list[dict[str, Any]],
    quality_gates: list[dict[str, Any]],
    history_spine_status: dict[str, Any],
    fitness_replacement_status: dict[str, Any],
) -> ImportReadinessDecision:
    staged_files = staged_real_data_files()
    real_files_present = len(staged_files) > 0
    manifest_present = REAL_DATA_MANIFEST_PATH.exists()
    sample_only_rows = any(_file_contains_sample_only(path) for path in staged_files)
    credential_or_token = any(_file_contains_token(path) for path in staged_files)
    forbidden_live_path = any(_file_contains_forbidden_live_path(path) for path in staged_files)
    manifest = _read_manifest() if manifest_present else {}
    network_fetch_performed = bool(manifest.get("network_fetch_performed_by_dopey", False)) or bool(manifest.get("not_network_fetched_by_dopey") is False)
    license_complete = _license_provenance_complete(manifest)
    reason_codes: list[str] = []
    decision = "plan_ready_import_not_started"
    ingestion_status = "real_data_ingestion_plan_ready"
    if sample_only_rows:
        decision = "terminal_block"
        ingestion_status = "terminal_block"
        reason_codes.append("sample_only_row_in_real_path")
    elif credential_or_token:
        decision = "terminal_block"
        ingestion_status = "terminal_block"
        reason_codes.append("credential_or_token_in_staged_file")
    elif forbidden_live_path:
        decision = "terminal_block"
        ingestion_status = "terminal_block"
        reason_codes.append("broker_live_order_scheduler_or_real_sizing_path_found")
    elif network_fetch_performed:
        decision = "blocked_network_fetch_attempt"
        ingestion_status = "terminal_block"
        reason_codes.append("network_fetch_attempted_by_dopey")
    elif not real_files_present:
        reason_codes.append("plan_ready_no_real_files_present")
    elif not manifest_present:
        decision = "manual_review_required"
        ingestion_status = "manual_review_required"
        reason_codes.append("real_files_present_manifest_missing")
    elif not license_complete:
        decision = _license_block_decision(manifest)
        ingestion_status = "missing_provider_selection"
        reason_codes.append("license_or_provenance_incomplete")
    else:
        decision = "manual_review_required"
        ingestion_status = "manual_review_required"
        reason_codes.append("manifest_and_files_present_validation_not_run")
    return ImportReadinessDecision(
        artifact_type="import_readiness_decision",
        ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
        decision_id="dopey-real-data-import-readiness-v1",
        ingestion_status=ingestion_status,
        import_readiness_decision=decision,
        real_data_files_present=real_files_present,
        real_data_ingested=False,
        real_data_validated=False,
        manifest_present=manifest_present,
        license_provenance_complete=license_complete,
        sample_only_rows_in_real_path=sample_only_rows,
        credential_or_token_found=credential_or_token,
        broker_live_order_scheduler_or_real_sizing_path_found=forbidden_live_path,
        network_fetch_performed=network_fetch_performed,
        reason_codes=sorted(reason_codes),
        next_recommended_target="DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1",
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        decision_hash="",
    )


def build_ingestion_quality_flags(decision: dict[str, Any]) -> list[IngestionPlanQualityFlag]:
    flags: list[IngestionPlanQualityFlag] = []
    for reason_code in decision.get("reason_codes", []) or []:
        terminal = decision.get("import_readiness_decision") in {"terminal_block", "blocked_network_fetch_attempt", "blocked_fake_real_data"}
        manual = decision.get("import_readiness_decision") == "manual_review_required"
        flags.append(IngestionPlanQualityFlag(
            artifact_type="ingestion_plan_quality_flag",
            ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
            flag_id=f"ingestion-flag-{reason_code}",
            severity="error" if terminal else ("warning" if manual else "info"),
            reason_code=str(reason_code),
            message=_message_for_reason(str(reason_code)),
            terminal_block=terminal,
            manual_review_required=manual,
            paper_only=True,
            live_blocked=True,
            not_real_data_ingested=True,
            flag_hash="",
        ))
    return flags


def staged_real_data_files() -> list[Path]:
    files: list[Path] = []
    for relative_path in RAW_FOLDER_CONTRACTS.values():
        folder = REPO_ROOT / relative_path
        if not folder.exists():
            continue
        files.extend(path for path in folder.rglob("*") if path.is_file() and not path.name.startswith("."))
    return sorted(files)


def _read_manifest() -> dict[str, Any]:
    try:
        return json.loads(REAL_DATA_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _license_provenance_complete(manifest: dict[str, Any]) -> bool:
    if not manifest or manifest.get("template_only") is True:
        return False
    if not manifest.get("provider_name"):
        return False
    if manifest.get("license_status") in {"", "unknown", "unreviewed", "missing", None}:
        return False
    if manifest.get("provider_terms_reviewed") is not True:
        return False
    if not manifest.get("local_file_paths"):
        return False
    if not manifest.get("file_hashes"):
        return False
    return True


def _license_block_decision(manifest: dict[str, Any]) -> str:
    if manifest.get("license_status") in {"", "unknown", "unreviewed", "missing", None}:
        return "blocked_missing_license"
    return "blocked_missing_provenance"


def _file_contains_sample_only(path: Path) -> bool:
    text = _safe_text(path)
    return "sample_only=true" in text.lower() or "not_real_data=true" in text.lower() or "SAMPLE_ONLY" in text


def _file_contains_token(path: Path) -> bool:
    text = _safe_text(path)
    return any(pattern.search(text) for pattern in TOKEN_PATTERNS)


def _file_contains_forbidden_live_path(path: Path) -> bool:
    text = _safe_text(path)
    return any(pattern.search(text) for pattern in FORBIDDEN_LIVE_PATTERNS)


def _safe_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _message_for_reason(reason_code: str) -> str:
    messages = {
        "plan_ready_no_real_files_present": "Plan is ready; local real-data import has not started.",
        "real_files_present_manifest_missing": "Real-data path contains files but manifest is missing.",
        "license_or_provenance_incomplete": "License or provenance fields are incomplete.",
        "sample_only_row_in_real_path": "Sample-only rows were found in a real-data path.",
        "credential_or_token_in_staged_file": "Credential-like material was found in a staged file.",
        "broker_live_order_scheduler_or_real_sizing_path_found": "Broker/live/order/scheduler/real-sizing marker was found.",
        "network_fetch_attempted_by_dopey": "Manifest indicates network fetch by DOPEY, which is forbidden for this bundle.",
        "manifest_and_files_present_validation_not_run": "Manifest and files are present, but validation has not run.",
    }
    return messages.get(reason_code, "Ingestion plan requires review.")
