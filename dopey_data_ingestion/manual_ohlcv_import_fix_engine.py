"""Manual OHLCV import repair advisor."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .manual_ohlcv_staging_models import (
    MANUAL_OHLCV_STAGING_VERSION,
    ManualOhlcvFileRepairHint,
    stable_manual_ohlcv_hash,
)


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "manual_ohlcv_staging"
MANUAL_OHLCV_IMPORT_FIX_PLAN_PATH = ARTIFACT_DIR / "manual_ohlcv_import_fix_plan.json"
MANUAL_OHLCV_IMPORT_FIX_ITEMS_PATH = ARTIFACT_DIR / "manual_ohlcv_import_fix_items.jsonl"
LOCAL_OHLCV_IMPORT_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "local_ohlcv_import" / "local_ohlcv_import_summary.json"
LOCAL_OHLCV_SCHEMA_RESULTS_PATH = REPO_ROOT / "artifacts" / "dopey" / "local_ohlcv_import" / "local_ohlcv_schema_results.jsonl"
LOCAL_OHLCV_QUALITY_RESULTS_PATH = REPO_ROOT / "artifacts" / "dopey" / "local_ohlcv_import" / "local_ohlcv_quality_results.jsonl"
LOCAL_OHLCV_LICENSE_RESULTS_PATH = REPO_ROOT / "artifacts" / "dopey" / "local_ohlcv_import" / "local_ohlcv_license_provenance_results.jsonl"
MANUAL_PREFLIGHT_RESULTS_PATH = ARTIFACT_DIR / "manual_ohlcv_preflight_results.jsonl"
MANUAL_PREFLIGHT_SUMMARY_PATH = ARTIFACT_DIR / "manual_ohlcv_preflight_summary.json"
MANUAL_MANIFEST_DRAFT_PATH = ARTIFACT_DIR / "manual_ohlcv_manifest_draft.json"
FREE_DATA_RESULTS_PATH = REPO_ROOT / "artifacts" / "dopey" / "free_data" / "free_data_provenance_gate_results.jsonl"
FIX_GROUPS: tuple[str, ...] = (
    "stage_files",
    "complete_manifest",
    "repair_schema",
    "repair_quality",
    "repair_license_provenance",
    "remove_sample_template_rows",
    "remove_credentials_or_live_markers",
    "repair_hash_mismatch",
    "manual_review_required",
    "ready_for_validator",
    "ready_for_history_activation_after_validator_pass",
)


def build_manual_ohlcv_import_fix_plan_from_records(
    local_summary: dict[str, Any],
    preflight_summary: dict[str, Any],
    manifest_draft: dict[str, Any],
    preflight_results: list[dict[str, Any]],
    schema_results: list[dict[str, Any]],
    quality_results: list[dict[str, Any]],
    license_results: list[dict[str, Any]],
    free_data_results: list[dict[str, Any]],
) -> dict[str, Any]:
    items = _fix_items(local_summary, preflight_summary, manifest_draft, preflight_results, schema_results, quality_results, license_results, free_data_results)
    groups = {group: [item for item in items if item["fix_group"] == group] for group in FIX_GROUPS}
    status = _fix_plan_status(local_summary, preflight_summary, items)
    plan = {
        "artifact_type": "manual_ohlcv_import_fix_plan",
        "staging_version": MANUAL_OHLCV_STAGING_VERSION,
        "fix_plan_id": "manual-ohlcv-import-fix-plan-v1",
        "fix_plan_status": status,
        "primary_fix_group": items[0]["fix_group"] if items else "ready_for_validator",
        "primary_fix": items[0]["operator_action"] if items else "Run local OHLCV validator and history activation gates.",
        "fix_group_counts": {group: len(groups[group]) for group in FIX_GROUPS},
        "fix_groups": groups,
        "real_evidence_claim_allowed": False,
        "manifest_draft_is_evidence": False,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_strategy_promotion": True,
    }
    plan["plan_hash"] = stable_manual_ohlcv_hash(plan)
    return {"plan": plan, "items": items}


def build_manual_ohlcv_import_fix_plan() -> dict[str, Any]:
    return build_manual_ohlcv_import_fix_plan_from_records(
        _load_json(LOCAL_OHLCV_IMPORT_SUMMARY_PATH),
        _load_json(MANUAL_PREFLIGHT_SUMMARY_PATH),
        _load_json(MANUAL_MANIFEST_DRAFT_PATH),
        _load_jsonl(MANUAL_PREFLIGHT_RESULTS_PATH),
        _load_jsonl(LOCAL_OHLCV_SCHEMA_RESULTS_PATH),
        _load_jsonl(LOCAL_OHLCV_QUALITY_RESULTS_PATH),
        _load_jsonl(LOCAL_OHLCV_LICENSE_RESULTS_PATH),
        _load_jsonl(FREE_DATA_RESULTS_PATH),
    )


def write_manual_ohlcv_import_fix_plan() -> dict[str, Any]:
    result = build_manual_ohlcv_import_fix_plan()
    _write_json(MANUAL_OHLCV_IMPORT_FIX_PLAN_PATH, result["plan"])
    _write_jsonl(MANUAL_OHLCV_IMPORT_FIX_ITEMS_PATH, result["items"])
    return {
        **result["plan"],
        "artifact_paths": {
            "manual_ohlcv_import_fix_plan": str(MANUAL_OHLCV_IMPORT_FIX_PLAN_PATH),
            "manual_ohlcv_import_fix_items": str(MANUAL_OHLCV_IMPORT_FIX_ITEMS_PATH),
        },
    }


def _fix_items(
    local_summary: dict[str, Any],
    preflight_summary: dict[str, Any],
    manifest_draft: dict[str, Any],
    preflight_results: list[dict[str, Any]],
    schema_results: list[dict[str, Any]],
    quality_results: list[dict[str, Any]],
    license_results: list[dict[str, Any]],
    free_data_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if local_summary.get("local_ohlcv_status") == "missing_local_ohlcv_files" or manifest_draft.get("real_data_files_present") is False:
        items.append(_hint("stage-files", "stage_files", "", "missing_local_ohlcv_files", "Stage local OHLCV CSV or JSONL files.", "Place reviewed operator-supplied files under dopey_data/real/raw/daily_ohlcv/."))
    if preflight_summary.get("final_manifest_exists") is not True or preflight_summary.get("final_manifest_template_only") is True:
        items.append(_hint("complete-manifest", "complete_manifest", "", "missing_or_template_manifest", "Complete final manifest with reviewed license/provenance.", "Finalize dopey_data/real/manifests/real_data_manifest.json after operator review."))
    for record in schema_results:
        if record.get("schema_pass") is False:
            items.append(_hint(f"schema-{record.get('result_id', '')}", "repair_schema", str(record.get("local_file_path", "")), "schema_errors", "Repair required OHLCV schema columns.", "Add missing required headers and fix malformed CSV/JSONL rows."))
    for record in quality_results:
        reasons = set(str(reason) for reason in record.get("reason_codes", []))
        if reasons & {"future_date", "high_low_inconsistency", "duplicate_date_symbol", "missing_source", "nonpositive_ohlc", "negative_volume"}:
            items.append(_hint(f"quality-{record.get('result_id', '')}", "repair_quality", str(record.get("local_file_path", "")), ",".join(sorted(reasons)), "Repair OHLCV quality errors.", "Remove duplicate/future/bad OHLC rows and ensure source is recorded."))
        if reasons & {"sample_template_contamination", "sample_only_symbol", "not_real_data_row"}:
            items.append(_hint(f"sample-{record.get('result_id', '')}", "remove_sample_template_rows", str(record.get("local_file_path", "")), "sample_template_contamination", "Remove sample/template contamination.", "Remove SAMPLE_ONLY, sample_only, and not_real_data rows from real raw folders."))
        if reasons & {"credential_or_token_contamination", "broker_live_order_scheduler_real_sizing_contamination"}:
            items.append(_hint(f"live-{record.get('result_id', '')}", "remove_credentials_or_live_markers", str(record.get("local_file_path", "")), "credential_or_live_marker_contamination", "Remove credentials or live-trading markers.", "Remove API keys, tokens, broker/live/order/scheduler, account balance, buying power, and real-sizing markers."))
    for record in preflight_results:
        reasons = set(str(reason) for reason in record.get("reason_codes", []))
        if "missing_required_header" in reasons:
            items.append(_hint(f"preflight-schema-{record.get('result_id', '')}", "repair_schema", str(record.get("local_file_path", "")), "missing_required_header", "Repair preflight schema failure.", "Add required OHLCV headers before running full validation."))
        if reasons & {"future_dates", "high_low_inconsistency", "duplicate_date_symbol_rows", "missing_source"}:
            items.append(_hint(f"preflight-quality-{record.get('result_id', '')}", "repair_quality", str(record.get("local_file_path", "")), ",".join(sorted(reasons)), "Repair preflight quality failure.", "Fix future dates, duplicate date/symbol rows, high/low inconsistency, and missing source values."))
        if reasons & {"sample_only_rows", "SAMPLE_ONLY"}:
            items.append(_hint(f"preflight-sample-{record.get('result_id', '')}", "remove_sample_template_rows", str(record.get("local_file_path", "")), "sample_template_contamination", "Remove sample/template rows.", "Remove sample-only rows and SAMPLE_ONLY symbols."))
        if reasons & {"credentials_tokens", "broker_live_order_scheduler_real_sizing_markers"}:
            items.append(_hint(f"preflight-live-{record.get('result_id', '')}", "remove_credentials_or_live_markers", str(record.get("local_file_path", "")), "credential_or_live_marker_contamination", "Remove credentials or live markers.", "Remove tokens and broker/live/order/scheduler/real-sizing markers."))
    for record in license_results:
        reasons = set(str(reason) for reason in record.get("reason_codes", []))
        if reasons & {"missing_manifest", "missing_manifest_fields", "manifest_file_reference_missing", "missing_provider", "missing_provenance", "missing_license", "terms_not_reviewed"}:
            items.append(_hint(f"license-{record.get('result_id', '')}", "repair_license_provenance", str(record.get("local_file_path", "")), ",".join(sorted(reasons)), "Repair manifest license/provenance blockers.", "Record reviewed provider, terms, source, license status, file paths, hashes, counts, and safety assertions."))
        if "missing_file_hash" in reasons or "file_hash_mismatch" in reasons:
            items.append(_hint(f"hash-{record.get('result_id', '')}", "repair_hash_mismatch", str(record.get("local_file_path", "")), ",".join(sorted(reasons)), "Repair manifest file hash entries.", "Regenerate hashes with the local draft helper and update the final manifest manually."))
    if any(record.get("manual_review_required", True) for record in free_data_results):
        items.append(_hint("free-data-manual-review", "manual_review_required", "", "free_data_manual_review_required", "Free/public data candidates require manual license/provenance review.", "Do not treat candidate data as evidence until operator records reviewed source terms and provenance."))
    if not items and local_summary.get("local_ohlcv_status") == "local_ohlcv_validation_pass":
        items.append(_hint("ready-for-activation", "ready_for_history_activation_after_validator_pass", "", "validator_pass", "Validator passed; history activation gate may evaluate next.", "Use only the existing history spine activation gate."))
    if not items:
        items.append(_hint("ready-for-validator", "ready_for_validator", "", "local_files_ready_for_validator", "Run the local OHLCV validator.", "Run python -m dopey_data_ingestion.run_local_ohlcv_import_validator."))
    return _dedupe_items(items)


def _fix_plan_status(local_summary: dict[str, Any], preflight_summary: dict[str, Any], items: list[dict[str, Any]]) -> str:
    if any(item["fix_group"] == "remove_credentials_or_live_markers" for item in items):
        return "terminal_block"
    if any(item["fix_group"] == "stage_files" for item in items):
        return "manual_staging_required"
    if local_summary.get("local_ohlcv_status") == "local_ohlcv_validation_pass":
        return "validator_pass_ready_for_history_activation"
    if preflight_summary.get("preflight_status") == "preflight_pass_manifest_incomplete":
        return "local_files_detected_repair_required"
    return "local_files_detected_repair_required"


def _hint(hint_id: str, fix_group: str, local_file_path: str, reason_code: str, message: str, operator_action: str) -> dict[str, Any]:
    return ManualOhlcvFileRepairHint(
        artifact_type="manual_ohlcv_import_fix_items",
        staging_version=MANUAL_OHLCV_STAGING_VERSION,
        hint_id=f"manual-{hint_id}"[:96],
        fix_group=fix_group,
        severity="blocker" if fix_group not in {"manual_review_required", "ready_for_validator", "ready_for_history_activation_after_validator_pass"} else "info",
        local_file_path=local_file_path,
        reason_code=reason_code,
        message=message,
        operator_action=operator_action,
        evidence_claim_allowed=False,
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        not_strategy_promotion=True,
        hint_hash="",
    ).to_dict()


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = stable_manual_ohlcv_hash({
            "fix_group": item["fix_group"],
            "local_file_path": item["local_file_path"],
            "reason_code": item["reason_code"],
            "operator_action": item["operator_action"],
        })
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return json.loads(text) if text else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
