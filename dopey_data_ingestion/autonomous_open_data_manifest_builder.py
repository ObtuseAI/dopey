"""Build final evidence-eligible manifest for autonomous open data only."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, file_hash, proof_record, read_csv_rows, read_jsonl, safety_state, stable_hash, write_json, write_jsonl

from .autonomous_open_ohlcv_normalizer import DAILY_OUTPUT_DIR, RECORDS_PATH


MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "autonomous_open_data_manifest.json"
ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_autonomy"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_open_data_manifest_summary.json"
PROOF_PATH = ARTIFACT_DIR / "autonomous_open_data_manifest_proof.jsonl"


def run_autonomous_open_data_manifest_builder() -> dict[str, Any]:
    normalized = read_jsonl(RECORDS_PATH)
    files = [DAILY_OUTPUT_DIR / record["output_path"].split("\\")[-1].split("/")[-1] for record in normalized if record.get("status") == "normalized"]
    files = [path for path in files if path.exists()]
    if not files:
        summary = _empty_summary()
        write_json(SUMMARY_PATH, summary)
        write_jsonl(PROOF_PATH, [proof_record("autonomous-open-data-manifest-proof-v1", summary["manifest_status"], summary)])
        return {**summary, "artifact_paths": artifact_paths()}
    manifest_records = [_manifest_file(path) for path in files]
    manifest = {
        "manifest_version": "dopey-autonomous-open-data-manifest-v1",
        "manifest_status": "final_manifest_machine_verified",
        "schema_version": "dopey-autonomous-open-data-schema-v1",
        "source_files": manifest_records,
        "file_count": len(manifest_records),
        "row_count": sum(record["row_count"] for record in manifest_records),
        "symbol_count": len({symbol for record in manifest_records for symbol in record["symbols"]}),
        "date_range": _date_range(manifest_records),
        "no_credentials": True,
        "not_broker_data": True,
        "not_live_data": True,
        "not_network_fetched_by_disallowed_source": True,
        "paper_only": True,
        "live_blocked": True,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    write_json(MANIFEST_PATH, manifest)
    summary = {
        "artifact_type": "autonomous_open_data_manifest_summary",
        "manifest_status": "final_manifest_machine_verified",
        "manifest_path": str(MANIFEST_PATH),
        "accepted_file_count": len(files),
        "row_count": manifest["row_count"],
        "symbol_count": manifest["symbol_count"],
        "valid_real_dataset": False,
        "network_fetch_performed": False,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("autonomous-open-data-manifest-proof-v1", summary["manifest_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_open_data_manifest": str(MANIFEST_PATH),
        "autonomous_open_data_manifest_summary": str(SUMMARY_PATH),
        "autonomous_open_data_manifest_proof": str(PROOF_PATH),
    }


def _empty_summary() -> dict[str, Any]:
    record = {
        "artifact_type": "autonomous_open_data_manifest_summary",
        "manifest_status": "no_accepted_open_data_files",
        "manifest_path": str(MANIFEST_PATH),
        "accepted_file_count": 0,
        "row_count": 0,
        "symbol_count": 0,
        "valid_real_dataset": False,
        "network_fetch_performed": False,
        **safety_state(),
    }
    record["summary_hash"] = stable_hash(record)
    return record


def _manifest_file(path) -> dict[str, Any]:
    rows = read_csv_rows(path)
    symbols = sorted({row["symbol"] for row in rows})
    dates = sorted({row["date"] for row in rows})
    first = rows[0]
    record = {
        "source_name": first["source"],
        "source_url": first["source_url"],
        "license": first["license_status"],
        "provenance_hash": first["provenance_hash"],
        "file_path": str(path),
        "file_hash": file_hash(path),
        "row_count": len(rows),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "date_range": {"start": dates[0], "end": dates[-1]},
        "schema_version": "dopey-autonomous-open-data-schema-v1",
        "admissibility_decision_ids": sorted({row["autonomous_admissibility_id"] for row in rows}),
        "no_credentials": True,
        "not_broker_data": True,
        "not_live_data": True,
        "not_network_fetched_by_disallowed_source": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _date_range(records: list[dict[str, Any]]) -> dict[str, str]:
    dates = [date for record in records for date in [record["date_range"]["start"], record["date_range"]["end"]]]
    return {"start": min(dates), "end": max(dates)}

