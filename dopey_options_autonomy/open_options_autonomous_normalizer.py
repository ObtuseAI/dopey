"""Normalize accepted open historical options chain/quote files."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, contains_sample_content, file_hash, proof_record, read_jsonl, stable_hash, write_json, write_jsonl
from dopey_data_ingestion.open_data_breakthrough_quarantine_downloader import RECORDS_PATH as DOWNLOAD_RECORDS_PATH

from .open_options_schema_detector import detect_open_options_schema


ARTIFACT_DIR = ARTIFACT_ROOT / "options_autonomy"
ACCEPTED_CHAIN_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "accepted" / "options_chain"
ACCEPTED_QUOTES_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "accepted" / "options_quotes"
SCHEMA_RESULTS_PATH = ARTIFACT_DIR / "open_options_schema_detection_results.jsonl"
NORMALIZATION_RECORDS_PATH = ARTIFACT_DIR / "open_options_normalization_records.jsonl"
REJECTIONS_PATH = ARTIFACT_DIR / "open_options_normalization_rejections.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "open_options_normalization_summary.json"
PROOF_PATH = ARTIFACT_DIR / "open_options_normalization_proof.jsonl"


def run_open_options_autonomous_normalizer() -> dict[str, Any]:
    source_records = [record for record in read_jsonl(DOWNLOAD_RECORDS_PATH) if record.get("dataset_family") in {"historical_options_chain", "historical_options_quotes"}]
    schemas: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for source in source_records:
        path = Path(source["quarantine_path"])
        if not path.exists():
            continue
        schema = detect_open_options_schema(path)
        schemas.append(schema)
        if schema["schema_status"] != "schema_detected":
            rejections.append(_rejection(path, "schema_rejected"))
            continue
        if contains_sample_content(path):
            rejections.append(_rejection(path, "sample_or_fixture_contamination"))
            continue
        rows, errors = _normalize_rows(path, schema["column_mapping"], source)
        if errors:
            rejections.append(_rejection(path, ",".join(errors)))
            continue
        output_dir = ACCEPTED_QUOTES_DIR if source["dataset_family"] == "historical_options_quotes" else ACCEPTED_CHAIN_DIR
        output = output_dir / path.name
        _write_options_csv(output, rows)
        records.append(_record(path, output, source, len(rows)))
    status = "open_options_normalized" if records else "no_machine_admissible_open_options_data"
    summary = {
        "artifact_type": "open_options_normalization_summary",
        "open_options_normalization_status": status,
        "normalized_options_file_count": len(records),
        "normalization_rejection_count": len(rejections),
        "quote_priced_backtest_allowed": bool(records),
        "model_priced_research_allowed": not bool(records),
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(SCHEMA_RESULTS_PATH, schemas)
    write_jsonl(NORMALIZATION_RECORDS_PATH, records)
    write_jsonl(REJECTIONS_PATH, rejections)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("open-options-normalization-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_options_schema_detection_results": str(SCHEMA_RESULTS_PATH),
        "open_options_normalization_records": str(NORMALIZATION_RECORDS_PATH),
        "open_options_normalization_rejections": str(REJECTIONS_PATH),
        "open_options_normalization_summary": str(SUMMARY_PATH),
        "open_options_normalization_proof": str(PROOF_PATH),
    }


def _normalize_rows(path: Path, mapping: dict[str, str], source: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for index, raw in enumerate(csv.DictReader(handle)):
            bid = float(raw[mapping["bid"]])
            ask = float(raw[mapping["ask"]])
            strike = float(raw[mapping["strike"]])
            option_type = raw[mapping["option_type"]].strip().lower()
            if option_type in {"c", "call"}:
                option_type = "call"
            elif option_type in {"p", "put"}:
                option_type = "put"
            else:
                errors.append(f"option_type_invalid_{index}")
            if strike <= 0:
                errors.append(f"strike_invalid_{index}")
            if bid < 0 or ask < 0 or ask < bid:
                errors.append(f"bid_ask_invalid_{index}")
            mid = round((bid + ask) / 2, 6)
            row = {
                "snapshot_date": raw[mapping["snapshot_date"]],
                "underlying_symbol": raw[mapping["underlying_symbol"]].upper(),
                "contract_symbol": raw[mapping["contract_symbol"]],
                "expiration_date": raw[mapping["expiration_date"]],
                "strike": strike,
                "option_type": option_type,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": float(raw.get(mapping.get("last", ""), mid) or mid),
                "volume": int(float(raw.get(mapping.get("volume", ""), 0) or 0)),
                "open_interest": int(float(raw.get(mapping.get("open_interest", ""), 0) or 0)),
                "implied_volatility": float(raw.get(mapping.get("implied_volatility", ""), 0) or 0),
                "source": source["candidate_id"],
                "source_url": source["source_url"],
                "license_status": source["license_name"],
                "provenance_hash": file_hash(path),
                "autonomous_admissibility_id": source["candidate_id"],
            }
            rows.append(row)
    if not rows:
        errors.append("empty_options_file")
    return rows, sorted(set(errors))


def _write_options_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _record(input_path: Path, output_path: Path, source: dict[str, Any], row_count: int) -> dict[str, Any]:
    record = {
        "artifact_type": "open_options_normalization_records",
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
        "artifact_type": "open_options_normalization_rejections",
        "path": str(path),
        "reason_code": reason,
        "paper_only": True,
        "live_blocked": True,
    }
    record["rejection_hash"] = stable_hash(record)
    return record

