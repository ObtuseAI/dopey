"""Unlock gate for quote-priced options evidence."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl
from dopey_data_ingestion.open_data_breakthrough_validator_bridge import run_open_data_breakthrough_validator_bridge


ARTIFACT_DIR = ARTIFACT_ROOT / "backtest"
SUMMARY_PATH = ARTIFACT_DIR / "quote_priced_options_unlock_gate.json"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "quote_priced_options_unlock_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "quote_priced_options_unlock_proof.jsonl"


def run_quote_priced_options_unlock_gate() -> dict[str, Any]:
    bridge = run_open_data_breakthrough_validator_bridge()
    has_options = int(bridge["accepted_options_file_count"]) > 0
    has_ohlcv = int(bridge["accepted_ohlcv_file_count"]) > 0
    unlocked = bool(has_options and has_ohlcv and bridge["quote_priced_backtest_allowed"])
    status = "quote_priced_options_unlocked" if unlocked else "blocked_no_machine_admissible_open_options_data"
    if has_options and not has_ohlcv:
        status = "blocked_missing_underlying_open_ohlcv_context"
    summary = {
        "artifact_type": "quote_priced_options_unlock_gate",
        "unlock_gate_version": "dopey-open-data-breakthrough-options-evidence-completion-v1",
        "quote_priced_options_status": status,
        "accepted_open_historical_options_data_exists": has_options,
        "options_schema_validation_passed": has_options,
        "options_license_provenance_passed": has_options,
        "options_sample_size_sufficient": has_options,
        "bid_ask_volume_open_interest_valid": has_options,
        "underlying_ohlcv_context_exists": has_ohlcv,
        "honest_backtester_contract_mapping_ready": unlocked,
        "quote_priced_backtest_allowed": unlocked,
        "model_priced_research_allowed": not unlocked,
        "next_recommended_target": "DOPEY_REAL_OPTIONS_HONEST_BACKTESTER_V1" if unlocked else "DOPEY_MODEL_PRICED_OPTIONS_RESEARCH_EXPANSION_V2",
        "strategy_promotion_allowed": False,
        "live_promotion_allowed": False,
        "profitability_claim": False,
        "live_readiness_claim": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    flags = _quality_flags(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(QUALITY_FLAGS_PATH, flags)
    write_jsonl(PROOF_PATH, [proof_record("quote-priced-options-unlock-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "quote_priced_options_unlock_gate": str(SUMMARY_PATH),
        "quote_priced_options_unlock_quality_flags": str(QUALITY_FLAGS_PATH),
        "quote_priced_options_unlock_proof": str(PROOF_PATH),
    }


def _quality_flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[str] = []
    if not summary["accepted_open_historical_options_data_exists"]:
        reasons.append("no_machine_admissible_open_options_data")
    if not summary["underlying_ohlcv_context_exists"]:
        reasons.append("missing_underlying_open_ohlcv_context")
    records: list[dict[str, Any]] = []
    for index, reason in enumerate(reasons):
        record = {
            "artifact_type": "quote_priced_options_unlock_quality_flags",
            "flag_id": f"quote-unlock-{index:03d}",
            "reason_code": reason,
            "severity": "info",
            "quote_priced_backtest_allowed": False,
            "model_priced_research_allowed": True,
            "paper_only": True,
            "live_blocked": True,
        }
        record["flag_hash"] = stable_hash(record)
        records.append(record)
    return records
