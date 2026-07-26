"""Combined open-source quant stack and free-data local path runner."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_data.real_ohlcv_history_spine_upgrade import REAL_OHLCV_HISTORY_ACTIVATION_BLOCKERS_PATH
from dopey_data.run_real_ohlcv_history_spine_upgrade import run_real_ohlcv_history_spine_upgrade
from dopey_data_ingestion.free_data_candidate_registry import write_free_data_candidate_registry
from dopey_data_ingestion.free_data_provenance_gate import write_free_data_provenance_gate
from dopey_data_ingestion.local_ohlcv_import_models import stable_local_ohlcv_hash
from dopey_data_ingestion.run_local_ohlcv_import_validator import run_local_ohlcv_import_validator

from .oss_capability_extraction import write_capability_extraction_artifacts
from .oss_sandbox_import_plan import write_oss_sandbox_import_plan
from .run_oss_quant_stack_discovery import run_oss_quant_stack_discovery


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "open_source_path"
OPEN_SOURCE_PATH_SUMMARY_PATH = ARTIFACT_DIR / "open_source_quant_stack_and_free_data_path_summary.json"
OPEN_SOURCE_PATH_QUALITY_FLAGS_PATH = ARTIFACT_DIR / "open_source_quant_stack_and_free_data_path_quality_flags.jsonl"
OPEN_SOURCE_PATH_PROOF_PATH = ARTIFACT_DIR / "open_source_quant_stack_and_free_data_path_proof.jsonl"


def run_open_source_quant_stack_and_free_data_path() -> dict[str, Any]:
    oss = run_oss_quant_stack_discovery()
    sandbox = write_oss_sandbox_import_plan()
    capability = write_capability_extraction_artifacts()
    free_data = write_free_data_candidate_registry()
    free_data_gate = write_free_data_provenance_gate()
    local_ohlcv = run_local_ohlcv_import_validator()
    history = run_real_ohlcv_history_spine_upgrade()
    summary = _summary(oss, sandbox, capability, free_data, free_data_gate, local_ohlcv, history)
    quality_flags = _quality_flags(summary)
    proof = _proof(summary)
    _write_json(OPEN_SOURCE_PATH_SUMMARY_PATH, {**summary, "artifact_paths": artifact_paths()})
    _write_jsonl(OPEN_SOURCE_PATH_QUALITY_FLAGS_PATH, quality_flags)
    _write_jsonl(OPEN_SOURCE_PATH_PROOF_PATH, proof)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_source_quant_stack_and_free_data_path_summary": str(OPEN_SOURCE_PATH_SUMMARY_PATH),
        "open_source_quant_stack_and_free_data_path_quality_flags": str(OPEN_SOURCE_PATH_QUALITY_FLAGS_PATH),
        "open_source_quant_stack_and_free_data_path_proof": str(OPEN_SOURCE_PATH_PROOF_PATH),
        "real_ohlcv_history_activation_blockers": str(REAL_OHLCV_HISTORY_ACTIVATION_BLOCKERS_PATH),
    }


def _summary(
    oss: dict[str, Any],
    sandbox: dict[str, Any],
    capability: dict[str, Any],
    free_data: dict[str, Any],
    free_data_gate: dict[str, Any],
    local_ohlcv: dict[str, Any],
    history: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "artifact_type": "open_source_quant_stack_and_free_data_path_summary",
        "bundle_version": "dopey-open-source-quant-stack-and-free-data-path-v1",
        "oss_candidate_count": int(oss["oss_candidate_count"]),
        "oss_reference_only_count": int(oss["oss_reference_only_count"]),
        "oss_sandbox_candidate_count": int(oss["oss_sandbox_candidate_count"]),
        "oss_adapter_candidate_count": int(oss["oss_adapter_candidate_count"]),
        "oss_rejected_count": int(oss["oss_rejected_count"]),
        "oss_imported_count": 0,
        "oss_executed_count": 0,
        "repo_cloned_count": 0,
        "dependency_installed_count": 0,
        "sandbox_import_plan_ready": True,
        "capability_plan_count": int(capability["capability_plan_count"]),
        "adapter_contract_count": int(capability["adapter_contract_count"]),
        "free_data_candidate_count": int(free_data["free_data_candidate_count"]),
        "free_data_evidence_allowed_count": int(free_data_gate["free_data_evidence_allowed_count"]),
        "free_data_manual_review_required_count": int(free_data_gate["free_data_manual_review_required_count"]),
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "local_ohlcv_status": str(local_ohlcv["local_ohlcv_status"]),
        "local_ohlcv_fix_advice_status": str(local_ohlcv["fix_advice_status"]),
        "real_data_files_present": bool(local_ohlcv["real_data_files_present"]),
        "valid_real_dataset": bool(local_ohlcv["valid_real_dataset"]),
        "history_spine_upgrade_status": str(history["history_spine_upgrade_status"]),
        "real_history_used": bool(history["real_history_used"]),
        "strategy_promotion_allowed": False,
        "alpha_vantage_excluded": True,
        "paper_only": True,
        "live_blocked": True,
        "next_recommended_target": "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1",
    }
    record["summary_hash"] = stable_local_ohlcv_hash(record)
    return record


def _quality_flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    flags = [{
        "artifact_type": "open_source_quant_stack_and_free_data_path_quality_flags",
        "flag_id": "open-source-path-no-real-ohlcv",
        "severity": "info",
        "reason_code": "local_ohlcv_missing_or_not_valid",
        "local_ohlcv_status": summary["local_ohlcv_status"],
        "history_spine_upgrade_status": summary["history_spine_upgrade_status"],
        "paper_only": True,
        "live_blocked": True,
    }]
    flags[0]["flag_hash"] = stable_local_ohlcv_hash(flags[0])
    return flags


def _proof(summary: dict[str, Any]) -> list[dict[str, Any]]:
    record = {
        "artifact_type": "open_source_quant_stack_and_free_data_path_proof",
        "proof_id": "open-source-quant-stack-free-data-path-proof-v1",
        "oss_imported_count": 0,
        "oss_executed_count": 0,
        "repo_cloned_count": 0,
        "dependency_installed_count": 0,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "alpha_vantage_excluded": True,
        "valid_real_dataset": summary["valid_real_dataset"],
        "real_history_used": summary["real_history_used"],
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["proof_hash"] = stable_local_ohlcv_hash(record)
    return [record]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result = run_open_source_quant_stack_and_free_data_path()
    print(json.dumps({
        "oss_candidate_count": result["oss_candidate_count"],
        "free_data_candidate_count": result["free_data_candidate_count"],
        "local_ohlcv_status": result["local_ohlcv_status"],
        "history_spine_upgrade_status": result["history_spine_upgrade_status"],
        "valid_real_dataset": result["valid_real_dataset"],
        "network_fetch_performed": result["network_fetch_performed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
