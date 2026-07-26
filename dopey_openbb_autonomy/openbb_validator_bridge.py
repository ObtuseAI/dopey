"""Bridge OpenBB accepted data into DOPEY evidence status."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl

from .openbb_evidence_manifest_builder import run_openbb_evidence_manifest_builder


ARTIFACT_DIR = ARTIFACT_ROOT / "openbb_autonomy"
SUMMARY_PATH = ARTIFACT_DIR / "openbb_validator_bridge_summary.json"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "openbb_validator_bridge_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "openbb_validator_bridge_proof.jsonl"


def run_openbb_validator_bridge() -> dict[str, Any]:
    manifest = run_openbb_evidence_manifest_builder()
    accepted_files = int(manifest["openbb_accepted_ohlcv_file_count"])
    valid = accepted_files > 0
    summary = {
        "artifact_type": "openbb_validator_bridge_summary",
        "bridge_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "openbb_accepted_ohlcv_file_count": accepted_files,
        "openbb_valid_real_dataset": valid,
        "openbb_history_activation_status": "openbb_history_activation_pass" if valid else "blocked_no_openbb_accepted_ohlcv",
        "openbb_real_signal_validation_status": "openbb_real_signal_validation_pass" if valid else "blocked_missing_valid_real_history",
        "openbb_quote_priced_options_status": "blocked_no_openbb_accepted_options_quotes",
        "openbb_model_priced_research_allowed": True,
        "strategy_promotion_allowed": False,
        "live_promotion_allowed": False,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    flags = _flags(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(QUALITY_FLAGS_PATH, flags)
    write_jsonl(PROOF_PATH, [proof_record("openbb-validator-bridge-proof-v1", summary["openbb_history_activation_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "openbb_validator_bridge_summary": str(SUMMARY_PATH),
        "openbb_validator_bridge_quality_flags": str(QUALITY_FLAGS_PATH),
        "openbb_validator_bridge_proof": str(PROOF_PATH),
    }


def _flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    if not summary["openbb_valid_real_dataset"]:
        reasons.append("blocked_no_openbb_accepted_ohlcv")
    reasons.append("openbb_quote_priced_options_blocked")
    flags: list[dict[str, Any]] = []
    for index, reason in enumerate(reasons):
        record = {
            "artifact_type": "openbb_validator_bridge_quality_flags",
            "flag_id": f"openbb-validator-{index:03d}",
            "reason_code": reason,
            "severity": "info",
            "paper_only": True,
            "live_blocked": True,
        }
        record["flag_hash"] = stable_hash(record)
        flags.append(record)
    return flags
