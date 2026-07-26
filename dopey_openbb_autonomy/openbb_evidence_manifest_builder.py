"""Build evidence manifest for normalized OpenBB OHLCV files."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, file_hash, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .openbb_ohlcv_normalization_bridge import NORMALIZATION_RECORDS_PATH


ARTIFACT_DIR = ARTIFACT_ROOT / "openbb_autonomy"
MANIFEST_DIR = REPO_ROOT / "dopey_data" / "openbb_autonomy" / "manifests"
MANIFEST_PATH = MANIFEST_DIR / "openbb_ohlcv_evidence_manifest.json"
SUMMARY_PATH = ARTIFACT_DIR / "openbb_evidence_manifest_summary.json"
PROOF_PATH = ARTIFACT_DIR / "openbb_evidence_manifest_proof.jsonl"


def run_openbb_evidence_manifest_builder() -> dict[str, Any]:
    records = [record for record in read_jsonl(NORMALIZATION_RECORDS_PATH) if Path(record.get("output_path", "")).exists()]
    files = [_file_entry(Path(record["output_path"]), record) for record in records]
    manifest_status = "openbb_ohlcv_manifest_ready" if files else "no_openbb_accepted_ohlcv_files"
    if files:
        manifest = {
            "artifact_type": "openbb_ohlcv_evidence_manifest",
            "manifest_version": "dopey-openbb-model-priced-s-tier-completion-v1",
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
        write_json(MANIFEST_PATH, manifest)
    summary = {
        "artifact_type": "openbb_evidence_manifest_summary",
        "manifest_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "openbb_manifest_status": manifest_status,
        "openbb_accepted_ohlcv_file_count": len(files),
        "openbb_manifest_path": str(MANIFEST_PATH) if files else "",
        "strategy_promotion_allowed": False,
        "live_promotion_allowed": False,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("openbb-evidence-manifest-proof-v1", manifest_status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "openbb_ohlcv_evidence_manifest": str(MANIFEST_PATH),
        "openbb_evidence_manifest_summary": str(SUMMARY_PATH),
        "openbb_evidence_manifest_proof": str(PROOF_PATH),
    }


def _file_entry(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    rows = _rows(path)
    symbols = sorted({row["symbol"] for row in rows})
    dates = sorted({row["date"] for row in rows})
    first = rows[0] if rows else {}
    entry = {
        "provider_id": record["provider_id"],
        "provider_name": record["provider_name"],
        "source_url": first.get("source_url", ""),
        "license": first.get("license_status", ""),
        "provenance_hash": first.get("provenance_hash", ""),
        "file_path": str(path),
        "file_hash": file_hash(path),
        "row_count": len(rows),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "date_range": {"start": dates[0] if dates else "", "end": dates[-1] if dates else ""},
        "schema_version": "dopey-openbb-normalized-ohlcv-v1",
        "admissibility_ids": sorted({first.get("autonomous_admissibility_id", "")}),
    }
    entry["entry_hash"] = stable_hash(entry)
    return entry


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _date_range(files: list[dict[str, Any]]) -> dict[str, str]:
    dates = [date for file in files for date in [file["date_range"]["start"], file["date_range"]["end"]] if date]
    return {"start": min(dates), "end": max(dates)} if dates else {"start": "", "end": ""}
