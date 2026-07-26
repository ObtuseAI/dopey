"""Fast local-only linter for manually staged OHLCV files."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .local_ohlcv_file_inventory import (
    ACCEPTED_FILE_EXTENSIONS,
    REAL_DATA_MANIFEST_PATH,
    SCAN_DIRS,
    credential_token_found,
    dataset_family_for_path,
    forbidden_live_marker_found,
    list_staged_local_ohlcv_paths,
    load_manifest_record,
    manifest_file_hashes,
    manifest_local_file_paths,
    parse_date,
    parse_float,
    read_local_ohlcv_file,
    repo_relative_path,
    sample_row_is_blocked,
)
from .local_ohlcv_license_provenance_validator import required_manifest_template_fields
from .local_ohlcv_schema_validator import required_columns_for_family
from .local_staging_contract import REPO_ROOT
from .manual_ohlcv_manifest_draft import MANUAL_OHLCV_MANIFEST_DRAFT_PATH
from .manual_ohlcv_staging_models import MANUAL_OHLCV_STAGING_VERSION, stable_manual_ohlcv_hash


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "manual_ohlcv_staging"
MANUAL_OHLCV_PREFLIGHT_RESULTS_PATH = ARTIFACT_DIR / "manual_ohlcv_preflight_results.jsonl"
MANUAL_OHLCV_PREFLIGHT_SUMMARY_PATH = ARTIFACT_DIR / "manual_ohlcv_preflight_summary.json"
ALLOWED_PREFLIGHT_STATUSES: frozenset[str] = frozenset({
    "manual_staging_required",
    "preflight_pass_manifest_incomplete",
    "preflight_fail",
    "terminal_block",
})


def run_manual_ohlcv_preflight() -> dict[str, Any]:
    file_results = build_manual_ohlcv_preflight_results()
    summary = build_manual_ohlcv_preflight_summary(file_results)
    return {"results": file_results, "summary": summary}


def build_manual_ohlcv_preflight_results() -> list[dict[str, Any]]:
    accepted_paths = set(list_staged_local_ohlcv_paths())
    all_files = _all_local_raw_files()
    results: list[dict[str, Any]] = []
    for path in all_files:
        if path in accepted_paths:
            results.append(_accepted_file_result(path))
        else:
            results.append(_rejected_extension_result(path))
    return sorted(results, key=lambda record: record["local_file_path"])


def build_manual_ohlcv_preflight_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = load_manifest_record(REAL_DATA_MANIFEST_PATH)
    final_manifest_exists = REAL_DATA_MANIFEST_PATH.exists()
    manifest_template_only = _manifest_is_template_only(manifest)
    manifest_missing_fields = [field for field in required_manifest_template_fields() if field not in manifest]
    terminal = any(record["terminal_block"] for record in results)
    failed = any(record["preflight_pass"] is False for record in results)
    if not results:
        status = "manual_staging_required"
    elif terminal:
        status = "terminal_block"
    elif failed:
        status = "preflight_fail"
    else:
        status = "preflight_pass_manifest_incomplete" if (not final_manifest_exists or manifest_template_only or manifest_missing_fields) else "preflight_pass_manifest_incomplete"
    record = {
        "artifact_type": "manual_ohlcv_preflight_summary",
        "staging_version": MANUAL_OHLCV_STAGING_VERSION,
        "preflight_status": _validate_preflight_status(status),
        "file_count": len(results),
        "preflight_failure_count": sum(1 for result in results if result["preflight_pass"] is False),
        "terminal_block_count": sum(1 for result in results if result["terminal_block"]),
        "manifest_draft_exists": MANUAL_OHLCV_MANIFEST_DRAFT_PATH.exists(),
        "final_manifest_exists": final_manifest_exists,
        "final_manifest_template_only": manifest_template_only,
        "manifest_missing_required_fields": manifest_missing_fields,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_strategy_promotion": True,
    }
    record["summary_hash"] = stable_manual_ohlcv_hash(record)
    return record


def write_manual_ohlcv_preflight() -> dict[str, Any]:
    result = run_manual_ohlcv_preflight()
    _write_jsonl(MANUAL_OHLCV_PREFLIGHT_RESULTS_PATH, result["results"])
    _write_json(MANUAL_OHLCV_PREFLIGHT_SUMMARY_PATH, result["summary"])
    return {
        **result["summary"],
        "artifact_paths": {
            "manual_ohlcv_preflight_results": str(MANUAL_OHLCV_PREFLIGHT_RESULTS_PATH),
            "manual_ohlcv_preflight_summary": str(MANUAL_OHLCV_PREFLIGHT_SUMMARY_PATH),
        },
    }


def _accepted_file_result(path: Path) -> dict[str, Any]:
    dataset_family = dataset_family_for_path(path)
    parsed = read_local_ohlcv_file(path, dataset_family)
    required = set(required_columns_for_family(dataset_family))
    headers = set(parsed.header_columns)
    missing_columns = sorted(required - headers)
    manifest = load_manifest_record(REAL_DATA_MANIFEST_PATH)
    relative = repo_relative_path(path)
    manifest_paths = manifest_local_file_paths(manifest)
    manifest_hashes = manifest_file_hashes(manifest)
    source_missing = "source" not in headers or any(not row.get("source", "").strip() for row in parsed.rows)
    sample_only = any(sample_row_is_blocked(row) for row in parsed.rows)
    fake_symbol = any(row.get("symbol", "").strip().upper() == "SAMPLE_ONLY" for row in parsed.rows)
    future = any((parse_date(row.get("date", "")) or date.min) > date.today() for row in parsed.rows)
    high_low_bad = any(_high_low_inconsistent(row) for row in parsed.rows if dataset_family != "corporate_actions")
    duplicates = _duplicate_symbol_date_count(parsed.rows)
    token_found = credential_token_found(parsed.text)
    live_found = forbidden_live_marker_found(parsed.text)
    reason_codes = _reason_codes(
        missing_columns,
        source_missing,
        sample_only,
        fake_symbol,
        token_found,
        live_found,
        future,
        high_low_bad,
        duplicates,
        relative not in manifest_paths and relative not in manifest_hashes,
    )
    terminal = token_found or live_found
    record = {
        "artifact_type": "manual_ohlcv_preflight_results",
        "staging_version": MANUAL_OHLCV_STAGING_VERSION,
        "result_id": f"manual-preflight-{stable_manual_ohlcv_hash({'path': relative})[:12]}",
        "local_file_path": relative,
        "dataset_family": dataset_family,
        "allowed_extension": path.suffix.lower() in ACCEPTED_FILE_EXTENSIONS,
        "required_header_exists": not missing_columns,
        "missing_columns": missing_columns,
        "sample_only_rows_detected": sample_only,
        "sample_only_symbol_detected": fake_symbol,
        "credential_token_patterns_detected": token_found,
        "broker_live_order_scheduler_real_sizing_patterns_detected": live_found,
        "future_dates_candidate_detected": future,
        "high_low_inconsistency_candidate_detected": high_low_bad,
        "missing_source_column_or_values": source_missing,
        "duplicate_date_symbol_rows_detected": duplicates > 0,
        "duplicate_date_symbol_count": duplicates,
        "missing_manifest_reference": relative not in manifest_paths and relative not in manifest_hashes,
        "manifest_draft_exists": MANUAL_OHLCV_MANIFEST_DRAFT_PATH.exists(),
        "final_manifest_exists": REAL_DATA_MANIFEST_PATH.exists(),
        "final_manifest_template_only": _manifest_is_template_only(manifest),
        "reason_codes": reason_codes,
        "preflight_pass": not reason_codes,
        "terminal_block": terminal,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_strategy_promotion": True,
    }
    record["record_hash"] = stable_manual_ohlcv_hash(record)
    return record


def _rejected_extension_result(path: Path) -> dict[str, Any]:
    relative = repo_relative_path(path)
    record = {
        "artifact_type": "manual_ohlcv_preflight_results",
        "staging_version": MANUAL_OHLCV_STAGING_VERSION,
        "result_id": f"manual-preflight-{stable_manual_ohlcv_hash({'path': relative})[:12]}",
        "local_file_path": relative,
        "dataset_family": dataset_family_for_path(path),
        "allowed_extension": False,
        "required_header_exists": False,
        "missing_columns": [],
        "sample_only_rows_detected": False,
        "sample_only_symbol_detected": False,
        "credential_token_patterns_detected": False,
        "broker_live_order_scheduler_real_sizing_patterns_detected": False,
        "future_dates_candidate_detected": False,
        "high_low_inconsistency_candidate_detected": False,
        "missing_source_column_or_values": False,
        "duplicate_date_symbol_rows_detected": False,
        "duplicate_date_symbol_count": 0,
        "missing_manifest_reference": True,
        "manifest_draft_exists": MANUAL_OHLCV_MANIFEST_DRAFT_PATH.exists(),
        "final_manifest_exists": REAL_DATA_MANIFEST_PATH.exists(),
        "final_manifest_template_only": _manifest_is_template_only(load_manifest_record(REAL_DATA_MANIFEST_PATH)),
        "reason_codes": ["unsupported_file_extension"],
        "preflight_pass": False,
        "terminal_block": False,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_strategy_promotion": True,
    }
    record["record_hash"] = stable_manual_ohlcv_hash(record)
    return record


def _reason_codes(
    missing_columns: list[str],
    source_missing: bool,
    sample_only: bool,
    fake_symbol: bool,
    token_found: bool,
    live_found: bool,
    future: bool,
    high_low_bad: bool,
    duplicates: int,
    missing_manifest_reference: bool,
) -> list[str]:
    reasons: list[str] = []
    if missing_columns:
        reasons.append("missing_required_header")
    if source_missing:
        reasons.append("missing_source")
    if sample_only:
        reasons.append("sample_only_rows")
    if fake_symbol:
        reasons.append("SAMPLE_ONLY")
    if token_found:
        reasons.append("credentials_tokens")
    if live_found:
        reasons.append("broker_live_order_scheduler_real_sizing_markers")
    if future:
        reasons.append("future_dates")
    if high_low_bad:
        reasons.append("high_low_inconsistency")
    if duplicates > 0:
        reasons.append("duplicate_date_symbol_rows")
    if missing_manifest_reference:
        reasons.append("missing_manifest_reference")
    return reasons


def _all_local_raw_files() -> list[Path]:
    paths: list[Path] = []
    for folder in SCAN_DIRS:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and not path.is_symlink():
                paths.append(path)
    return sorted(paths)


def _high_low_inconsistent(row: dict[str, str]) -> bool:
    high = parse_float(row.get("high"))
    low = parse_float(row.get("low"))
    open_value = parse_float(row.get("open"))
    close = parse_float(row.get("close"))
    if high is None or low is None or open_value is None or close is None:
        return True
    return not (high >= open_value and high >= close and high >= low and low <= open_value and low <= close and low <= high)


def _duplicate_symbol_date_count(rows: list[dict[str, str]]) -> int:
    seen: set[tuple[str, str]] = set()
    duplicates = 0
    for row in rows:
        key = (row.get("date", "").strip(), row.get("symbol", "").strip().upper())
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def _manifest_is_template_only(manifest: dict[str, Any]) -> bool:
    license_status = str(manifest.get("license_status", "")).lower()
    return bool(
        not manifest
        or manifest.get("template_only") is True
        or manifest.get("manifest_id") in {"TEMPLATE_ONLY_NOT_REAL_DATA", "OPERATOR_FILLED_REAL_DATA_MANIFEST"}
        or license_status in {"template_only", "unknown", "missing", "unreviewed"}
    )


def _validate_preflight_status(status: str) -> str:
    if status not in ALLOWED_PREFLIGHT_STATUSES:
        raise ValueError(f"unsupported preflight status: {status}")
    return status


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
