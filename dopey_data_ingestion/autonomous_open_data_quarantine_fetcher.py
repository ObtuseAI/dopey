"""Fetch only machine-admissible open data into quarantine first."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, contains_forbidden_content, fetch_https_file, proof_record, read_jsonl, safety_state, stable_hash, write_json, write_jsonl

from .autonomous_open_data_source_discovery import CANDIDATES_PATH, run_autonomous_open_data_source_discovery


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_autonomy"
QUARANTINE_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "quarantine"
ACCEPTED_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "accepted"
REJECTED_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "rejected"
FETCH_PLAN_PATH = ARTIFACT_DIR / "open_data_quarantine_fetch_plan.json"
FETCH_RECORDS_PATH = ARTIFACT_DIR / "open_data_quarantine_fetch_records.jsonl"
HASH_RECORDS_PATH = ARTIFACT_DIR / "open_data_quarantine_hash_records.jsonl"
REJECTIONS_PATH = ARTIFACT_DIR / "open_data_quarantine_rejections.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "open_data_quarantine_fetch_summary.json"
PROOF_PATH = ARTIFACT_DIR / "open_data_quarantine_fetch_proof.jsonl"


def run_autonomous_open_data_quarantine_fetcher() -> dict[str, Any]:
    if not CANDIDATES_PATH.exists():
        run_autonomous_open_data_source_discovery()
    candidates = read_jsonl(CANDIDATES_PATH)
    fetchable = [record for record in candidates if record.get("outcome") == "accepted_for_internal_research_ingest" and record.get("direct_download_url")]
    plan = _fetch_plan(fetchable)
    records: list[dict[str, Any]] = []
    hashes: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for source in fetchable:
        target = QUARANTINE_DIR / f"{_safe_name(str(source['source_id']))}.csv"
        try:
            fetch_result = fetch_https_file(str(source["direct_download_url"]), target)
            if contains_forbidden_content(target):
                rejections.append(_rejection(source, "terminal_block_forbidden_content", target))
                target.replace(REJECTED_DIR / target.name)
                continue
            records.append(_fetch_record(source, target, fetch_result))
            hashes.append(_hash_record(source, target, fetch_result))
        except Exception as exc:
            rejections.append(_rejection(source, f"fetch_failed:{type(exc).__name__}:{exc}", target))
    status = "no_machine_admissible_sources" if not fetchable else ("completed" if not rejections else "completed_with_rejections")
    summary = {
        "artifact_type": "open_data_quarantine_fetch_summary",
        "fetch_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "accepted_source_count": len(fetchable),
        "fetch_attempt_count": len(fetchable),
        "fetch_success_count": len(records),
        "fetch_rejection_count": len(rejections),
        "fetch_status": status,
        "network_fetch_performed": bool(records),
        "quarantine_folder": str(QUARANTINE_DIR),
        "accepted_folder": str(ACCEPTED_DIR),
        "rejected_folder": str(REJECTED_DIR),
        "alpha_vantage_excluded": True,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(FETCH_PLAN_PATH, plan)
    write_jsonl(FETCH_RECORDS_PATH, records)
    write_jsonl(HASH_RECORDS_PATH, hashes)
    write_jsonl(REJECTIONS_PATH, rejections)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("open-data-quarantine-fetch-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_data_quarantine_fetch_plan": str(FETCH_PLAN_PATH),
        "open_data_quarantine_fetch_records": str(FETCH_RECORDS_PATH),
        "open_data_quarantine_hash_records": str(HASH_RECORDS_PATH),
        "open_data_quarantine_rejections": str(REJECTIONS_PATH),
        "open_data_quarantine_fetch_summary": str(SUMMARY_PATH),
        "open_data_quarantine_fetch_proof": str(PROOF_PATH),
    }


def _fetch_plan(fetchable: list[dict[str, Any]]) -> dict[str, Any]:
    plan = {
        "artifact_type": "open_data_quarantine_fetch_plan",
        "plan_id": "open-data-quarantine-fetch-plan-v1",
        "fetchable_source_count": len(fetchable),
        "fetchable_sources": [record["source_id"] for record in fetchable],
        "quarantine_first": True,
        "direct_to_evidence_allowed": False,
        "no_credentials": True,
        "no_scraping": True,
        "no_broker": True,
        "alpha_vantage_excluded": True,
        "paper_only": True,
        "live_blocked": True,
    }
    plan["plan_hash"] = stable_hash(plan)
    return plan


def _fetch_record(source: dict[str, Any], target: Path, fetch_result: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "open_data_quarantine_fetch_records",
        "source_id": source["source_id"],
        "source_url": source["source_url"],
        "direct_download_url": source["direct_download_url"],
        "license_id": source["license_id"],
        "dataset_family": source["dataset_family"],
        "quarantine_path": str(target),
        "status_code": fetch_result["status_code"],
        "size_bytes": fetch_result["size_bytes"],
        "sha256": fetch_result["sha256"],
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _hash_record(source: dict[str, Any], target: Path, fetch_result: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "open_data_quarantine_hash_records",
        "source_id": source["source_id"],
        "path": str(target),
        "sha256": fetch_result["sha256"],
        "license_id": source["license_id"],
        "source_url": source["source_url"],
        "paper_only": True,
        "live_blocked": True,
    }
    record["hash_record_hash"] = stable_hash(record)
    return record


def _rejection(source: dict[str, Any], reason_code: str, target: Path) -> dict[str, Any]:
    record = {
        "artifact_type": "open_data_quarantine_rejections",
        "source_id": source.get("source_id", ""),
        "source_url": source.get("source_url", ""),
        "path": str(target),
        "reason_code": reason_code,
        "paper_only": True,
        "live_blocked": True,
    }
    record["rejection_hash"] = stable_hash(record)
    return record


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "source"

