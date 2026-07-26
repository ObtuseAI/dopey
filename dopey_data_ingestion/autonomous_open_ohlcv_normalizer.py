"""Normalize accepted autonomous open OHLCV into Dopey local schema."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import (
    ARTIFACT_ROOT,
    REPO_ROOT,
    contains_forbidden_content,
    contains_sample_content,
    normalize_ohlcv_rows,
    proof_record,
    read_csv_rows,
    read_jsonl,
    safety_state,
    stable_hash,
    validate_ohlcv_rows,
    write_csv_records,
    write_json,
    write_jsonl,
)

from .autonomous_open_data_quarantine_fetcher import FETCH_RECORDS_PATH


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_autonomy"
QUARANTINE_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "quarantine"
ACCEPTED_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "accepted"
DAILY_OUTPUT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "daily_ohlcv_autonomous_open"
MARKET_OUTPUT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "market_context_autonomous_open"
CORPORATE_OUTPUT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "corporate_actions_autonomous_open"
RECORDS_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_records.jsonl"
REJECTIONS_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_rejections.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_summary.json"
PROOF_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_proof.jsonl"


def run_autonomous_open_ohlcv_normalizer() -> dict[str, Any]:
    source_records = read_jsonl(FETCH_RECORDS_PATH)
    source_by_path = {Path(record["quarantine_path"]).resolve(): record for record in source_records if record.get("dataset_family") == "daily_ohlcv"}
    candidate_paths = [path for root in [QUARANTINE_DIR, ACCEPTED_DIR] if root.exists() for path in root.glob("*.csv")]
    records: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for path in candidate_paths:
        source = source_by_path.get(path.resolve())
        if source is None:
            continue
        if contains_forbidden_content(path):
            rejections.append(_rejection(path, "terminal_block_forbidden_content"))
            continue
        if contains_sample_content(path):
            rejections.append(_rejection(path, "rejected_sample_or_fixture"))
            continue
        try:
            rows = normalize_ohlcv_rows(read_csv_rows(path), source)
            errors = validate_ohlcv_rows(rows)
        except Exception as exc:
            rejections.append(_rejection(path, f"normalization_error:{type(exc).__name__}:{exc}"))
            continue
        if errors:
            rejections.append(_rejection(path, ",".join(errors)))
            continue
        output_path = DAILY_OUTPUT_DIR / path.name
        write_csv_records(output_path, rows)
        records.append(_record(path, output_path, source, len(rows)))
    status = "normalized" if records else "blocked_no_accepted_open_ohlcv_files"
    summary = {
        "artifact_type": "open_ohlcv_normalization_summary",
        "normalization_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "normalization_status": status,
        "normalized_file_count": len(records),
        "rejection_count": len(rejections),
        "accepted_ohlcv_file_count": len(records),
        "output_daily_folder": str(DAILY_OUTPUT_DIR),
        "output_market_context_folder": str(MARKET_OUTPUT_DIR),
        "output_corporate_actions_folder": str(CORPORATE_OUTPUT_DIR),
        "valid_real_dataset": False,
        "network_fetch_performed": bool(source_records),
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(RECORDS_PATH, records)
    write_jsonl(REJECTIONS_PATH, rejections)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("open-ohlcv-normalization-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_ohlcv_normalization_records": str(RECORDS_PATH),
        "open_ohlcv_normalization_rejections": str(REJECTIONS_PATH),
        "open_ohlcv_normalization_summary": str(SUMMARY_PATH),
        "open_ohlcv_normalization_proof": str(PROOF_PATH),
    }


def _record(input_path: Path, output_path: Path, source: dict[str, Any], row_count: int) -> dict[str, Any]:
    record = {
        "artifact_type": "open_ohlcv_normalization_records",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_id": source["source_id"],
        "source_url": source["source_url"],
        "license_id": source["license_id"],
        "row_count": row_count,
        "status": "normalized",
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _rejection(path: Path, reason_code: str) -> dict[str, Any]:
    record = {
        "artifact_type": "open_ohlcv_normalization_rejections",
        "path": str(path),
        "reason_code": reason_code,
        "paper_only": True,
        "live_blocked": True,
    }
    record["rejection_hash"] = stable_hash(record)
    return record

