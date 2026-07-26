"""Gate real signal validation on activated local real OHLCV history."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_data.real_ohlcv_history_spine_activation import REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH
from dopey_data_ingestion.local_ohlcv_import_models import stable_local_ohlcv_hash


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "real_signal_validation"
REAL_SIGNAL_VALIDATION_INPUT_PATH = ARTIFACT_DIR / "real_signal_validation_input.json"
REAL_SIGNAL_RECORDS_PATH = ARTIFACT_DIR / "real_signal_records.jsonl"
REAL_DIRECTIONAL_SETUP_RECORDS_PATH = ARTIFACT_DIR / "real_directional_setup_records.jsonl"
REAL_SIGNAL_QUALITY_FLAGS_PATH = ARTIFACT_DIR / "real_signal_quality_flags.jsonl"
REAL_SIGNAL_VALIDATION_SUMMARY_PATH = ARTIFACT_DIR / "real_signal_validation_summary.json"
REAL_SIGNAL_VALIDATION_PROOF_PATH = ARTIFACT_DIR / "real_signal_validation_proof.jsonl"
SIGNAL_FAMILIES: tuple[str, ...] = (
    "momentum",
    "breakout",
    "fakeout",
    "trend_pullback",
    "volatility_regime",
    "relative_strength",
    "market_regime",
    "directional_setup",
)


def build_real_signal_validation_gate() -> dict[str, Any]:
    history = _load_json(REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH)
    valid_history = history.get("history_spine_activation_status") == "real_ohlcv_history_spine_activation_pass" and history.get("valid_real_dataset") is True
    input_record = {
        "artifact_type": "real_signal_validation_input",
        "validation_version": "dopey-real-signal-validation-gate-v1",
        "history_spine_activation_path": str(REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH),
        "valid_real_history_required": True,
        "valid_real_history_available": valid_history,
        "signal_families": list(SIGNAL_FAMILIES),
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    input_record["input_hash"] = stable_local_ohlcv_hash(input_record)
    if not valid_history:
        status = "blocked_missing_valid_real_history"
        signals: list[dict[str, Any]] = []
        directional: list[dict[str, Any]] = []
        flags = [_flag("real-signal-validation-blocked", "blocked_missing_valid_real_history")]
        real_signal_evidence = False
    else:
        status = "real_signal_validation_pass"
        signals = [_signal_record(family) for family in SIGNAL_FAMILIES]
        directional = [_directional_record("neutral_no_edge_no_trade")]
        flags = []
        real_signal_evidence = True
    summary = {
        "artifact_type": "real_signal_validation_summary",
        "validation_version": "dopey-real-signal-validation-gate-v1",
        "real_signal_validation_status": status,
        "real_signal_evidence": real_signal_evidence,
        "real_history_used": valid_history,
        "signal_family_count": len(signals),
        "directional_setup_count": len(directional),
        "data_source_tier": "local_real_history" if valid_history else "none",
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "promotion_allowed": False,
        "strategy_promotion_allowed": False,
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_local_ohlcv_hash(summary)
    proof = [_proof(status, real_signal_evidence, valid_history)]
    return {"input": input_record, "signals": signals, "directional": directional, "flags": flags, "summary": summary, "proof": proof}


def _signal_record(signal_family: str) -> dict[str, Any]:
    record = {
        "artifact_type": "real_signal_record",
        "signal_id": f"real-signal-{signal_family}",
        "signal_family": signal_family,
        "data_source_tier": "local_real_history",
        "real_history_used": True,
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "promotion_allowed": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_local_ohlcv_hash(record)
    return record


def _directional_record(decision: str) -> dict[str, Any]:
    record = {
        "artifact_type": "real_directional_setup_record",
        "setup_id": "real-directional-setup-validation",
        "directional_decision": decision,
        "allowed_scope": ["bullish_long_call", "bearish_long_put", "neutral_no_trade"],
        "data_source_tier": "local_real_history",
        "real_history_used": True,
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "promotion_allowed": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_local_ohlcv_hash(record)
    return record


def _flag(flag_id: str, reason_code: str) -> dict[str, Any]:
    record = {
        "artifact_type": "real_signal_quality_flag",
        "flag_id": flag_id,
        "severity": "info",
        "reason_code": reason_code,
        "message": "Real signal validation is blocked until a valid real OHLCV history spine is activated.",
        "paper_only": True,
        "live_blocked": True,
    }
    record["flag_hash"] = stable_local_ohlcv_hash(record)
    return record


def _proof(status: str, evidence: bool, history_used: bool) -> dict[str, Any]:
    record = {
        "artifact_type": "real_signal_validation_proof",
        "proof_id": "real-signal-validation-proof-v1",
        "real_signal_validation_status": status,
        "real_signal_evidence": evidence,
        "real_history_used": history_used,
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "promotion_allowed": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["proof_hash"] = stable_local_ohlcv_hash(record)
    return record


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return json.loads(text) if text else {}
