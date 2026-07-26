"""Provider-neutral free/public data candidates. No fetch or credential path."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT


FREE_DATA_STACK_VERSION = "dopey-free-data-candidate-gate-v1"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "free_data"
FREE_DATA_CANDIDATE_REGISTRY_PATH = ARTIFACT_DIR / "free_data_candidate_registry.jsonl"
FREE_DATA_CANDIDATE_SUMMARY_PATH = ARTIFACT_DIR / "free_data_candidate_summary.json"


@dataclass(frozen=True)
class FreeDataCandidate:
    artifact_type: str
    free_data_stack_version: str
    source_name: str
    dataset_family: str
    access_mode: str
    license_status: str
    provenance_status: str
    terms_review_required: bool
    redistribution_allowed: str
    commercial_use_allowed: str
    historical_depth: str
    coverage_limitations: str
    survivorship_bias_risk: str
    staleness_risk: str
    schema_risk: str
    evidence_allowed: bool
    manual_review_required: bool
    not_fetched_by_dopey: bool
    credentials_required: bool
    paper_only: bool
    live_blocked: bool
    candidate_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["free_data_stack_version"] = FREE_DATA_STACK_VERSION
        clear = record["license_status"] == "reviewed_allowed" and record["provenance_status"] == "complete"
        record["evidence_allowed"] = bool(clear and record["evidence_allowed"])
        record["manual_review_required"] = bool(record["manual_review_required"] or not clear)
        record["not_fetched_by_dopey"] = True
        record["credentials_required"] = False
        record["paper_only"] = True
        record["live_blocked"] = True
        record["candidate_hash"] = stable_free_data_hash(record)
        return record


def build_free_data_candidates() -> list[FreeDataCandidate]:
    return [
        _candidate("manual exchange or ETF OHLCV export", "daily_ohlcv", "manual_download_only", "manual_review_required", "operator_attested_required", "unknown", "unknown", "operator-selected history", "file coverage only", "medium", "medium", "medium"),
        _candidate("SEC EDGAR filings/fundamentals metadata", "fundamentals", "public_bulk_file", "manual_review_required", "source_url_required", "unknown", "unknown", "public filings metadata depth varies", "not normalized fundamentals by default", "low", "medium", "high"),
        _candidate("FRED public macro CSV export", "market_context", "manual_download_only", "manual_review_required", "source_url_required", "unknown", "unknown", "series dependent", "macro/rates only", "low", "low", "medium"),
        _candidate("Stooq-style free OHLCV candidate", "daily_ohlcv", "manual_download_only", "manual_review_required", "source_url_required", "unknown", "unknown", "source dependent", "coverage and adjustment rules require review", "medium", "medium", "high"),
        _candidate("Yahoo Finance manual-download candidate", "daily_ohlcv", "manual_download_only", "manual_review_required", "source_url_required", "unknown", "unknown", "source dependent", "terms and adjustments require review", "medium", "medium", "high"),
        _candidate("Nasdaq public downloadable reference files if license permits", "benchmark_and_universe_metadata", "public_bulk_file", "manual_review_required", "source_url_required", "unknown", "unknown", "file dependent", "reference metadata only unless licensed", "medium", "medium", "medium"),
        _candidate("CBOE public reference files if license permits", "options_reference", "manual_download_only", "manual_review_required", "source_url_required", "unknown", "unknown", "file dependent", "not historical options quotes by default", "medium", "medium", "medium"),
        _candidate("GitHub-hosted datasets with explicit license/provenance", "operator_supplied_dataset", "operator_supplied_file", "manual_review_required", "license_file_and_source_url_required", "unknown", "unknown", "repository dependent", "high license and staleness risk", "high", "high", "high"),
    ]


def free_data_candidate_records() -> list[dict[str, Any]]:
    return [candidate.to_dict() for candidate in build_free_data_candidates()]


def write_free_data_candidate_registry() -> dict[str, Any]:
    records = free_data_candidate_records()
    summary = {
        "artifact_type": "free_data_candidate_summary",
        "free_data_stack_version": FREE_DATA_STACK_VERSION,
        "free_data_candidate_count": len(records),
        "free_data_evidence_allowed_count": sum(1 for record in records if record["evidence_allowed"]),
        "free_data_manual_review_required_count": sum(1 for record in records if record["manual_review_required"]),
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_free_data_hash(summary)
    _write_jsonl(FREE_DATA_CANDIDATE_REGISTRY_PATH, records)
    _write_json(FREE_DATA_CANDIDATE_SUMMARY_PATH, summary)
    return {**summary, "artifact_paths": {
        "free_data_candidate_registry": str(FREE_DATA_CANDIDATE_REGISTRY_PATH),
        "free_data_candidate_summary": str(FREE_DATA_CANDIDATE_SUMMARY_PATH),
    }}


def _candidate(
    source_name: str,
    dataset_family: str,
    access_mode: str,
    license_status: str,
    provenance_status: str,
    redistribution_allowed: str,
    commercial_use_allowed: str,
    historical_depth: str,
    coverage_limitations: str,
    survivorship_bias_risk: str,
    staleness_risk: str,
    schema_risk: str,
) -> FreeDataCandidate:
    return FreeDataCandidate(
        artifact_type="free_data_candidate_registry",
        free_data_stack_version=FREE_DATA_STACK_VERSION,
        source_name=source_name,
        dataset_family=dataset_family,
        access_mode=access_mode,
        license_status=license_status,
        provenance_status=provenance_status,
        terms_review_required=True,
        redistribution_allowed=redistribution_allowed,
        commercial_use_allowed=commercial_use_allowed,
        historical_depth=historical_depth,
        coverage_limitations=coverage_limitations,
        survivorship_bias_risk=survivorship_bias_risk,
        staleness_risk=staleness_risk,
        schema_risk=schema_risk,
        evidence_allowed=False,
        manual_review_required=True,
        not_fetched_by_dopey=True,
        credentials_required=False,
        paper_only=True,
        live_blocked=True,
        candidate_hash="",
    )


def stable_free_data_hash(payload: dict[str, Any]) -> str:
    stripped = {key: value for key, value in payload.items() if key not in {"candidate_hash", "result_hash", "summary_hash", "proof_hash"}}
    encoded = json.dumps(stripped, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
