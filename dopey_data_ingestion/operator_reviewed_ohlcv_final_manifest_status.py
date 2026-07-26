"""Evaluate whether the final real-data manifest is ready for validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .operator_ohlcv_source_review_contract import OPERATOR_SOURCE_REVIEW_PATH, VALID_LICENSE_STATUSES, validate_operator_source_review_packet
from .operator_reviewed_ohlcv_manifest_candidate import REAL_DATA_MANIFEST_CANDIDATE_PATH, REAL_DATA_MANIFEST_FINAL_PATH
from .operator_reviewed_ohlcv_stage_models import OPERATOR_REVIEWED_OHLCV_STAGE_VERSION, stable_operator_stage_hash
from .operator_reviewed_ohlcv_staged_file_detector import detect_operator_reviewed_staged_files


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
FINAL_MANIFEST_STATUS_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_final_manifest_status.json"
ALLOWED_FINAL_MANIFEST_STATUSES: frozenset[str] = frozenset({
    "final_manifest_missing",
    "candidate_manifest_ready_final_missing",
    "final_manifest_template_only",
    "final_manifest_incomplete",
    "final_manifest_hash_mismatch",
    "final_manifest_count_mismatch",
    "final_manifest_license_provenance_incomplete",
    "final_manifest_safety_fields_failed",
    "final_manifest_ready_for_validator",
    "terminal_block",
})
REQUIRED_FINAL_MANIFEST_FIELDS: tuple[str, ...] = (
    "manifest_id",
    "provider_terms_reviewed",
    "license_status",
    "local_file_paths",
    "file_hashes",
    "row_counts",
    "symbol_counts",
    "date_ranges",
    "not_broker_data",
    "not_credentials",
    "not_live_data",
    "not_network_fetched_by_dopey",
    "paper_only",
    "live_blocked",
)


def evaluate_operator_reviewed_final_manifest_status() -> dict[str, Any]:
    staged = detect_operator_reviewed_staged_files()
    source_review = validate_operator_source_review_packet(OPERATOR_SOURCE_REVIEW_PATH)
    manifest = _load_json(REAL_DATA_MANIFEST_FINAL_PATH)
    candidate = _load_json(REAL_DATA_MANIFEST_CANDIDATE_PATH)
    status, reasons = _final_status(manifest, candidate, staged, source_review)
    record = _status_record(status, reasons, manifest, candidate, staged, source_review)
    _write_json(FINAL_MANIFEST_STATUS_PATH, record)
    return record


def _final_status(
    manifest: dict[str, Any],
    candidate: dict[str, Any],
    staged: dict[str, Any],
    source_review: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if staged.get("terminal_block") is True or source_review.get("status") == "terminal_block":
        return "terminal_block", ["terminal_source_or_file_block"]
    if int(staged.get("staged_file_count", 0)) == 0:
        return "final_manifest_missing", ["operator_files_missing"]
    if not manifest:
        if candidate.get("manifest_candidate_status") == "manifest_candidate_ready_for_operator_finalization":
            return "candidate_manifest_ready_final_missing", ["operator_must_copy_reviewed_candidate_to_final_manifest"]
        return "final_manifest_missing", ["final_manifest_missing"]
    if _manifest_template_only(manifest):
        return "final_manifest_template_only", ["final_manifest_template_only"]
    missing = [field for field in REQUIRED_FINAL_MANIFEST_FIELDS if field not in manifest]
    if missing:
        return "final_manifest_incomplete", [f"missing:{field}" for field in missing]
    if not _safety_fields_pass(manifest):
        return "final_manifest_safety_fields_failed", ["safety_fields_failed"]
    if str(manifest.get("license_status", "")) not in VALID_LICENSE_STATUSES or manifest.get("provider_terms_reviewed") is not True:
        return "final_manifest_license_provenance_incomplete", ["license_or_terms_incomplete"]
    if not str(manifest.get("provenance_notes", manifest.get("source", ""))).strip():
        return "final_manifest_license_provenance_incomplete", ["provenance_missing"]
    hash_reasons = _hash_mismatch_reasons(manifest, staged)
    if hash_reasons:
        return "final_manifest_hash_mismatch", hash_reasons
    count_reasons = _count_mismatch_reasons(manifest, staged)
    if count_reasons:
        return "final_manifest_count_mismatch", count_reasons
    return "final_manifest_ready_for_validator", reasons


def _status_record(
    status: str,
    reasons: list[str],
    manifest: dict[str, Any],
    candidate: dict[str, Any],
    staged: dict[str, Any],
    source_review: dict[str, Any],
) -> dict[str, Any]:
    if status not in ALLOWED_FINAL_MANIFEST_STATUSES:
        raise ValueError(f"unsupported final manifest status: {status}")
    record = {
        "artifact_type": "operator_reviewed_ohlcv_final_manifest_status",
        "stage_version": OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        "final_manifest_status": status,
        "reason_codes": reasons,
        "final_manifest_exists": bool(manifest),
        "final_manifest_template_only": _manifest_template_only(manifest),
        "candidate_manifest_exists": bool(candidate),
        "final_manifest_references_staged_files": _references_staged_files(manifest, staged),
        "final_manifest_file_hashes_match_staged_files": not _hash_mismatch_reasons(manifest, staged) if manifest else False,
        "final_manifest_row_counts_match_staged_files": not _count_mismatch_reasons(manifest, staged) if manifest else False,
        "final_manifest_symbol_counts_present": bool(_dict_field(manifest, "symbol_counts")),
        "final_manifest_date_ranges_present": bool(_dict_field(manifest, "date_ranges")),
        "final_manifest_license_status": str(manifest.get("license_status", "missing")),
        "final_manifest_provider_terms_reviewed": manifest.get("provider_terms_reviewed") is True,
        "final_manifest_provenance_complete": bool(str(manifest.get("provenance_notes", manifest.get("source", ""))).strip()),
        "final_manifest_source_review_linkage": str(manifest.get("source_review_id", "")) or str(source_review.get("review_id", "")),
        "source_review_status": source_review.get("status", "operator_review_packet_missing"),
        "staged_file_count": int(staged.get("staged_file_count", 0)),
        "not_broker_data": manifest.get("not_broker_data") is True if manifest else True,
        "not_credentials": manifest.get("not_credentials") is True if manifest else True,
        "not_live_data": manifest.get("not_live_data") is True if manifest else True,
        "not_network_fetched_by_dopey": manifest.get("not_network_fetched_by_dopey") is True if manifest else True,
        "paper_only": True,
        "live_blocked": True,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
    }
    record["status_hash"] = stable_operator_stage_hash(record)
    return record


def _hash_mismatch_reasons(manifest: dict[str, Any], staged: dict[str, Any]) -> list[str]:
    hashes = _dict_field(manifest, "file_hashes")
    inventory = staged.get("inventory", []) if isinstance(staged.get("inventory"), list) else []
    reasons: list[str] = []
    for record in inventory:
        path = str(record.get("local_file_path", ""))
        if path and hashes.get(path) != record.get("sha256"):
            reasons.append(f"hash_mismatch:{path}")
    return reasons


def _count_mismatch_reasons(manifest: dict[str, Any], staged: dict[str, Any]) -> list[str]:
    row_counts = _dict_field(manifest, "row_counts")
    symbol_counts = _dict_field(manifest, "symbol_counts")
    date_ranges = _dict_field(manifest, "date_ranges")
    inventory = staged.get("inventory", []) if isinstance(staged.get("inventory"), list) else []
    reasons: list[str] = []
    for record in inventory:
        path = str(record.get("local_file_path", ""))
        if not path:
            continue
        if int(row_counts.get(path, -1)) != int(record.get("row_count", -2)):
            reasons.append(f"row_count_mismatch:{path}")
        if path not in symbol_counts:
            reasons.append(f"symbol_count_missing:{path}")
        if path not in date_ranges:
            reasons.append(f"date_range_missing:{path}")
    return reasons


def _references_staged_files(manifest: dict[str, Any], staged: dict[str, Any]) -> bool:
    paths = set(str(path) for path in manifest.get("local_file_paths", []) if isinstance(manifest.get("local_file_paths", []), list))
    inventory = staged.get("inventory", []) if isinstance(staged.get("inventory"), list) else []
    staged_paths = {str(record.get("local_file_path", "")) for record in inventory}
    return bool(paths and staged_paths and staged_paths.issubset(paths))


def _safety_fields_pass(manifest: dict[str, Any]) -> bool:
    return all(manifest.get(field) is True for field in (
        "not_broker_data",
        "not_credentials",
        "not_live_data",
        "not_network_fetched_by_dopey",
        "paper_only",
        "live_blocked",
    ))


def _manifest_template_only(manifest: dict[str, Any]) -> bool:
    return bool(
        manifest.get("template_only") is True
        or manifest.get("sample_only") is True
        or manifest.get("not_real_data") is True
        or str(manifest.get("license_status", "")).lower() in {"unknown", "unreviewed", "missing", "template_only", "unlicensed"}
        or manifest.get("manifest_id") in {"TEMPLATE_ONLY_NOT_REAL_DATA", "OPERATOR_FILLED_REAL_DATA_MANIFEST"}
    )


def _dict_field(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key, {})
    return value if isinstance(value, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
