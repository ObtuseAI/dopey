"""Local contract for future options chain and quote imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT


OPTIONS_CONTRACT_VERSION = "dopey-options-chain-quote-import-contract-v1"
OPTIONS_CHAIN_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chain"
OPTIONS_QUOTES_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_quotes"
OPTIONS_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json"
OPTIONS_CHAIN_REQUIRED_FIELDS: list[str] = [
    "snapshot_date",
    "underlying_symbol",
    "expiration_date",
    "strike",
    "option_type",
    "bid",
    "ask",
    "mid",
    "last",
    "volume",
    "open_interest",
    "implied_volatility",
    "source",
    "provider_record_id",
]
OPTIONS_CHAIN_OPTIONAL_FIELDS: list[str] = ["delta", "gamma", "theta", "vega", "rho"]
OPTIONS_QUOTES_REQUIRED_FIELDS: list[str] = [
    "timestamp",
    "underlying_symbol",
    "contract_symbol",
    "expiration_date",
    "strike",
    "option_type",
    "bid",
    "ask",
    "bid_size",
    "ask_size",
    "last",
    "volume",
    "open_interest",
    "source",
]


def build_options_chain_quote_contract() -> dict[str, Any]:
    OPTIONS_CHAIN_DIR.mkdir(parents=True, exist_ok=True)
    OPTIONS_QUOTES_DIR.mkdir(parents=True, exist_ok=True)
    OPTIONS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not OPTIONS_MANIFEST_PATH.exists():
        OPTIONS_MANIFEST_PATH.write_text(json.dumps(_manifest_template(), sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files_present = _options_files_present()
    contract = {
        "artifact_type": "options_chain_quote_contract",
        "options_contract_version": OPTIONS_CONTRACT_VERSION,
        "options_contract_status": "options_import_contract_ready",
        "chain_folder": "dopey_data/real/raw/options_chain/",
        "quotes_folder": "dopey_data/real/raw/options_quotes/",
        "manifest_path": "dopey_data/real/manifests/options_data_manifest.json",
        "options_data_files_present": files_present,
        "options_data_ingested": False,
        "options_data_validated": False,
        "quote_priced_backtest_allowed": False,
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    contract["contract_hash"] = _hash(contract)
    schemas = [_schema("historical_options_chain", OPTIONS_CHAIN_REQUIRED_FIELDS, OPTIONS_CHAIN_OPTIONAL_FIELDS), _schema("historical_options_quotes", OPTIONS_QUOTES_REQUIRED_FIELDS, [])]
    gates = [_gate(name) for name in [
        "bid_ask_nonnegative",
        "ask_ge_bid",
        "mid_between_bid_and_ask",
        "strike_positive",
        "expiry_ge_snapshot_or_quote_date",
        "option_type_call_or_put",
        "implied_volatility_nonnegative_if_present",
        "volume_nonnegative",
        "open_interest_nonnegative",
        "contract_uniqueness",
        "no_sample_only_rows",
        "no_credentials_or_tokens",
        "license_provenance_required",
    ]]
    decision = {
        "artifact_type": "options_import_readiness_decision",
        "options_contract_version": OPTIONS_CONTRACT_VERSION,
        "options_import_readiness_decision": "options_import_not_started" if not files_present else "manual_review_required",
        "options_data_files_present": files_present,
        "options_data_ingested": False,
        "options_data_validated": False,
        "quote_priced_backtest_allowed": False,
        "reason_codes": ["options_contract_ready_import_not_started"] if not files_present else ["options_files_present_validation_not_run"],
        "paper_only": True,
        "live_blocked": True,
    }
    decision["decision_hash"] = _hash(decision)
    summary = {
        "artifact_type": "options_data_contract_summary",
        "options_contract_version": OPTIONS_CONTRACT_VERSION,
        "options_contract_status": "options_import_contract_ready",
        "options_data_files_present": files_present,
        "options_data_ingested": False,
        "options_data_validated": False,
        "quote_priced_backtest_allowed": False,
        "schema_contract_count": len(schemas),
        "quality_gate_count": len(gates),
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = _hash(summary)
    proof = [{
        "artifact_type": "options_data_contract_proof",
        "proof_id": "options-data-contract-proof-v1",
        "options_contract_status": "options_import_contract_ready",
        "options_data_files_present": files_present,
        "options_data_ingested": False,
        "options_data_validated": False,
        "quote_priced_backtest_allowed": False,
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }]
    proof[0]["proof_hash"] = _hash(proof[0])
    return {"contract": contract, "schemas": schemas, "gates": gates, "decision": decision, "summary": summary, "proof": proof}


def _options_files_present() -> bool:
    for folder in [OPTIONS_CHAIN_DIR, OPTIONS_QUOTES_DIR]:
        if folder.exists() and any(path.is_file() for path in folder.rglob("*")):
            return True
    return False


def _schema(dataset_family: str, required_fields: list[str], optional_fields: list[str]) -> dict[str, Any]:
    record = {
        "artifact_type": "options_schema_contract",
        "schema_id": f"options-schema-{dataset_family}",
        "options_contract_version": OPTIONS_CONTRACT_VERSION,
        "dataset_family": dataset_family,
        "required_fields": required_fields,
        "optional_fields": optional_fields,
        "sample_rows_allowed_as_real": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["schema_hash"] = _hash(record)
    return record


def _gate(gate_name: str) -> dict[str, Any]:
    record = {
        "artifact_type": "options_quality_gate_plan",
        "gate_id": f"options-gate-{gate_name}",
        "gate_name": gate_name,
        "status": "gate_defined_not_run",
        "paper_only": True,
        "live_blocked": True,
    }
    record["gate_hash"] = _hash(record)
    return record


def _manifest_template() -> dict[str, Any]:
    return {
        "manifest_id": "OPTIONS_TEMPLATE_ONLY",
        "provider_name": "REQUIRED_LICENSED_PROVIDER_NAME",
        "provider_terms_reviewed": False,
        "license_status": "unknown",
        "local_file_paths": [],
        "file_hashes": {},
        "not_credentials": True,
        "not_live_data": True,
        "not_network_fetched_by_dopey": True,
        "paper_only": True,
        "live_blocked": True,
        "template_only": True,
        "not_real_data": True,
    }


def _hash(record: dict[str, Any]) -> str:
    cleaned = {key: value for key, value in record.items() if not key.endswith("_hash")}
    return hashlib.sha256(json.dumps(cleaned, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
