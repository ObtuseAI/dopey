"""Provider health diagnostics for public OHLCV intake."""
from __future__ import annotations

from collections import Counter

from dopey_runtime_bootstrap.active_python_resolver import preferred_repo_python
from dopey_runtime_bootstrap.venv_package_import_audit import repo_venv_import_status
from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl

from .public_ohlcv_provider_models import PRIMARY_UNIVERSE
from .stooq_ohlcv_provider_v2 import fetch_stooq_ohlcv_v2
from .yahoo_direct_csv_provider import fetch_yahoo_direct_ohlcv


ARTIFACT_DIR = ARTIFACT_ROOT / "market_intake"
RECORDS_PATH = ARTIFACT_DIR / "provider_health_diagnostics.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "provider_health_diagnostics_summary.json"
PROOF_PATH = ARTIFACT_DIR / "provider_health_diagnostics_proof.jsonl"


def run_provider_health_diagnostics(symbols: list[str], timeout_seconds: int) -> dict:
    imports = repo_venv_import_status(5)
    records: list[dict] = []
    for package in ["yfinance", "openbb", "pandas_datareader", "yahooquery", "requests_cache"]:
        records.append(_package_record(package, imports.get(package, "missing")))
    for symbol in symbols:
        yahoo = fetch_yahoo_direct_ohlcv(symbol, timeout_seconds)
        records.append(_provider_record(yahoo, "dns_connect_http_json_chart"))
        stooq = fetch_stooq_ohlcv_v2(symbol, timeout_seconds)
        records.append(_provider_record(stooq, "dns_connect_http_csv"))
    counts = Counter(str(record["status"]) for record in records)
    stooq_records = [record for record in records if record.get("provider") == "stooq_v2"]
    yahoo_records = [record for record in records if record.get("provider") == "yahoo_direct_csv"]
    summary = {
        "artifact_type": "provider_health_diagnostics_summary",
        "provider_health_diagnostics_version": "dopey-provider-health-diagnostics-v2",
        "python_executable_used": str(preferred_repo_python()),
        "yfinance_diagnosis": imports.get("yfinance", "missing"),
        "openbb_diagnosis": imports.get("openbb", "missing"),
        "stooq_diagnosis": _dominant_status(stooq_records),
        "yahoo_direct_diagnosis": _dominant_status(yahoo_records),
        "repo_venv_has_provider_packages": imports,
        "diagnostic_status_counts": dict(sorted(counts.items())),
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(RECORDS_PATH, records, False)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("provider-health-diagnostics", "complete", summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def _package_record(package: str, status: str) -> dict:
    record = {
        "artifact_type": "provider_health_diagnostic",
        "diagnostic_type": "package_import",
        "provider": package,
        "symbol": "",
        "status": status,
        "package_import_status": status,
        "python_executable_used": str(preferred_repo_python()),
        "exact_command_used": [str(preferred_repo_python()), "-c", f"import {package}"],
        "blocked_by_missing_package": status != "importable",
        "skipped_by_policy": False,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _provider_record(result: dict, diagnostic_type: str) -> dict:
    record = {
        "artifact_type": "provider_health_diagnostic",
        "diagnostic_type": diagnostic_type,
        "provider": result["provider"],
        "symbol": result["symbol"],
        "status": result["status"],
        "dns_connect_status": "attempted",
        "http_status": result["response_status"],
        "response_byte_count": result["response_bytes"],
        "csv_header_status": result["header_status"],
        "row_count": len(result["rows"]),
        "first_date": result["rows"][0]["date"] if result["rows"] else "",
        "last_date": result["rows"][-1]["date"] if result["rows"] else "",
        "exception_type": result["error"].split(":", 1)[0] if ":" in result["error"] else "",
        "timeout": result["status"] == "timeout",
        "package_import_status": result["package_import_status"],
        "python_executable_used": str(preferred_repo_python()),
        "exact_command_used": result["attempted_url"],
        "returned_empty_data": result["empty_response"],
        "blocked_by_missing_package": result["status"] == "missing_package",
        "skipped_by_policy": False,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _dominant_status(records: list[dict]) -> str:
    if not records:
        return "missing"
    counts = Counter(str(record["status"]) for record in records)
    return counts.most_common(1)[0][0]


def artifact_paths() -> dict[str, str]:
    return {
        "provider_health_diagnostics": str(RECORDS_PATH),
        "provider_health_diagnostics_summary": str(SUMMARY_PATH),
        "provider_health_diagnostics_proof": str(PROOF_PATH),
    }
