"""Activate real OHLCV history spine only after local validation passes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_data_ingestion.local_ohlcv_import_models import stable_local_ohlcv_hash
from dopey_data_ingestion.run_local_ohlcv_import_validator import (
    LOCAL_OHLCV_FILE_INVENTORY_PATH,
    LOCAL_OHLCV_IMPORT_DECISION_PATH,
    LOCAL_OHLCV_IMPORT_SUMMARY_PATH,
    LOCAL_OHLCV_QUALITY_RESULTS_PATH,
    LOCAL_OHLCV_LICENSE_PROVENANCE_RESULTS_PATH,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "history"
REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH = ARTIFACT_DIR / "real_ohlcv_history_spine_activation.json"
REAL_OHLCV_HISTORY_SYMBOL_COVERAGE_PATH = ARTIFACT_DIR / "real_ohlcv_history_symbol_coverage.jsonl"
REAL_OHLCV_HISTORY_DATE_COVERAGE_PATH = ARTIFACT_DIR / "real_ohlcv_history_date_coverage.jsonl"
REAL_OHLCV_HISTORY_ACTIVATION_BLOCKERS_PATH = ARTIFACT_DIR / "real_ohlcv_history_activation_blockers.jsonl"
REAL_OHLCV_HISTORY_ACTIVATION_QUALITY_FLAGS_PATH = ARTIFACT_DIR / "real_ohlcv_history_activation_quality_flags.jsonl"
REAL_OHLCV_HISTORY_ACTIVATION_PROOF_PATH = ARTIFACT_DIR / "real_ohlcv_history_activation_proof.jsonl"


def build_real_ohlcv_history_spine_activation() -> dict[str, Any]:
    summary = _load_json(LOCAL_OHLCV_IMPORT_SUMMARY_PATH)
    decision = _load_json(LOCAL_OHLCV_IMPORT_DECISION_PATH)
    inventory = _load_jsonl(LOCAL_OHLCV_FILE_INVENTORY_PATH)
    quality = _load_jsonl(LOCAL_OHLCV_QUALITY_RESULTS_PATH)
    provenance = _load_jsonl(LOCAL_OHLCV_LICENSE_PROVENANCE_RESULTS_PATH)
    local_status = str(summary.get("local_ohlcv_status") or decision.get("local_ohlcv_status") or "missing_local_ohlcv_files")
    valid = bool(summary.get("valid_real_dataset") is True and decision.get("history_spine_upgrade_allowed") is True)
    if not valid:
        activation_status = "blocked_missing_local_ohlcv" if local_status == "missing_local_ohlcv_files" else "blocked_local_ohlcv_validator_not_passed"
    else:
        activation_status = "real_ohlcv_history_spine_activation_pass"
    rows = sum(int(record.get("row_count", 0)) for record in inventory) if valid else 0
    symbols = sorted({symbol for record in quality for symbol in record.get("symbol_coverage", [])}) if valid else []
    activation = {
        "artifact_type": "real_ohlcv_history_spine_activation",
        "activation_version": "dopey-real-ohlcv-history-spine-activation-v1",
        "history_spine_activation_status": activation_status,
        "history_spine_upgrade_status": activation_status,
        "local_ohlcv_status": local_status,
        "valid_real_dataset": valid,
        "real_history_used": valid,
        "real_ohlcv_rows_activated": rows,
        "real_ohlcv_symbols_activated": len(symbols),
        "source_provenance_reference_count": len(provenance) if valid else 0,
        "file_hash_reference_count": len(inventory) if valid else 0,
        "synthetic_rows_generated": False,
        "fixture_rows_rewritten_as_real": False,
        "strategy_promotion_allowed": False,
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    activation["activation_hash"] = stable_local_ohlcv_hash(activation)
    return {
        "activation": activation,
        "symbol_coverage": _symbol_coverage(symbols, quality) if valid else [],
        "date_coverage": _date_coverage(quality) if valid else [],
        "blockers": [] if valid else [_blocker(activation_status, local_status)],
        "quality_flags": [] if valid else [_flag("real-ohlcv-history-activation-blocked", activation_status, local_status)],
        "proof": [_proof(activation)],
    }


def _symbol_coverage(symbols: list[str], quality: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for symbol in symbols:
        row_count = sum(1 for record in quality if symbol in record.get("symbol_coverage", []))
        record = {
            "artifact_type": "real_ohlcv_history_symbol_coverage",
            "coverage_id": f"real-ohlcv-symbol-{symbol.lower()}",
            "symbol": symbol,
            "validated_file_count": row_count,
            "data_source_tier": "local_real_history",
            "paper_only": True,
            "live_blocked": True,
        }
        record["coverage_hash"] = stable_local_ohlcv_hash(record)
        records.append(record)
    return records


def _date_coverage(quality: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in quality:
        coverage = {
            "artifact_type": "real_ohlcv_history_date_coverage",
            "coverage_id": f"real-ohlcv-date-{stable_local_ohlcv_hash(record)[:12]}",
            "local_file_path": record.get("local_file_path", ""),
            "date_range": record.get("date_range", {}),
            "missing_day_count": int(record.get("missing_day_count", 0)),
            "stale_symbol_count": int(record.get("stale_symbol_count", 0)),
            "paper_only": True,
            "live_blocked": True,
        }
        coverage["coverage_hash"] = stable_local_ohlcv_hash(coverage)
        records.append(coverage)
    return records


def _blocker(status: str, local_status: str) -> dict[str, Any]:
    record = {
        "artifact_type": "real_ohlcv_history_activation_blockers",
        "blocker_id": "real-ohlcv-history-activation-blocker-v1",
        "history_spine_activation_status": status,
        "history_spine_upgrade_status": status,
        "local_ohlcv_status": local_status,
        "valid_real_dataset": False,
        "real_history_used": False,
        "reason_code": "local_ohlcv_validator_not_passed",
        "required_fix": "Stage reviewed local OHLCV files and pass schema, quality, license, provenance, and hash gates.",
        "synthetic_rows_generated": False,
        "sample_rows_used": False,
        "network_fetch_performed": False,
        "credentials_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["blocker_hash"] = stable_local_ohlcv_hash(record)
    return record


def _flag(flag_id: str, status: str, local_status: str) -> dict[str, Any]:
    record = {
        "artifact_type": "real_ohlcv_history_activation_quality_flags",
        "flag_id": flag_id,
        "severity": "info",
        "reason_code": status,
        "local_ohlcv_status": local_status,
        "message": "History activation is blocked until local OHLCV validation passes.",
        "paper_only": True,
        "live_blocked": True,
    }
    record["flag_hash"] = stable_local_ohlcv_hash(record)
    return record


def _proof(activation: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "real_ohlcv_history_activation_proof",
        "proof_id": "real-ohlcv-history-activation-proof-v1",
        "history_spine_activation_status": activation["history_spine_activation_status"],
        "valid_real_dataset": activation["valid_real_dataset"],
        "real_history_used": activation["real_history_used"],
        "strategy_promotion_allowed": False,
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
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


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
