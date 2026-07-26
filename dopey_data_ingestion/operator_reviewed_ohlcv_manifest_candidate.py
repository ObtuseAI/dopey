"""Build a non-evidence final-manifest candidate from local reviewed inputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .operator_ohlcv_source_review_contract import OPERATOR_SOURCE_REVIEW_PATH, validate_operator_source_review_packet
from .operator_reviewed_ohlcv_stage_models import (
    OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
    OperatorReviewedOhlcvManifestCandidate,
    stable_operator_stage_hash,
)
from .operator_reviewed_ohlcv_staged_file_detector import detect_operator_reviewed_staged_files


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
MANIFEST_DIR = REPO_ROOT / "dopey_data" / "real" / "manifests"
MANIFEST_CANDIDATE_ARTIFACT_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_manifest_candidate.json"
REAL_DATA_MANIFEST_DRAFT_PATH = MANIFEST_DIR / "real_data_manifest.draft.json"
REAL_DATA_MANIFEST_CANDIDATE_PATH = MANIFEST_DIR / "real_data_manifest.candidate.json"
REAL_DATA_MANIFEST_FINAL_PATH = MANIFEST_DIR / "real_data_manifest.json"
ALLOWED_MANIFEST_CANDIDATE_STATUSES: frozenset[str] = frozenset({
    "blocked_missing_staged_files",
    "blocked_missing_operator_source_review",
    "blocked_operator_source_review_incomplete",
    "manifest_candidate_ready_for_operator_finalization",
    "terminal_block",
})


def build_operator_reviewed_manifest_candidate() -> dict[str, Any]:
    staged = detect_operator_reviewed_staged_files()
    source_review = validate_operator_source_review_packet(OPERATOR_SOURCE_REVIEW_PATH)
    inventory = [record for record in staged["inventory"] if record["file_extension"] in {".csv", ".jsonl"}]
    status = _candidate_status(staged, source_review)
    candidate = _candidate_record(status, source_review, inventory)
    manifest_payload = _manifest_payload(candidate, source_review, inventory)
    _write_json(MANIFEST_CANDIDATE_ARTIFACT_PATH, candidate)
    _write_json(REAL_DATA_MANIFEST_CANDIDATE_PATH, manifest_payload)
    return {**candidate, "manifest_candidate_path": str(REAL_DATA_MANIFEST_CANDIDATE_PATH), "artifact_path": str(MANIFEST_CANDIDATE_ARTIFACT_PATH)}


def _candidate_status(staged: dict[str, Any], source_review: dict[str, Any]) -> str:
    if staged.get("terminal_block") is True:
        return "terminal_block"
    if int(staged.get("staged_file_count", 0)) == 0:
        return "blocked_missing_staged_files"
    if source_review.get("status") == "operator_review_packet_missing":
        return "blocked_missing_operator_source_review"
    if source_review.get("status") != "operator_review_packet_valid":
        return "blocked_operator_source_review_incomplete"
    return "manifest_candidate_ready_for_operator_finalization"


def _candidate_record(status: str, source_review: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    if status not in ALLOWED_MANIFEST_CANDIDATE_STATUSES:
        raise ValueError(f"unsupported manifest candidate status: {status}")
    return OperatorReviewedOhlcvManifestCandidate(
        artifact_type="operator_reviewed_ohlcv_manifest_candidate",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        candidate_id="operator-reviewed-ohlcv-manifest-candidate-v1",
        manifest_candidate_status=status,
        staged_file_count=len(inventory),
        source_review_status=str(source_review.get("status", "operator_review_packet_missing")),
        candidate_manifest_is_evidence=False,
        final_manifest_required=True,
        operator_must_approve_final_manifest=True,
        local_file_paths=[str(record["local_file_path"]) for record in inventory],
        file_hashes={str(record["local_file_path"]): str(record["sha256"]) for record in inventory},
        row_counts={str(record["local_file_path"]): int(record["row_count"]) for record in inventory},
        symbol_counts={str(record["local_file_path"]): int(record["symbol_count_candidate"]) for record in inventory},
        date_ranges={str(record["local_file_path"]): dict(record["date_range_candidate"]) for record in inventory},
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        strategy_promotion_allowed=False,
        not_options_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        candidate_hash="",
    ).to_dict()


def _manifest_payload(candidate: dict[str, Any], source_review: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    review = _load_json(OPERATOR_SOURCE_REVIEW_PATH)
    draft = _load_json(REAL_DATA_MANIFEST_DRAFT_PATH)
    payload = {
        "artifact_type": "operator_reviewed_ohlcv_manifest_candidate_payload",
        "stage_version": OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        "manifest_id": "CANDIDATE_OPERATOR_MUST_REVIEW_AND_COPY_TO_FINAL",
        "manifest_candidate_status": candidate["manifest_candidate_status"],
        "candidate_manifest_is_evidence": False,
        "final_manifest_required_path": "dopey_data/real/manifests/real_data_manifest.json",
        "final_manifest_overwritten": False,
        "source_review_status": source_review.get("status", "operator_review_packet_missing"),
        "source_review_id": review.get("review_id", ""),
        "source_name": review.get("source_name", ""),
        "source_type": review.get("source_type", ""),
        "source_urls_or_reference_names": review.get("source_urls_or_reference_names", []),
        "download_or_export_dates": review.get("download_or_export_dates", {}),
        "dataset_families": review.get("dataset_families", []),
        "provider_terms_reviewed": review.get("provider_terms_reviewed", False),
        "license_status": review.get("license_status", "missing"),
        "license_notes": review.get("license_notes", ""),
        "redistribution_allowed": review.get("redistribution_allowed", False),
        "commercial_use_allowed": review.get("commercial_use_allowed", False),
        "internal_research_use_allowed": review.get("internal_research_use_allowed", False),
        "provenance_notes": review.get("provenance_notes", ""),
        "local_file_paths": candidate["local_file_paths"],
        "file_hashes": candidate["file_hashes"],
        "row_counts": candidate["row_counts"],
        "symbol_counts": candidate["symbol_counts"],
        "date_ranges": candidate["date_ranges"],
        "hash_record_count": len(inventory),
        "draft_manifest_hash": draft.get("draft_manifest_hash", ""),
        "not_broker_data": True,
        "not_credentials": True,
        "not_live_data": True,
        "not_network_fetched_by_dopey": True,
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
    payload["candidate_payload_hash"] = stable_operator_stage_hash(payload)
    return payload


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
