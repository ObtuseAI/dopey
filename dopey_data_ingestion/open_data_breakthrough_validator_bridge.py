"""Bridge breakthrough open-data manifests into DOPEY evidence status."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl

from .open_data_breakthrough_manifest_builder import run_open_data_breakthrough_manifest_builder


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_breakthrough"
SUMMARY_PATH = ARTIFACT_DIR / "open_data_validator_bridge_summary.json"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "open_data_validator_bridge_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "open_data_validator_bridge_proof.jsonl"


def run_open_data_breakthrough_validator_bridge() -> dict[str, Any]:
    manifest = run_open_data_breakthrough_manifest_builder()
    ohlcv_count = int(manifest["accepted_ohlcv_file_count"])
    options_count = int(manifest["accepted_options_file_count"])
    valid_real_dataset = ohlcv_count > 0
    options_valid = options_count > 0
    quote_allowed = bool(valid_real_dataset and options_valid)
    summary = {
        "artifact_type": "open_data_validator_bridge_summary",
        "validator_bridge_version": "dopey-open-data-breakthrough-options-evidence-completion-v1",
        "accepted_ohlcv_file_count": ohlcv_count,
        "accepted_options_file_count": options_count,
        "valid_real_dataset": valid_real_dataset,
        "history_activation_status": "open_ohlcv_history_activation_pass" if valid_real_dataset else "blocked_missing_open_ohlcv",
        "real_signal_validation_status": "open_real_signal_validation_pass" if valid_real_dataset else "blocked_missing_valid_real_history",
        "options_validation_status": "open_options_validation_pass" if options_valid else "blocked_no_machine_admissible_open_options_data",
        "quote_priced_backtest_allowed": quote_allowed,
        "model_priced_research_allowed": not quote_allowed,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    flags = _flags(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(QUALITY_FLAGS_PATH, flags)
    write_jsonl(PROOF_PATH, [proof_record("open-data-validator-bridge-proof-v1", summary["history_activation_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_data_validator_bridge_summary": str(SUMMARY_PATH),
        "open_data_validator_bridge_quality_flags": str(QUALITY_FLAGS_PATH),
        "open_data_validator_bridge_proof": str(PROOF_PATH),
    }


def _flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    if not summary["valid_real_dataset"]:
        reasons.append("blocked_missing_open_ohlcv")
    if summary["accepted_options_file_count"] == 0:
        reasons.append("blocked_no_machine_admissible_open_options_data")
    flags = []
    for index, reason in enumerate(reasons):
        record = {
            "artifact_type": "open_data_validator_bridge_quality_flags",
            "flag_id": f"open-data-bridge-{index:03d}",
            "reason_code": reason,
            "severity": "info",
            "paper_only": True,
            "live_blocked": True,
        }
        record["flag_hash"] = stable_hash(record)
        flags.append(record)
    return flags

