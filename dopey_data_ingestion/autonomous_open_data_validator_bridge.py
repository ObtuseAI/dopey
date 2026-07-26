"""Bridge autonomous open-data outputs into validation/history/signal status."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_json, safety_state, stable_hash, write_json, write_jsonl

from .autonomous_open_data_manifest_builder import MANIFEST_PATH, run_autonomous_open_data_manifest_builder
from .autonomous_open_data_quarantine_fetcher import run_autonomous_open_data_quarantine_fetcher
from .autonomous_open_data_source_discovery import run_autonomous_open_data_source_discovery
from .autonomous_open_ohlcv_normalizer import run_autonomous_open_ohlcv_normalizer


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_autonomy"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_open_data_validator_bridge_summary.json"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "autonomous_open_data_validator_bridge_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "autonomous_open_data_validator_bridge_proof.jsonl"


def run_autonomous_open_data_validator_bridge() -> dict[str, Any]:
    source = run_autonomous_open_data_source_discovery()
    fetch = run_autonomous_open_data_quarantine_fetcher()
    normalizer = run_autonomous_open_ohlcv_normalizer()
    manifest_summary = run_autonomous_open_data_manifest_builder()
    manifest = read_json(MANIFEST_PATH)
    valid_real_dataset = bool(manifest.get("manifest_status") == "final_manifest_machine_verified" and manifest.get("row_count", 0) > 0)
    history_status = "real_ohlcv_history_spine_activation_pass" if valid_real_dataset else "blocked_missing_local_ohlcv"
    signal_status = "real_signal_validation_pass" if valid_real_dataset else "blocked_missing_valid_real_history"
    status = "autonomous_open_data_validated" if valid_real_dataset else "no_accepted_open_data_sources"
    flags = _flags(status, source, fetch, normalizer, manifest_summary)
    summary = {
        "artifact_type": "autonomous_open_data_validator_bridge_summary",
        "validator_bridge_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "autonomous_open_data_status": status,
        "open_data_candidate_count": source["open_data_candidate_count"],
        "open_data_accepted_count": source["open_data_accepted_count"],
        "accepted_ingest_source_count": source["accepted_ingest_source_count"],
        "open_data_fetch_count": fetch["fetch_success_count"],
        "accepted_ohlcv_file_count": normalizer["accepted_ohlcv_file_count"],
        "manifest_status": manifest_summary["manifest_status"],
        "valid_real_dataset": valid_real_dataset,
        "history_activation_status": history_status,
        "history_spine_activation_status": history_status,
        "real_history_used": valid_real_dataset,
        "real_signal_validation_status": signal_status,
        "real_signal_evidence": valid_real_dataset,
        "quote_priced_backtest_allowed": False,
        "network_fetch_performed": bool(fetch["network_fetch_performed"]),
        "alpha_vantage_excluded": True,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(QUALITY_FLAGS_PATH, flags)
    write_jsonl(PROOF_PATH, [proof_record("autonomous-open-data-validator-bridge-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_open_data_validator_bridge_summary": str(SUMMARY_PATH),
        "autonomous_open_data_validator_bridge_quality_flags": str(QUALITY_FLAGS_PATH),
        "autonomous_open_data_validator_bridge_proof": str(PROOF_PATH),
    }


def _flags(status: str, source: dict[str, Any], fetch: dict[str, Any], normalizer: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    if status != "autonomous_open_data_validated":
        reasons.append("no_valid_autonomous_open_ohlcv")
    if source["accepted_ingest_source_count"] == 0:
        reasons.append("no_accepted_ingest_source")
    if fetch["fetch_success_count"] == 0:
        reasons.append(fetch["fetch_status"])
    if normalizer["accepted_ohlcv_file_count"] == 0:
        reasons.append(normalizer["normalization_status"])
    if manifest["manifest_status"] != "final_manifest_machine_verified":
        reasons.append(manifest["manifest_status"])
    flags: list[dict[str, Any]] = []
    for index, reason in enumerate(sorted(set(reasons))):
        record = {
            "artifact_type": "autonomous_open_data_validator_bridge_quality_flags",
            "flag_id": f"autonomous-open-data-bridge-{index:03d}",
            "severity": "info",
            "reason_code": reason,
            "paper_only": True,
            "live_blocked": True,
        }
        record["flag_hash"] = stable_hash(record)
        flags.append(record)
    return flags

