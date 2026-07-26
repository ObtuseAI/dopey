"""Write options-chain/quote import contract artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .options_chain_quote_contract import build_options_chain_quote_contract


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "options_data_contract"
OPTIONS_CHAIN_QUOTE_CONTRACT_PATH = ARTIFACT_DIR / "options_chain_quote_contract.json"
OPTIONS_SCHEMA_CONTRACTS_PATH = ARTIFACT_DIR / "options_schema_contracts.jsonl"
OPTIONS_QUALITY_GATE_PLAN_PATH = ARTIFACT_DIR / "options_quality_gate_plan.jsonl"
OPTIONS_IMPORT_READINESS_DECISION_PATH = ARTIFACT_DIR / "options_import_readiness_decision.json"
OPTIONS_DATA_CONTRACT_SUMMARY_PATH = ARTIFACT_DIR / "options_data_contract_summary.json"
OPTIONS_DATA_CONTRACT_PROOF_PATH = ARTIFACT_DIR / "options_data_contract_proof.jsonl"


def run_options_chain_quote_import_contract() -> dict[str, Any]:
    result = build_options_chain_quote_contract()
    _write_json(OPTIONS_CHAIN_QUOTE_CONTRACT_PATH, result["contract"])
    _write_jsonl(OPTIONS_SCHEMA_CONTRACTS_PATH, result["schemas"])
    _write_jsonl(OPTIONS_QUALITY_GATE_PLAN_PATH, result["gates"])
    _write_json(OPTIONS_IMPORT_READINESS_DECISION_PATH, result["decision"])
    _write_json(OPTIONS_DATA_CONTRACT_SUMMARY_PATH, {**result["summary"], "artifact_paths": artifact_paths()})
    _write_jsonl(OPTIONS_DATA_CONTRACT_PROOF_PATH, result["proof"])
    return {**result["summary"], "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "options_chain_quote_contract": str(OPTIONS_CHAIN_QUOTE_CONTRACT_PATH),
        "options_schema_contracts": str(OPTIONS_SCHEMA_CONTRACTS_PATH),
        "options_quality_gate_plan": str(OPTIONS_QUALITY_GATE_PLAN_PATH),
        "options_import_readiness_decision": str(OPTIONS_IMPORT_READINESS_DECISION_PATH),
        "options_data_contract_summary": str(OPTIONS_DATA_CONTRACT_SUMMARY_PATH),
        "options_data_contract_proof": str(OPTIONS_DATA_CONTRACT_PROOF_PATH),
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_options_chain_quote_import_contract()
    print(json.dumps({
        "options_contract_status": result["options_contract_status"],
        "options_data_files_present": result["options_data_files_present"],
        "options_data_ingested": result["options_data_ingested"],
        "options_data_validated": result["options_data_validated"],
        "quote_priced_backtest_allowed": result["quote_priced_backtest_allowed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
