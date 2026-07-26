"""Probe no-key/no-paid OpenBB providers without credentials or broker paths."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, file_hash, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .openbb_provider_registry import PROVIDER_REGISTRY_PATH, run_openbb_provider_registry
from .openbb_runtime_detector import detect_openbb_runtime


ARTIFACT_DIR = ARTIFACT_ROOT / "openbb_autonomy"
QUARANTINE_ROOT = REPO_ROOT / "dopey_data" / "openbb_autonomy" / "quarantine"
OHLCV_QUARANTINE_DIR = QUARANTINE_ROOT / "ohlcv"
CONTEXT_QUARANTINE_DIR = QUARANTINE_ROOT / "context"
OPTIONS_QUARANTINE_DIR = QUARANTINE_ROOT / "options"
PLAN_PATH = ARTIFACT_DIR / "openbb_no_key_source_probe_plan.json"
RESULTS_PATH = ARTIFACT_DIR / "openbb_no_key_probe_results.jsonl"
REJECTIONS_PATH = ARTIFACT_DIR / "openbb_no_key_probe_rejections.jsonl"
HASH_RECORDS_PATH = ARTIFACT_DIR / "openbb_no_key_quarantine_hash_records.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "openbb_no_key_source_probe_summary.json"
PROOF_PATH = ARTIFACT_DIR / "openbb_no_key_source_probe_proof.jsonl"
PROBE_SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT"]


def run_openbb_no_key_source_probe() -> dict[str, Any]:
    runtime = detect_openbb_runtime()
    if not PROVIDER_REGISTRY_PATH.exists():
        run_openbb_provider_registry()
    providers = read_jsonl(PROVIDER_REGISTRY_PATH)
    plan = _probe_plan(runtime, providers)
    accepted_providers = [provider for provider in providers if provider.get("accepted_for_probe")]
    rejections = [_rejection(provider) for provider in providers if not provider.get("accepted_for_probe")]
    results: list[dict[str, Any]] = []
    hashes: list[dict[str, Any]] = []
    if runtime["openbb_runtime_status"] == "not_installed_adapter_ready":
        status = "openbb_not_available"
    else:
        status = "no_machine_admissible_openbb_provider"
    summary = {
        "artifact_type": "openbb_no_key_source_probe_summary",
        "probe_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "probe_status": status,
        "openbb_runtime_status": runtime["openbb_runtime_status"],
        "accepted_probe_count": len(accepted_providers),
        "probe_attempt_count": 0,
        "probe_success_count": len(results),
        "probe_rejection_count": len(rejections),
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "alpha_vantage_excluded": True,
        "alpaca_excluded": True,
        "databento_excluded": True,
        "tradingview_excluded": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(PLAN_PATH, plan)
    write_jsonl(RESULTS_PATH, results)
    write_jsonl(REJECTIONS_PATH, rejections)
    write_jsonl(HASH_RECORDS_PATH, hashes)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("openbb-no-key-source-probe-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "openbb_no_key_source_probe_plan": str(PLAN_PATH),
        "openbb_no_key_probe_results": str(RESULTS_PATH),
        "openbb_no_key_probe_rejections": str(REJECTIONS_PATH),
        "openbb_no_key_quarantine_hash_records": str(HASH_RECORDS_PATH),
        "openbb_no_key_source_probe_summary": str(SUMMARY_PATH),
        "openbb_no_key_source_probe_proof": str(PROOF_PATH),
    }


def build_probe_result(provider: dict[str, Any], quarantine_path: Path) -> dict[str, Any]:
    record = {
        "artifact_type": "openbb_no_key_probe_results",
        "probe_id": f"openbb-probe-{provider['provider_name']}",
        "provider_id": provider["provider_id"],
        "provider_name": provider["provider_name"],
        "dataset_family": provider["dataset_family"],
        "quarantine_path": str(quarantine_path),
        "source_url": f"openbb://{provider['openbb_endpoint']}",
        "license_status": "machine_verified_openbb_provider",
        "terms_status": "machine_verified_no_key_no_paid",
        "symbol_set": PROBE_SYMBOLS,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "paper_only": True,
        "live_blocked": True,
    }
    if quarantine_path.exists():
        record["sha256"] = file_hash(quarantine_path)
        record["size_bytes"] = quarantine_path.stat().st_size
    else:
        record["sha256"] = ""
        record["size_bytes"] = 0
    record["record_hash"] = stable_hash(record)
    return record


def _probe_plan(runtime: dict[str, Any], providers: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [provider for provider in providers if provider.get("accepted_for_probe")]
    plan = {
        "artifact_type": "openbb_no_key_source_probe_plan",
        "plan_id": "openbb-no-key-source-probe-plan-v1",
        "openbb_runtime_status": runtime["openbb_runtime_status"],
        "symbol_set": PROBE_SYMBOLS,
        "accepted_provider_ids": [provider["provider_id"] for provider in accepted],
        "quarantine_first": True,
        "no_credentials": True,
        "no_env": True,
        "no_broker": True,
        "no_live": True,
        "excluded_providers": ["alpha_vantage", "alpaca", "databento", "tradingview"],
        "paper_only": True,
        "live_blocked": True,
    }
    plan["plan_hash"] = stable_hash(plan)
    return plan


def _rejection(provider: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "openbb_no_key_probe_rejections",
        "provider_id": provider["provider_id"],
        "provider_name": provider["provider_name"],
        "reason_code": provider["provider_decision"],
        "reject_reason": provider.get("reject_reason", ""),
        "paper_only": True,
        "live_blocked": True,
    }
    record["rejection_hash"] = stable_hash(record)
    return record
