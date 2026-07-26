"""Normalize breakthrough OHLCV files after machine-admissible quarantine."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, contains_sample_content, file_hash, proof_record, read_jsonl, stable_hash, validate_ohlcv_rows, write_csv_records, write_json, write_jsonl

from .open_data_breakthrough_quarantine_downloader import RECORDS_PATH as DOWNLOAD_RECORDS_PATH
from .open_data_breakthrough_quarantine_downloader import QUARANTINE_ROOT
from .open_ohlcv_schema_detector import detect_open_ohlcv_schema


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_breakthrough"
ACCEPTED_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "accepted" / "daily_ohlcv"
SCHEMA_RESULTS_PATH = ARTIFACT_DIR / "open_ohlcv_schema_detection_results.jsonl"
NORMALIZATION_RECORDS_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_records.jsonl"
REJECTIONS_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_rejections.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_summary.json"
PROOF_PATH = ARTIFACT_DIR / "open_ohlcv_normalization_proof.jsonl"


def run_open_ohlcv_autonomous_normalizer() -> dict[str, Any]:
    download_records = [record for record in read_jsonl(DOWNLOAD_RECORDS_PATH) if record.get("dataset_family") == "open_ohlcv"]
    source_by_path = {str(Path(record["quarantine_path"]).resolve()): record for record in download_records}
    paths = [Path(record["quarantine_path"]) for record in download_records if Path(record["quarantine_path"]).exists()]
    schemas: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for path in paths:
        schema = detect_open_ohlcv_schema(path)
        schemas.append(schema)
        source = source_by_path[str(path.resolve())]
        if schema["schema_status"] != "schema_detected":
            rejections.append(_rejection(path, "schema_rejected"))
            continue
        if contains_sample_content(path):
            rejections.append(_rejection(path, "sample_or_fixture_contamination"))
            continue
        rows = _normalize_rows(path, schema["column_mapping"], source)
        errors = validate_ohlcv_rows(rows)
        if errors:
            rejections.append(_rejection(path, ",".join(errors)))
            continue
        output = ACCEPTED_DIR / path.name
        write_csv_records(output, rows)
        records.append(_record(path, output, source, len(rows)))
    status = "open_ohlcv_normalized" if records else "no_accepted_ohlcv_files"
    summary = {
        "artifact_type": "open_ohlcv_normalization_summary",
        "open_ohlcv_normalization_status": status,
        "schema_detection_count": len(schemas),
        "normalized_ohlcv_file_count": len(records),
        "normalization_rejection_count": len(rejections),
        "accepted_output_folder": str(ACCEPTED_DIR),
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(SCHEMA_RESULTS_PATH, schemas)
    write_jsonl(NORMALIZATION_RECORDS_PATH, records)
    write_jsonl(REJECTIONS_PATH, rejections)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("open-ohlcv-normalization-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_ohlcv_schema_detection_results": str(SCHEMA_RESULTS_PATH),
        "open_ohlcv_normalization_records": str(NORMALIZATION_RECORDS_PATH),
        "open_ohlcv_normalization_rejections": str(REJECTIONS_PATH),
        "open_ohlcv_normalization_summary": str(SUMMARY_PATH),
        "open_ohlcv_normalization_proof": str(PROOF_PATH),
    }


def _normalize_rows(path: Path, mapping: dict[str, str], source: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for raw in csv.DictReader(handle):
            row = {
                "date": raw[mapping["date"]],
                "symbol": raw[mapping["symbol"]].upper(),
                "open": float(raw[mapping["open"]]),
                "high": float(raw[mapping["high"]]),
                "low": float(raw[mapping["low"]]),
                "close": float(raw[mapping["close"]]),
                "adjusted_close": float(raw[mapping["adjusted_close"]]),
                "volume": int(float(raw[mapping["volume"]])),
                "source": source["candidate_id"],
                "source_url": source["source_url"],
                "license_status": source["license_name"],
                "provenance_hash": file_hash(path),
                "autonomous_admissibility_id": source["candidate_id"],
            }
            rows.append(row)
    return rows


def _record(input_path: Path, output_path: Path, source: dict[str, Any], row_count: int) -> dict[str, Any]:
    record = {
        "artifact_type": "open_ohlcv_normalization_records",
        "candidate_id": source["candidate_id"],
        "input_path": str(input_path),
        "output_path": str(output_path),
        "row_count": row_count,
        "file_hash": file_hash(output_path),
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _rejection(path: Path, reason: str) -> dict[str, Any]:
    record = {
        "artifact_type": "open_ohlcv_normalization_rejections",
        "path": str(path),
        "reason_code": reason,
        "paper_only": True,
        "live_blocked": True,
    }
    record["rejection_hash"] = stable_hash(record)
    return record

