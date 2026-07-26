"""Normalize OpenBB-quarantined OHLCV into DOPEY schema."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, contains_forbidden_content, contains_sample_content, file_hash, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .openbb_no_key_source_probe import RESULTS_PATH as PROBE_RESULTS_PATH


ARTIFACT_DIR = ARTIFACT_ROOT / "openbb_autonomy"
ACCEPTED_DIR = REPO_ROOT / "dopey_data" / "openbb_autonomy" / "accepted" / "daily_ohlcv"
NORMALIZATION_RECORDS_PATH = ARTIFACT_DIR / "openbb_ohlcv_normalization_records.jsonl"
REJECTIONS_PATH = ARTIFACT_DIR / "openbb_ohlcv_normalization_rejections.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "openbb_ohlcv_normalization_summary.json"
PROOF_PATH = ARTIFACT_DIR / "openbb_ohlcv_normalization_proof.jsonl"
REQUIRED_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume"]
OUTPUT_COLUMNS = REQUIRED_COLUMNS + ["source", "source_provider", "source_url", "license_status", "provenance_hash", "openbb_provider_id", "autonomous_admissibility_id"]


def run_openbb_ohlcv_normalization_bridge() -> dict[str, Any]:
    probe_records = [record for record in read_jsonl(PROBE_RESULTS_PATH) if record.get("dataset_family") in {"equities OHLCV", "ETFs OHLCV"}]
    records: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for probe in probe_records:
        path = Path(probe["quarantine_path"])
        if not path.exists():
            rejections.append(_rejection(path, probe, "quarantine_file_missing"))
            continue
        if contains_forbidden_content(path):
            rejections.append(_rejection(path, probe, "credential_live_broker_marker"))
            continue
        if contains_sample_content(path):
            rejections.append(_rejection(path, probe, "sample_or_fixture_contamination"))
            continue
        rows, errors = _normalize_rows(path, probe)
        if errors:
            rejections.append(_rejection(path, probe, ",".join(errors)))
            continue
        output = ACCEPTED_DIR / path.name
        _write_csv(output, rows)
        records.append(_record(path, output, probe, len(rows)))
    status = "openbb_ohlcv_normalized" if records else "no_openbb_accepted_ohlcv_files"
    summary = {
        "artifact_type": "openbb_ohlcv_normalization_summary",
        "normalization_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "openbb_ohlcv_status": status,
        "openbb_accepted_ohlcv_file_count": len(records),
        "openbb_ohlcv_rejection_count": len(rejections),
        "accepted_output_folder": str(ACCEPTED_DIR),
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "network_fetch_performed": False,
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(NORMALIZATION_RECORDS_PATH, records)
    write_jsonl(REJECTIONS_PATH, rejections)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("openbb-ohlcv-normalization-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "openbb_ohlcv_normalization_records": str(NORMALIZATION_RECORDS_PATH),
        "openbb_ohlcv_normalization_rejections": str(REJECTIONS_PATH),
        "openbb_ohlcv_normalization_summary": str(SUMMARY_PATH),
        "openbb_ohlcv_normalization_proof": str(PROOF_PATH),
    }


def _normalize_rows(path: Path, probe: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        raw_rows = [dict(row) for row in csv.DictReader(handle)]
    errors: list[str] = []
    if not raw_rows:
        return [], ["empty_ohlcv_file"]
    missing = [column for column in REQUIRED_COLUMNS if column not in raw_rows[0]]
    if missing:
        return [], [f"missing_columns:{','.join(missing)}"]
    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    today = date.today().isoformat()
    for index, raw in enumerate(raw_rows):
        key = (raw["date"], raw["symbol"].upper())
        if key in seen:
            errors.append(f"duplicate_date_symbol_{index}")
        seen.add(key)
        if raw["date"] > today:
            errors.append(f"future_date_{index}")
        open_price = float(raw["open"])
        high = float(raw["high"])
        low = float(raw["low"])
        close = float(raw["close"])
        adjusted = float(raw["adjusted_close"])
        volume = int(float(raw["volume"]))
        if min(open_price, high, low, close, adjusted) <= 0:
            errors.append(f"nonpositive_price_{index}")
        if low > high or not (low <= open_price <= high) or not (low <= close <= high):
            errors.append(f"ohlc_inconsistent_{index}")
        if volume < 0:
            errors.append(f"negative_volume_{index}")
        normalized.append({
            "date": raw["date"],
            "symbol": raw["symbol"].upper(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "adjusted_close": adjusted,
            "volume": volume,
            "source": "OpenBB",
            "source_provider": probe["provider_name"],
            "source_url": probe["source_url"],
            "license_status": probe["license_status"],
            "provenance_hash": file_hash(path),
            "openbb_provider_id": probe["provider_id"],
            "autonomous_admissibility_id": probe["probe_id"],
        })
    return normalized, sorted(set(errors))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _record(input_path: Path, output_path: Path, probe: dict[str, Any], row_count: int) -> dict[str, Any]:
    record = {
        "artifact_type": "openbb_ohlcv_normalization_records",
        "provider_id": probe["provider_id"],
        "provider_name": probe["provider_name"],
        "input_path": str(input_path),
        "output_path": str(output_path),
        "row_count": row_count,
        "file_hash": file_hash(output_path),
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _rejection(path: Path, probe: dict[str, Any], reason: str) -> dict[str, Any]:
    record = {
        "artifact_type": "openbb_ohlcv_normalization_rejections",
        "provider_id": probe.get("provider_id", ""),
        "path": str(path),
        "reason_code": reason,
        "paper_only": True,
        "live_blocked": True,
    }
    record["rejection_hash"] = stable_hash(record)
    return record
