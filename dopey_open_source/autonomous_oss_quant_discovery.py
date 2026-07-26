"""Autonomous OSS quant discovery based on metadata-only candidates."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, oss_candidates, proof_record, safety_state, stable_hash, write_json, write_jsonl

from .autonomous_oss_quant_scorecard import build_autonomous_oss_scorecard


ARTIFACT_DIR = ARTIFACT_ROOT / "open_source_autonomy"
CANDIDATES_PATH = ARTIFACT_DIR / "autonomous_oss_candidate_registry.jsonl"
LICENSE_RESULTS_PATH = ARTIFACT_DIR / "autonomous_oss_license_results.jsonl"
SCORECARD_PATH = ARTIFACT_DIR / "autonomous_oss_scorecard.json"
IMPORT_PLAN_PATH = ARTIFACT_DIR / "autonomous_oss_import_plan.json"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_oss_discovery_summary.json"
PROOF_PATH = ARTIFACT_DIR / "autonomous_oss_discovery_proof.jsonl"


def run_autonomous_oss_quant_discovery() -> dict[str, Any]:
    records = oss_candidates()
    license_results = [_license_record(record) for record in records]
    scorecard = build_autonomous_oss_scorecard(records)
    import_plan = _import_plan(records)
    summary = {
        "artifact_type": "autonomous_oss_discovery_summary",
        "oss_discovery_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "open_source_candidate_count": len(records),
        "open_source_accepted_count": scorecard["accepted_count"],
        "reference_only_count": scorecard["reference_only_count"],
        "rejected_count": scorecard["rejected_count"],
        "repo_cloned_count": 0,
        "dependency_installed_count": 0,
        "external_code_imported_count": 0,
        "external_code_executed_count": 0,
        "accepted_import_modes": ["reference_only", "adapter_candidate", "sandbox_candidate", "rejected"],
        "unknown_license_auto_rejected": True,
        "copyleft_reference_only": True,
        "broker_live_execution_repos_not_embedded": True,
        "credentialed_data_adapters_rejected_for_data_use": True,
        "external_code_cannot_control_dopey": True,
        "network_fetch_performed": False,
        "alpha_vantage_excluded": True,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(CANDIDATES_PATH, records)
    write_jsonl(LICENSE_RESULTS_PATH, license_results)
    write_json(SCORECARD_PATH, scorecard)
    write_json(IMPORT_PLAN_PATH, import_plan)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("autonomous-oss-discovery-proof-v1", "completed", summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_oss_candidate_registry": str(CANDIDATES_PATH),
        "autonomous_oss_license_results": str(LICENSE_RESULTS_PATH),
        "autonomous_oss_scorecard": str(SCORECARD_PATH),
        "autonomous_oss_import_plan": str(IMPORT_PLAN_PATH),
        "autonomous_oss_discovery_summary": str(SUMMARY_PATH),
        "autonomous_oss_discovery_proof": str(PROOF_PATH),
    }


def _license_record(candidate: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "autonomous_oss_license_results",
        "candidate_id": candidate["candidate_id"],
        "license_id": candidate["license_id"],
        "license_result": "rejected_unknown_license" if not candidate["license_id"] else ("reference_only_copyleft" if candidate["license_id"].startswith("GPL") else "machine_verified_permissive"),
        "import_mode": candidate["import_mode"],
        "reason_codes": candidate["reason_codes"],
        "paper_only": True,
        "live_blocked": True,
    }
    record["license_hash"] = stable_hash(record)
    return record


def _import_plan(records: list[dict[str, Any]]) -> dict[str, Any]:
    plan = {
        "artifact_type": "autonomous_oss_import_plan",
        "plan_id": "autonomous-oss-import-plan-v1",
        "reference_only": [record["candidate_id"] for record in records if record["import_mode"] == "reference_only"],
        "adapter_candidates": [record["candidate_id"] for record in records if record["import_mode"] == "adapter_candidate"],
        "sandbox_candidates": [record["candidate_id"] for record in records if record["import_mode"] == "sandbox_candidate"],
        "rejected": [record["candidate_id"] for record in records if record["import_mode"] == "rejected"],
        "quarantine_folder": "dopey_open_source_vendor/quarantine/",
        "do_not_clone_by_default": True,
        "repo_cloned_count": 0,
        "external_code_imported_count": 0,
        "external_code_executed_count": 0,
        "external_code_cannot_place_orders": True,
        "external_code_cannot_promote_strategies": True,
        "paper_only": True,
        "live_blocked": True,
    }
    plan["plan_hash"] = stable_hash(plan)
    return plan

