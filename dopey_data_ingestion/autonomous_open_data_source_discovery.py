"""Discover admissible open-data sources without manual review or credentials."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, data_outcome, open_data_candidates, proof_record, safety_state, stable_hash, write_json, write_jsonl

from .autonomous_open_data_source_scorecard import build_autonomous_open_data_source_scorecard


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_autonomy"
CANDIDATES_PATH = ARTIFACT_DIR / "autonomous_open_data_candidate_registry.jsonl"
LICENSE_RESULTS_PATH = ARTIFACT_DIR / "autonomous_open_data_license_results.jsonl"
PROVENANCE_RESULTS_PATH = ARTIFACT_DIR / "autonomous_open_data_provenance_results.jsonl"
SCORECARD_PATH = ARTIFACT_DIR / "autonomous_open_data_source_scorecard.json"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_open_data_source_summary.json"
PROOF_PATH = ARTIFACT_DIR / "autonomous_open_data_source_proof.jsonl"


def run_autonomous_open_data_source_discovery() -> dict[str, Any]:
    candidate_inputs = open_data_candidates()
    records = [_candidate_record(candidate) for candidate in candidate_inputs]
    license_records = [_license_record(record) for record in records]
    provenance_records = [_provenance_record(record) for record in records]
    scorecard = build_autonomous_open_data_source_scorecard(records)
    summary = {
        "artifact_type": "autonomous_open_data_source_summary",
        "source_discovery_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "open_data_candidate_count": len(records),
        "open_data_accepted_count": scorecard["accepted_source_count"],
        "accepted_ingest_source_count": scorecard["accepted_ingest_source_count"],
        "daily_ohlcv_ingest_source_count": scorecard["daily_ohlcv_ingest_source_count"],
        "context_only_source_count": sum(1 for record in records if record["outcome"] == "accepted_for_context_only"),
        "rejected_source_count": scorecard["rejected_source_count"],
        "quarantined_source_count": scorecard["quarantined_source_count"],
        "alpha_vantage_excluded": True,
        "network_fetch_performed": False,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(CANDIDATES_PATH, records)
    write_jsonl(LICENSE_RESULTS_PATH, license_records)
    write_jsonl(PROVENANCE_RESULTS_PATH, provenance_records)
    write_json(SCORECARD_PATH, scorecard)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("autonomous-open-data-source-proof-v1", "completed", summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_open_data_candidate_registry": str(CANDIDATES_PATH),
        "autonomous_open_data_license_results": str(LICENSE_RESULTS_PATH),
        "autonomous_open_data_provenance_results": str(PROVENANCE_RESULTS_PATH),
        "autonomous_open_data_source_scorecard": str(SCORECARD_PATH),
        "autonomous_open_data_source_summary": str(SUMMARY_PATH),
        "autonomous_open_data_source_proof": str(PROOF_PATH),
    }


def _candidate_record(candidate) -> dict[str, Any]:
    outcome = data_outcome(candidate)
    record = {
        "artifact_type": "autonomous_open_data_candidate_registry",
        "source_id": candidate.source_id,
        "source_name": candidate.name,
        "dataset_family": candidate.family,
        "source_url": candidate.source_url,
        "license_id": candidate.license_id,
        "outcome": outcome,
        "direct_download_url": candidate.direct_download_url,
        "adjusted_close_semantics_known": candidate.adjusted_close_semantics_known,
        "machine_readable_license": candidate.machine_readable_license,
        "machine_readable_terms": candidate.machine_readable_terms,
        "credentials_required": candidate.credentials_required,
        "paid_or_proprietary": candidate.paid_or_proprietary,
        "broker_or_live_source": candidate.broker_or_live_source,
        "scrape_only": candidate.scrape_only,
        "sample_or_fixture": candidate.sample_or_fixture,
        "paper_only": True,
        "live_blocked": True,
    }
    record["candidate_hash"] = stable_hash(record)
    return record


def _license_record(record: dict[str, Any]) -> dict[str, Any]:
    license_record = {
        "artifact_type": "autonomous_open_data_license_results",
        "source_id": record["source_id"],
        "license_id": record["license_id"],
        "outcome": record["outcome"],
        "license_machine_verified": record["machine_readable_license"],
        "unknown_license_rejected": record["outcome"] == "rejected_unknown_license",
        "paper_only": True,
        "live_blocked": True,
    }
    license_record["license_hash"] = stable_hash(license_record)
    return license_record


def _provenance_record(record: dict[str, Any]) -> dict[str, Any]:
    provenance_record = {
        "artifact_type": "autonomous_open_data_provenance_results",
        "source_id": record["source_id"],
        "source_url": record["source_url"],
        "outcome": record["outcome"],
        "credentials_required": record["credentials_required"],
        "broker_or_live_source": record["broker_or_live_source"],
        "sample_or_fixture": record["sample_or_fixture"],
        "provenance_machine_verified": bool(record["machine_readable_terms"] and record["source_url"]),
        "paper_only": True,
        "live_blocked": True,
    }
    provenance_record["provenance_hash"] = stable_hash(provenance_record)
    return provenance_record

