"""Build evidence manifests for accepted breakthrough OHLCV/options files."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, file_hash, proof_record, read_jsonl, stable_hash, write_json, write_jsonl
from dopey_options_autonomy.open_options_autonomous_normalizer import NORMALIZATION_RECORDS_PATH as OPTIONS_NORMALIZATION_RECORDS_PATH

from .open_ohlcv_autonomous_normalizer import NORMALIZATION_RECORDS_PATH as OHLCV_NORMALIZATION_RECORDS_PATH


MANIFEST_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "manifests"
OHLCV_MANIFEST_PATH = MANIFEST_DIR / "open_ohlcv_evidence_manifest.json"
OPTIONS_MANIFEST_PATH = MANIFEST_DIR / "open_options_evidence_manifest.json"
ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_breakthrough"
SUMMARY_PATH = ARTIFACT_DIR / "open_data_evidence_manifest_summary.json"
PROOF_PATH = ARTIFACT_DIR / "open_data_evidence_manifest_proof.jsonl"


def run_open_data_breakthrough_manifest_builder() -> dict[str, Any]:
    ohlcv_records = [record for record in read_jsonl(OHLCV_NORMALIZATION_RECORDS_PATH) if Path(record.get("output_path", "")).exists()]
    options_records = [record for record in read_jsonl(OPTIONS_NORMALIZATION_RECORDS_PATH) if Path(record.get("output_path", "")).exists()]
    ohlcv_manifest = _manifest("open_ohlcv_evidence_manifest", ohlcv_records)
    options_manifest = _manifest("open_options_evidence_manifest", options_records)
    if ohlcv_records:
        write_json(OHLCV_MANIFEST_PATH, ohlcv_manifest)
    if options_records:
        write_json(OPTIONS_MANIFEST_PATH, options_manifest)
    status = _status(bool(ohlcv_records), bool(options_records))
    summary = {
        "artifact_type": "open_data_evidence_manifest_summary",
        "manifest_version": "dopey-open-data-breakthrough-options-evidence-completion-v1",
        "manifest_status": status,
        "accepted_ohlcv_file_count": len(ohlcv_records),
        "accepted_options_file_count": len(options_records),
        "open_ohlcv_manifest_path": str(OHLCV_MANIFEST_PATH) if ohlcv_records else "",
        "open_options_manifest_path": str(OPTIONS_MANIFEST_PATH) if options_records else "",
        "paper_only": True,
        "live_blocked": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("open-data-evidence-manifest-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_ohlcv_evidence_manifest": str(OHLCV_MANIFEST_PATH),
        "open_options_evidence_manifest": str(OPTIONS_MANIFEST_PATH),
        "open_data_evidence_manifest_summary": str(SUMMARY_PATH),
        "open_data_evidence_manifest_proof": str(PROOF_PATH),
    }


def _status(has_ohlcv: bool, has_options: bool) -> str:
    if has_ohlcv and has_options:
        return "open_ohlcv_and_options_manifests_ready"
    if has_ohlcv:
        return "open_ohlcv_manifest_ready"
    if has_options:
        return "open_options_manifest_ready"
    return "no_accepted_open_data_files"


def _manifest(artifact_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    files = [_file_entry(record) for record in records]
    manifest = {
        "artifact_type": artifact_type,
        "manifest_version": "dopey-open-data-breakthrough-options-evidence-completion-v1",
        "file_count": len(files),
        "files": files,
        "row_count": sum(file["row_count"] for file in files),
        "symbol_count": len({symbol for file in files for symbol in file["symbols"]}),
        "date_range": _date_range(files),
        "paper_only": True,
        "live_blocked": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    return manifest


def _file_entry(record: dict[str, Any]) -> dict[str, Any]:
    path = Path(record["output_path"])
    rows = _rows(path)
    symbols = sorted({row.get("symbol") or row.get("underlying_symbol", "") for row in rows if row.get("symbol") or row.get("underlying_symbol")})
    dates = sorted({row.get("date") or row.get("snapshot_date", "") for row in rows if row.get("date") or row.get("snapshot_date")})
    first = rows[0] if rows else {}
    entry = {
        "candidate_id": record["candidate_id"],
        "source_url": first.get("source_url", ""),
        "license": first.get("license_status", ""),
        "provenance_hash": first.get("provenance_hash", ""),
        "file_path": str(path),
        "file_hash": file_hash(path),
        "row_count": len(rows),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "date_range": {"start": dates[0] if dates else "", "end": dates[-1] if dates else ""},
        "schema_version": "dopey-open-data-breakthrough-normalized-v1",
        "admissibility_ids": sorted({first.get("autonomous_admissibility_id", record["candidate_id"])}),
    }
    entry["entry_hash"] = stable_hash(entry)
    return entry


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _date_range(files: list[dict[str, Any]]) -> dict[str, str]:
    dates = [date for file in files for date in [file["date_range"]["start"], file["date_range"]["end"]] if date]
    return {"start": min(dates), "end": max(dates)} if dates else {"start": "", "end": ""}

