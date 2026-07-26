"""Write DOPEY real-data ingestion plan artifacts without fetching data."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .data_quality_gate_plan import data_quality_gate_records, license_provenance_requirement_records
from .dataset_requirement_catalog import dataset_requirement_records
from .ingestion_plan_models import DATA_INGESTION_PLAN_VERSION, DataIngestionPlan, IngestionPlanProofRecord, stable_ingestion_hash
from .ingestion_readiness_decision import build_ingestion_quality_flags, decide_import_readiness
from .local_staging_contract import REPO_ROOT, build_local_staging_contract
from .provider_candidate_registry import provider_candidate_records
from .schema_contracts import sample_template_paths, schema_contract_records
from dopey_core.repo_paths import REPORTS_DIR


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "data_ingestion"
DATA_INGESTION_PLAN_PATH = ARTIFACT_DIR / "data_ingestion_plan.json"
DATASET_REQUIREMENTS_PATH = ARTIFACT_DIR / "dataset_requirements.jsonl"
PROVIDER_CANDIDATES_PATH = ARTIFACT_DIR / "provider_candidates.jsonl"
LOCAL_STAGING_CONTRACT_PATH = ARTIFACT_DIR / "local_staging_contract.json"
SCHEMA_CONTRACTS_PATH = ARTIFACT_DIR / "schema_contracts.jsonl"
LICENSE_PROVENANCE_REQUIREMENTS_PATH = ARTIFACT_DIR / "license_provenance_requirements.jsonl"
DATA_QUALITY_GATES_PATH = ARTIFACT_DIR / "data_quality_gates.jsonl"
IMPORT_READINESS_DECISION_PATH = ARTIFACT_DIR / "import_readiness_decision.json"
INGESTION_PLAN_QUALITY_FLAGS_PATH = ARTIFACT_DIR / "ingestion_plan_quality_flags.jsonl"
DATA_INGESTION_PLAN_SUMMARY_PATH = ARTIFACT_DIR / "data_ingestion_plan_summary.json"
DATA_INGESTION_PLAN_PROOF_PATH = ARTIFACT_DIR / "data_ingestion_plan_proof.jsonl"
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "data_ingestion"
REPORT_PATH = REPORTS_DIR / "DOPEY_REAL_DATA_INGESTION_PLAN_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_REAL_DATA_INGESTION_PLAN_ARTIFACT_LEDGER.md"


def run_real_data_ingestion_plan() -> dict[str, Any]:
    requirements = dataset_requirement_records()
    providers = provider_candidate_records()
    local_contract = build_local_staging_contract(True).to_dict()
    schemas = schema_contract_records(True)
    license_requirements = license_provenance_requirement_records()
    gates = data_quality_gate_records()
    decision = decide_import_readiness(
        requirements,
        providers,
        local_contract,
        schemas,
        gates,
        _load_json(REPO_ROOT / "artifacts" / "dopey" / "history" / "history_spine_summary.json"),
        _load_json(REPO_ROOT / "artifacts" / "dopey" / "fitness" / "fitness_replacement_summary.json"),
    ).to_dict()
    quality_flags = [flag.to_dict() for flag in build_ingestion_quality_flags(decision)]
    plan = _build_plan(requirements, providers, schemas, gates, decision)
    summary = _build_summary(requirements, providers, schemas, gates, license_requirements, decision, quality_flags)
    proof = _build_proof(decision).to_dict()
    _write_json(DATA_INGESTION_PLAN_PATH, plan)
    _write_jsonl(DATASET_REQUIREMENTS_PATH, requirements)
    _write_jsonl(PROVIDER_CANDIDATES_PATH, providers)
    _write_json(LOCAL_STAGING_CONTRACT_PATH, local_contract)
    _write_jsonl(SCHEMA_CONTRACTS_PATH, schemas)
    _write_jsonl(LICENSE_PROVENANCE_REQUIREMENTS_PATH, license_requirements)
    _write_jsonl(DATA_QUALITY_GATES_PATH, gates)
    _write_json(IMPORT_READINESS_DECISION_PATH, decision)
    _write_jsonl(INGESTION_PLAN_QUALITY_FLAGS_PATH, quality_flags)
    _write_json(DATA_INGESTION_PLAN_SUMMARY_PATH, summary)
    _write_jsonl(DATA_INGESTION_PLAN_PROOF_PATH, [proof])
    fixture_paths = write_fixture_cases()
    report = _write_report(summary, requirements, providers, schemas, gates, license_requirements, decision)
    ledger = _write_ledger([*artifact_paths().values(), *fixture_paths, *sample_template_paths(), str(report)])
    summary_with_paths = {
        **summary,
        "artifact_paths": artifact_paths(),
        "fixture_paths": fixture_paths,
        "report_path": str(report),
        "ledger_path": str(ledger),
    }
    _write_json(DATA_INGESTION_PLAN_SUMMARY_PATH, summary_with_paths)
    return summary_with_paths


def artifact_paths() -> dict[str, str]:
    return {
        "data_ingestion_plan": str(DATA_INGESTION_PLAN_PATH),
        "dataset_requirements": str(DATASET_REQUIREMENTS_PATH),
        "provider_candidates": str(PROVIDER_CANDIDATES_PATH),
        "local_staging_contract": str(LOCAL_STAGING_CONTRACT_PATH),
        "schema_contracts": str(SCHEMA_CONTRACTS_PATH),
        "license_provenance_requirements": str(LICENSE_PROVENANCE_REQUIREMENTS_PATH),
        "data_quality_gates": str(DATA_QUALITY_GATES_PATH),
        "import_readiness_decision": str(IMPORT_READINESS_DECISION_PATH),
        "ingestion_plan_quality_flags": str(INGESTION_PLAN_QUALITY_FLAGS_PATH),
        "data_ingestion_plan_summary": str(DATA_INGESTION_PLAN_SUMMARY_PATH),
        "data_ingestion_plan_proof": str(DATA_INGESTION_PLAN_PROOF_PATH),
    }


def write_fixture_cases() -> list[str]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    requirement_cases = [_fixture_case(f"requirement-{index:03d}", "dataset_requirement", {"dataset_family": family}) for index, family in enumerate([
        "daily_ohlcv", "corporate_actions", "historical_options_chain", "historical_options_quotes", "fundamentals",
        "earnings_calendar", "market_context", "benchmark_and_universe_metadata", "missing-real-file", "manifest-missing",
        "license-required", "provenance-required", "manual-review", "terminal-block", "no-network-fetch", "sample-only-blocked",
        "credential-token-blocked", "broker-live-order-scheduler-real-sizing-blocked", "daily-ohlcv-positive-prices", "options-expiry-check",
    ], start=1)]
    provider_cases = [_fixture_case(f"provider-{index:03d}", "provider_candidate", {"provider_name": provider}) for index, provider in enumerate([
        "Polygon", "Cboe DataShop", "ORATS", "OptionMetrics", "Nasdaq Data Link", "Alpha Vantage", "Tiingo", "Stooq",
        "Yahoo Finance manual download", "SEC EDGAR", "FRED", "credential-required-manual-review", "license-review-required",
        "candidate-only-not-integrated", "manual-offline-export-only", "rejected-unlicensed", "redistribution-restricted",
        "options-data-available", "corporate-actions-available", "fundamentals-available",
    ], start=1)]
    schema_cases = [_fixture_case(f"schema-{index:03d}", "schema_contract", {"schema_family": family}) for index, family in enumerate([
        "daily_ohlcv_required_columns", "daily_ohlcv_optional_actions", "daily_ohlcv_primary_key", "corporate_actions_required_columns",
        "corporate_actions_primary_key", "options_chain_required_columns", "options_chain_greeks_optional", "options_chain_option_type",
        "options_quotes_required_columns", "options_quotes_bid_ask_size", "fundamentals_required_columns", "fundamentals_numeric_parse",
        "earnings_calendar_required_columns", "earnings_report_time", "market_context_same_as_ohlcv", "market_context_vix_equivalent",
        "universe_metadata_required_columns", "universe_metadata_survivorship", "sample_daily_ohlcv_blocked", "sample_options_chain_blocked",
        "sample_options_quotes_blocked", "sample_fundamentals_blocked",
    ], start=1)]
    readiness_cases = [_fixture_case(f"readiness-{index:03d}", "readiness_decision", {"scenario": scenario}) for index, scenario in enumerate([
        "plan_ready_import_not_started", "real_files_present_manifest_missing", "blocked_missing_license", "blocked_missing_provenance",
        "blocked_network_fetch_attempt", "blocked_fake_real_data", "sample_only_row_terminal_block", "credential_token_terminal_block",
        "broker_path_terminal_block", "live_order_terminal_block", "scheduler_terminal_block", "real_sizing_terminal_block",
        "manifest_present_validation_not_run", "license_review_required", "manual_review_required", "terminal_block",
        "full_pytest_timeout_inconclusive_not_pass", "live_trading_disabled", "broker_connection_absent", "credentials_absent",
        "env_absent", "robinhood_mcp_not_integrated",
    ], start=1)]
    paths = [
        FIXTURE_DIR / "data_requirement_cases.json",
        FIXTURE_DIR / "provider_candidate_cases.json",
        FIXTURE_DIR / "schema_contract_cases.json",
        FIXTURE_DIR / "readiness_decision_cases.json",
    ]
    for path, cases in zip(paths, [requirement_cases, provider_cases, schema_cases, readiness_cases]):
        _write_json(path, {"case_count": len(cases), "cases": cases})
    return [str(path) for path in paths]


def _build_plan(
    requirements: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    schemas: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    decision: dict[str, Any],
) -> dict[str, Any]:
    return DataIngestionPlan(
        artifact_type="data_ingestion_plan",
        ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
        plan_id="dopey-real-data-ingestion-plan-v1",
        ingestion_status=str(decision["ingestion_status"]),
        import_readiness_decision=str(decision["import_readiness_decision"]),
        dataset_requirement_count=len(requirements),
        provider_candidate_count=len(providers),
        schema_contract_count=len(schemas),
        quality_gate_count=len(gates),
        objective="Define offline manual acquisition and local staging contracts for future real-data validation.",
        allowed_later_bundles=["DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1"],
        network_fetch_performed=False,
        broker_connection_used=False,
        credentials_created=False,
        env_created=False,
        real_data_files_present=bool(decision["real_data_files_present"]),
        real_data_ingested=False,
        real_data_validated=False,
        not_real_evidence=True,
        not_strategy_promotion=True,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        plan_hash="",
    ).to_dict()


def _build_summary(
    requirements: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    schemas: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    license_requirements: list[dict[str, Any]],
    decision: dict[str, Any],
    quality_flags: list[dict[str, Any]],
) -> dict[str, Any]:
    terminal_count = sum(1 for flag in quality_flags if flag.get("terminal_block") is True)
    manual_count = sum(1 for flag in quality_flags if flag.get("manual_review_required") is True)
    provider_manual_count = sum(1 for provider in providers if provider.get("status") == "manual_review_required")
    summary = {
        "artifact_type": "data_ingestion_plan_summary",
        "ingestion_plan_version": DATA_INGESTION_PLAN_VERSION,
        "ingestion_status": decision["ingestion_status"],
        "import_readiness_decision": decision["import_readiness_decision"],
        "dataset_requirement_count": len(requirements),
        "provider_candidate_count": len(providers),
        "schema_contract_count": len(schemas),
        "quality_gate_count": len(gates),
        "real_data_files_present": bool(decision["real_data_files_present"]),
        "real_data_ingested": False,
        "real_data_validated": False,
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "live_data_used": False,
        "sample_template_count": len(sample_template_paths()),
        "license_review_required_count": len(license_requirements),
        "manual_review_required_count": provider_manual_count + manual_count,
        "terminal_block_count": terminal_count,
        "not_real_data_ingested": True,
        "not_real_evidence": True,
        "not_strategy_promotion": True,
        "paper_only": True,
        "live_blocked": True,
        "next_recommended_target": "DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1",
    }
    summary["summary_hash"] = stable_ingestion_hash(summary)
    return summary


def _build_proof(decision: dict[str, Any]) -> IngestionPlanProofRecord:
    return IngestionPlanProofRecord(
        artifact_type="data_ingestion_plan_proof",
        ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
        proof_id="dopey-real-data-ingestion-plan-proof-v1",
        ingestion_status=str(decision["ingestion_status"]),
        import_readiness_decision=str(decision["import_readiness_decision"]),
        real_data_files_present=bool(decision["real_data_files_present"]),
        real_data_ingested=False,
        real_data_validated=False,
        network_fetch_performed=False,
        broker_connection_used=False,
        credentials_created=False,
        env_created=False,
        live_data_used=False,
        no_orders=True,
        no_scheduler=True,
        no_real_sizing=True,
        no_strategy_promotion=True,
        sample_templates_not_real_evidence=True,
        next_recommended_target="DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1",
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        proof_hash="",
    )


def _write_report(
    summary: dict[str, Any],
    requirements: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    schemas: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    license_requirements: list[dict[str, Any]],
    decision: dict[str, Any],
) -> Path:
    lines = [
        "# DOPEY Real Data Ingestion Plan Report",
        "",
        "## Objective",
        "Define the offline acquisition contract for future manually staged real market data. This bundle does not fetch, ingest, or validate real data.",
        "",
        "## Current Blocker Summary",
        "- real_data_files_present: `false`",
        "- real_data_ingested: `false`",
        "- real_data_validated: `false`",
        "- import_readiness_decision: `" + str(summary["import_readiness_decision"]) + "`",
        "",
        "## Required Datasets",
        *[f"- `{record['dataset_family']}`: {record['purpose']}" for record in requirements],
        "",
        "## Provider Candidate Registry",
        *[f"- `{record['provider_name']}` status=`{record['status']}` credential_required=`{str(record['credential_required']).lower()}`" for record in providers],
        "",
        "## Local Staging Folder Contract",
        "- Raw local-only folders are under `dopey_data/real/raw/`.",
        "- Manifest template is `dopey_data/real/manifests/real_data_manifest.json`.",
        "- Validated outputs, when a later bundle exists, are under `dopey_data/real/validated/`.",
        "",
        "## Schema Contracts",
        *[f"- `{record['dataset_family']}` required_columns={len(record['required_columns'])}" for record in schemas],
        "",
        "## License And Provenance Requirements",
        f"- license_provenance_requirement_count: `{len(license_requirements)}`",
        "- Unknown, unreviewed, missing, or unlicensed data blocks import readiness.",
        "",
        "## Quality Gate Plan",
        f"- quality_gate_count: `{len(gates)}`",
        "- All gates are `gate_defined_not_run` in this planning bundle.",
        "",
        "## Import Readiness Decision",
        f"- ingestion_status: `{decision['ingestion_status']}`",
        f"- import_readiness_decision: `{decision['import_readiness_decision']}`",
        f"- reason_codes: `{decision['reason_codes']}`",
        "",
        "## What This Bundle Does Not Do",
        "- It does not fetch market data, scrape market data, connect to brokers, create credentials, create `.env`, place orders, create schedulers, size real capital, promote strategies, or claim real edge.",
        "",
        "## Current No-Real-Data Limitation",
        "- Sample templates are schema examples only and are not evidence.",
        "- The next bundle may validate manually staged local OHLCV only.",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- not_real_data_ingested: `true`",
        "",
        "## Validation Summary",
        "- Targeted test: `tests/test_real_data_ingestion_plan.py`",
        "- Full pytest timeout, if encountered, remains `inconclusive_timeout` and is not pass.",
        "",
        "## Limitations",
        "- Provider approval is not claimed.",
        "- License review is not completed by this bundle.",
        "- No data-quality gate has run against real market data.",
        "",
        "## Next Target",
        "- `DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT_PATH


def _write_ledger(paths: list[str]) -> Path:
    lines = ["# DOPEY Real Data Ingestion Plan Artifact Ledger", ""]
    lines.append("## Safety State")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append("- not_real_data_ingested: `true`")
    lines.append("")
    lines.append("## Artifacts")
    for path_text in sorted(set(paths)):
        path = Path(path_text)
        if path.exists():
            lines.append(f"- `{_repo_relative(path)}` records=`{_record_count(path)}` sha256=`{_sha256(path)}`")
    LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return LEDGER_PATH


def _fixture_case(case_id: str, case_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = {
        "case_id": case_id,
        "case_type": case_type,
        "input": payload,
        "expected": {
            "fixture_only": True,
            "sample_only": True,
            "not_real_data": True,
            "not_real_data_ingested": True,
            "real_data_ingested": False,
            "paper_only": True,
            "live_blocked": True,
        },
        "fixture_only": True,
        "sample_only": True,
        "not_real_data": True,
        "not_real_data_ingested": True,
        "real_data_ingested": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["case_hash"] = stable_ingestion_hash(record)
    return record


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if path.suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return max(sum(1 for _row in csv.reader(handle)) - 1, 0)
    return 1


def _repo_relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    result = run_real_data_ingestion_plan()
    print(json.dumps({
        "ingestion_status": result["ingestion_status"],
        "import_readiness_decision": result["import_readiness_decision"],
        "real_data_files_present": result["real_data_files_present"],
        "real_data_ingested": result["real_data_ingested"],
        "real_data_validated": result["real_data_validated"],
        "network_fetch_performed": result["network_fetch_performed"],
        "next_recommended_target": result["next_recommended_target"],
        "summary_path": str(DATA_INGESTION_PLAN_SUMMARY_PATH),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
