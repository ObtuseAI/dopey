"""Write open-source quant candidate discovery artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .oss_license_security_gate import build_oss_candidate_scorecard, oss_license_security_records
from .oss_models import OSS_STACK_VERSION
from .oss_quant_stack_registry import oss_candidate_records


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "open_source"
OSS_CANDIDATE_REGISTRY_PATH = ARTIFACT_DIR / "oss_candidate_registry.jsonl"
OSS_LICENSE_SECURITY_RESULTS_PATH = ARTIFACT_DIR / "oss_license_security_results.jsonl"
OSS_CANDIDATE_SCORECARD_PATH = ARTIFACT_DIR / "oss_candidate_scorecard.json"
OSS_DISCOVERY_SUMMARY_PATH = ARTIFACT_DIR / "oss_discovery_summary.json"
OSS_DISCOVERY_PROOF_PATH = ARTIFACT_DIR / "oss_discovery_proof.jsonl"


def run_oss_quant_stack_discovery() -> dict[str, Any]:
    candidates = oss_candidate_records()
    gate_results = oss_license_security_records(candidates)
    scorecard = build_oss_candidate_scorecard(candidates, gate_results)
    summary = {
        "artifact_type": "oss_discovery_summary",
        "oss_stack_version": OSS_STACK_VERSION,
        "oss_candidate_count": len(candidates),
        "oss_reference_only_count": scorecard["reference_only_count"],
        "oss_sandbox_candidate_count": scorecard["sandbox_candidate_count"],
        "oss_adapter_candidate_count": scorecard["adapter_candidate_count"],
        "oss_rejected_count": scorecard["rejected_count"],
        "oss_imported_count": 0,
        "oss_executed_count": 0,
        "repo_cloned_count": 0,
        "dependency_installed_count": 0,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "production_import_allowed": False,
        "live_integration_allowed": False,
        "broker_integration_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    proof = [{
        "artifact_type": "oss_discovery_proof",
        "proof_id": "oss-discovery-proof-v1",
        "repo_cloned_count": 0,
        "dependency_installed_count": 0,
        "external_code_imported_count": 0,
        "external_code_executed_count": 0,
        "network_fetch_performed": False,
        "credentials_created": False,
        "paper_only": True,
        "live_blocked": True,
    }]
    _write_jsonl(OSS_CANDIDATE_REGISTRY_PATH, candidates)
    _write_jsonl(OSS_LICENSE_SECURITY_RESULTS_PATH, gate_results)
    _write_json(OSS_CANDIDATE_SCORECARD_PATH, scorecard)
    _write_json(OSS_DISCOVERY_SUMMARY_PATH, {**summary, "artifact_paths": artifact_paths()})
    _write_jsonl(OSS_DISCOVERY_PROOF_PATH, proof)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "oss_candidate_registry": str(OSS_CANDIDATE_REGISTRY_PATH),
        "oss_license_security_results": str(OSS_LICENSE_SECURITY_RESULTS_PATH),
        "oss_candidate_scorecard": str(OSS_CANDIDATE_SCORECARD_PATH),
        "oss_discovery_summary": str(OSS_DISCOVERY_SUMMARY_PATH),
        "oss_discovery_proof": str(OSS_DISCOVERY_PROOF_PATH),
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_oss_quant_stack_discovery()
    print(json.dumps({
        "oss_candidate_count": result["oss_candidate_count"],
        "oss_imported_count": result["oss_imported_count"],
        "oss_executed_count": result["oss_executed_count"],
        "repo_cloned_count": result["repo_cloned_count"],
        "network_fetch_performed": result["network_fetch_performed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
