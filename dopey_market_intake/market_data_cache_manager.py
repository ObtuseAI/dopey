"""Persist and audit public OHLCV cache files."""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from dopey_wealth_engine.common import ARTIFACT_ROOT, DATA_ROOT, proof_record, read_csv, stable_hash, write_json, write_jsonl


ARTIFACT_DIR = ARTIFACT_ROOT / "market_intake"
CACHE_ROOT = DATA_ROOT / "market_lake" / "cache" / "public_ohlcv"
SUMMARY_PATH = ARTIFACT_DIR / "market_data_cache_summary.json"
MANIFEST_PATH = ARTIFACT_DIR / "market_data_cache_manifest.json"
RECORDS_PATH = ARTIFACT_DIR / "market_data_cache_records.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "market_data_cache_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "market_data_cache_proof.jsonl"


def run_market_data_cache_manager(stale_days: int) -> dict:
    records: list[dict] = []
    flags: list[dict] = []
    for path in sorted(CACHE_ROOT.glob("*/*.csv")):
        rows = read_csv(path)
        if not rows:
            flags.append(_flag("empty-cache-file", "warning", str(path)))
            continue
        last_date = str(rows[-1].get("date", ""))
        stale = _is_stale(last_date, stale_days)
        record = {
            "artifact_type": "market_data_cache_record",
            "provider": path.parent.name,
            "symbol": path.stem,
            "path": str(path),
            "row_count": len(rows),
            "first_date": str(rows[0].get("date", "")),
            "last_date": last_date,
            "sha256": _sha256(path),
            "cache_source_type": "public_cache",
            "stale": stale,
            "usable_for_market_vision": True,
            "usable_for_research_sandbox": len(rows) >= 120,
            "usable_for_paper_trading": len(rows) >= 500 and not stale,
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
        if stale:
            flags.append(_flag("stale-public-cache", "note", str(path)))
    manifest = {
        "artifact_type": "market_data_cache_manifest",
        "cache_file_count": len(records),
        "cache_rows": sum(int(record["row_count"]) for record in records),
        "records": records,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    summary = {
        "artifact_type": "market_data_cache_summary",
        "market_data_cache_status": "cache_available" if records else "cache_empty",
        "cache_file_count": len(records),
        "cache_symbol_count": len({record["symbol"] for record in records}),
        "cache_rows": manifest["cache_rows"],
        "stale_file_count": sum(1 for record in records if record["stale"]),
        "cache_manifest_path": str(MANIFEST_PATH),
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(MANIFEST_PATH, manifest)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(RECORDS_PATH, records, False)
    write_jsonl(QUALITY_FLAGS_PATH, flags, False)
    write_jsonl(PROOF_PATH, [proof_record("market-data-cache-manager", summary["market_data_cache_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def _is_stale(last_date: str, stale_days: int) -> bool:
    try:
        value = date.fromisoformat(last_date[:10])
    except ValueError:
        return True
    return (date.today() - value).days > stale_days


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _flag(flag_id: str, severity: str, path: str) -> dict:
    record = {"artifact_type": "market_data_cache_quality_flag", "flag_id": flag_id, "severity": severity, "path": path}
    record["flag_hash"] = stable_hash(record)
    return record


def artifact_paths() -> dict[str, str]:
    return {
        "market_data_cache_summary": str(SUMMARY_PATH),
        "market_data_cache_manifest": str(MANIFEST_PATH),
        "market_data_cache_records": str(RECORDS_PATH),
        "market_data_cache_quality_flags": str(QUALITY_FLAGS_PATH),
        "market_data_cache_proof": str(PROOF_PATH),
    }
