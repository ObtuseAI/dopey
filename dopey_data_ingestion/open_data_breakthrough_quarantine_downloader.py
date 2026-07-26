"""Quarantine downloader for accepted breakthrough candidates."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, contains_forbidden_content, fetch_https_file, file_hash, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .exhaustive_open_data_discovery_matrix import CANDIDATE_REGISTRY_PATH, run_exhaustive_open_data_discovery_matrix
from .machine_license_terms_verifier import RESULTS_PATH as LICENSE_RESULTS_PATH, run_machine_license_terms_verifier


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_breakthrough"
QUARANTINE_ROOT = REPO_ROOT / "dopey_data" / "open_autonomy" / "quarantine"
REJECTED_DIR = REPO_ROOT / "dopey_data" / "open_autonomy" / "rejected"
FAMILY_DIRS = {
    "open_ohlcv": QUARANTINE_ROOT / "ohlcv",
    "historical_options_chain": QUARANTINE_ROOT / "options_chain",
    "historical_options_quotes": QUARANTINE_ROOT / "options_quotes",
    "market_context": QUARANTINE_ROOT / "context",
    "macro_rates": QUARANTINE_ROOT / "context",
    "filings_fundamentals": QUARANTINE_ROOT / "fundamentals",
}
PLAN_PATH = ARTIFACT_DIR / "quarantine_download_plan.json"
RECORDS_PATH = ARTIFACT_DIR / "quarantine_download_records.jsonl"
HASH_RECORDS_PATH = ARTIFACT_DIR / "quarantine_download_hash_records.jsonl"
REJECTIONS_PATH = ARTIFACT_DIR / "quarantine_download_rejections.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "quarantine_download_summary.json"
PROOF_PATH = ARTIFACT_DIR / "quarantine_download_proof.jsonl"


def run_open_data_breakthrough_quarantine_downloader() -> dict[str, Any]:
    if not CANDIDATE_REGISTRY_PATH.exists():
        run_exhaustive_open_data_discovery_matrix()
    if not LICENSE_RESULTS_PATH.exists():
        run_machine_license_terms_verifier()
    candidates = read_jsonl(CANDIDATE_REGISTRY_PATH)
    license_results = {record["candidate_id"]: record for record in read_jsonl(LICENSE_RESULTS_PATH)}
    accepted = [
        candidate for candidate in candidates
        if candidate["machine_admissibility_status"] in {"accepted_machine_verified_open_ohlcv_candidate", "accepted_machine_verified_open_options_candidate", "accepted_machine_verified_context_candidate"}
        and license_results.get(candidate["candidate_id"], {}).get("license_terms_acceptance_allowed") is True
        and candidate.get("direct_download_url")
    ]
    plan = _plan(accepted)
    records: list[dict[str, Any]] = []
    hashes: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for candidate in accepted:
        target_dir = FAMILY_DIRS.get(candidate["dataset_family"], QUARANTINE_ROOT / "context")
        target = target_dir / f"{candidate['candidate_id']}.csv"
        try:
            result = _download(candidate["direct_download_url"], target)
            if contains_forbidden_content(target):
                rejections.append(_rejection(candidate, "terminal_block_forbidden_content", target))
                _move_to_rejected(target)
                continue
            records.append(_record(candidate, target, result))
            hashes.append(_hash_record(candidate, target))
        except Exception as exc:
            rejections.append(_rejection(candidate, f"download_failed:{type(exc).__name__}:{exc}", target))
    status = "no_machine_admissible_sources" if not accepted else ("completed" if not rejections else "completed_with_rejections")
    summary = {
        "artifact_type": "quarantine_download_summary",
        "download_version": "dopey-open-data-breakthrough-options-evidence-completion-v1",
        "download_status": status,
        "accepted_download_candidate_count": len(accepted),
        "download_attempt_count": len(accepted),
        "download_success_count": len(records),
        "download_rejection_count": len(rejections),
        "network_fetch_performed": any(str(candidate.get("direct_download_url", "")).startswith("http") for candidate in accepted),
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "alpha_vantage_excluded": True,
        "tradingview_excluded": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(PLAN_PATH, plan)
    write_jsonl(RECORDS_PATH, records)
    write_jsonl(HASH_RECORDS_PATH, hashes)
    write_jsonl(REJECTIONS_PATH, rejections)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("quarantine-download-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "quarantine_download_plan": str(PLAN_PATH),
        "quarantine_download_records": str(RECORDS_PATH),
        "quarantine_download_hash_records": str(HASH_RECORDS_PATH),
        "quarantine_download_rejections": str(REJECTIONS_PATH),
        "quarantine_download_summary": str(SUMMARY_PATH),
        "quarantine_download_proof": str(PROOF_PATH),
    }


def _download(url: str, target: Path) -> dict[str, Any]:
    if url.startswith("file://"):
        source = Path(url.removeprefix("file://"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return {"status_code": 200, "size_bytes": target.stat().st_size, "sha256": file_hash(target)}
    return fetch_https_file(url, target)


def _plan(accepted: list[dict[str, Any]]) -> dict[str, Any]:
    plan = {
        "artifact_type": "quarantine_download_plan",
        "plan_id": "open-data-breakthrough-quarantine-plan-v1",
        "download_candidate_count": len(accepted),
        "candidate_ids": [candidate["candidate_id"] for candidate in accepted],
        "quarantine_first": True,
        "no_credentials": True,
        "no_login": True,
        "no_api_keys": True,
        "no_scraping": True,
        "paper_only": True,
        "live_blocked": True,
    }
    plan["plan_hash"] = stable_hash(plan)
    return plan


def _record(candidate: dict[str, Any], target: Path, result: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "quarantine_download_records",
        "candidate_id": candidate["candidate_id"],
        "dataset_family": candidate["dataset_family"],
        "source_url": candidate["source_url"],
        "license_name": candidate["license_name"],
        "terms_url": candidate["terms_url"],
        "quarantine_path": str(target),
        "sha256": result["sha256"],
        "size_bytes": result["size_bytes"],
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _hash_record(candidate: dict[str, Any], target: Path) -> dict[str, Any]:
    record = {
        "artifact_type": "quarantine_download_hash_records",
        "candidate_id": candidate["candidate_id"],
        "path": str(target),
        "sha256": file_hash(target),
        "paper_only": True,
        "live_blocked": True,
    }
    record["hash_record_hash"] = stable_hash(record)
    return record


def _rejection(candidate: dict[str, Any], reason: str, target: Path) -> dict[str, Any]:
    record = {
        "artifact_type": "quarantine_download_rejections",
        "candidate_id": candidate["candidate_id"],
        "target": str(target),
        "reason_code": reason,
        "paper_only": True,
        "live_blocked": True,
    }
    record["rejection_hash"] = stable_hash(record)
    return record


def _move_to_rejected(path: Path) -> None:
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.replace(REJECTED_DIR / path.name)

