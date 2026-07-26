"""OpenBB provider capability and admissibility registry."""
from __future__ import annotations

from collections import Counter
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl

from .openbb_runtime_detector import detect_openbb_runtime


ARTIFACT_DIR = ARTIFACT_ROOT / "openbb_autonomy"
PROVIDER_REGISTRY_PATH = ARTIFACT_DIR / "openbb_provider_registry.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "openbb_provider_registry_summary.json"
PROOF_PATH = ARTIFACT_DIR / "openbb_provider_registry_proof.jsonl"
EXCLUDED_PROVIDERS = frozenset({"alpha_vantage", "alpaca", "databento", "tradingview"})


def run_openbb_provider_registry() -> dict[str, Any]:
    runtime = detect_openbb_runtime()
    records = [_provider_record(provider, runtime) for provider in _provider_inputs()]
    counts = Counter(record["provider_decision"] for record in records)
    accepted_probe = sum(1 for record in records if record["accepted_for_probe"])
    accepted_ingest = sum(1 for record in records if record["accepted_for_ingest"])
    summary = {
        "artifact_type": "openbb_provider_registry_summary",
        "registry_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "openbb_runtime_status": runtime["openbb_runtime_status"],
        "provider_count": len(records),
        "accepted_provider_count": accepted_probe,
        "accepted_ingest_provider_count": accepted_ingest,
        "rejected_provider_count": len(records) - accepted_probe,
        "provider_decision_counts": dict(sorted(counts.items())),
        "alpha_vantage_excluded": True,
        "alpaca_excluded": True,
        "databento_excluded": True,
        "tradingview_excluded": True,
        "global_install_attempted": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "network_fetch_performed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(PROVIDER_REGISTRY_PATH, records)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("openbb-provider-registry-proof-v1", summary["openbb_runtime_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "openbb_provider_registry": str(PROVIDER_REGISTRY_PATH),
        "openbb_provider_registry_summary": str(SUMMARY_PATH),
        "openbb_provider_registry_proof": str(PROOF_PATH),
    }


def _provider_inputs() -> list[dict[str, Any]]:
    return [
        _provider("sec", "openbb.equity.fundamental", "filings", False, False, False, False, False, True, True),
        _provider("fred", "openbb.economy", "macro/rates", False, False, False, False, False, True, True),
        _provider("yfinance", "openbb.equity.price.historical", "equities OHLCV", False, False, False, False, False, False, False),
        _provider("yfinance_etf", "openbb.etf.price.historical", "ETFs OHLCV", False, False, False, False, False, False, False),
        _provider("cboe", "openbb.derivatives.options.chains", "options chains", False, False, False, False, False, False, False),
        _provider("nasdaq_calendar", "openbb.equity.calendar", "earnings/corporate calendar", False, False, False, False, False, False, False),
        _provider("fmp", "openbb.equity.fundamental", "fundamentals", True, False, False, False, False, True, False),
        _provider("polygon", "openbb.equity.price.historical", "equities OHLCV", True, False, True, True, False, True, False),
        _provider("intrinio", "openbb.derivatives.options", "options historical quotes", True, False, True, True, False, True, False),
        _provider("alpha_vantage", "openbb.equity.price.historical", "equities OHLCV", True, False, False, False, False, False, False),
        _provider("alpaca", "openbb.trading", "equities OHLCV", True, True, False, False, True, False, False),
        _provider("databento", "openbb.equity.price.historical", "equities OHLCV", True, False, True, True, False, True, False),
        _provider("tradingview", "openbb.charting", "indexes", False, True, False, False, False, False, False),
        _provider("broker_adapter", "openbb.trading.account", "indexes", True, True, False, False, True, False, False),
    ]


def _provider(name: str, endpoint: str, family: str, api_key: bool, login: bool, payment: bool, subscription: bool, broker: bool, terms: bool, license_ok: bool) -> dict[str, Any]:
    return {
        "provider_name": name,
        "openbb_endpoint": endpoint,
        "dataset_family": family,
        "requires_api_key": api_key,
        "requires_login": login,
        "requires_payment": payment,
        "requires_subscription": subscription,
        "broker_adjacent": broker,
        "terms_machine_verifiable": terms,
        "license_machine_verifiable": license_ok,
    }


def _provider_record(provider: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    decision, reason = _decision(provider, runtime["openbb_runtime_status"])
    accepted_probe = decision in {"accepted_no_key_public_probe", "accepted_context_only"} and runtime["openbb_import_available"]
    accepted_ingest = decision == "accepted_no_key_public_probe" and provider["dataset_family"] in {"equities OHLCV", "ETFs OHLCV"} and runtime["openbb_import_available"]
    record = {
        "artifact_type": "openbb_provider_registry",
        "registry_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "provider_id": f"openbb-provider-{provider['provider_name']}",
        **provider,
        "source_machine_admissible": decision in {"accepted_no_key_public_probe", "accepted_context_only"},
        "accepted_for_probe": accepted_probe,
        "accepted_for_ingest": accepted_ingest,
        "provider_decision": decision,
        "reject_reason": reason,
        "openbb_runtime_status": runtime["openbb_runtime_status"],
        "global_install_attempted": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _decision(provider: dict[str, Any], runtime_status: str) -> tuple[str, str]:
    name = str(provider["provider_name"])
    if name in EXCLUDED_PROVIDERS:
        return f"rejected_{name}", f"{name}_excluded_by_policy"
    if provider["broker_adjacent"]:
        return "rejected_broker_adjacent", "broker_or_account_adjacent_provider"
    if provider["requires_api_key"]:
        return "rejected_requires_api_key", "api_key_required"
    if provider["requires_login"]:
        return "rejected_requires_login", "login_required"
    if provider["requires_payment"]:
        return "rejected_requires_payment", "payment_required"
    if provider["requires_subscription"]:
        return "rejected_subscription_or_proprietary", "subscription_or_proprietary"
    if not provider["terms_machine_verifiable"] or not provider["license_machine_verifiable"]:
        return "rejected_unknown_terms", "terms_or_license_not_machine_verifiable"
    if runtime_status == "not_installed_adapter_ready":
        return "openbb_runtime_not_available", "openbb_not_installed"
    if provider["dataset_family"] in {"macro/rates", "filings"}:
        return "accepted_context_only", ""
    return "accepted_no_key_public_probe", ""
