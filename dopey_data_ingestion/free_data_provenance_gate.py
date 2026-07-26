"""License/provenance gate for free/public data candidates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .free_data_candidate_registry import (
    FREE_DATA_STACK_VERSION,
    ARTIFACT_DIR,
    free_data_candidate_records,
    stable_free_data_hash,
)


FREE_DATA_PROVENANCE_GATE_RESULTS_PATH = ARTIFACT_DIR / "free_data_provenance_gate_results.jsonl"
FREE_DATA_CANDIDATE_PROOF_PATH = ARTIFACT_DIR / "free_data_candidate_proof.jsonl"


def build_free_data_provenance_gate_results(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        license_clear = candidate["license_status"] == "reviewed_allowed"
        provenance_clear = candidate["provenance_status"] == "complete"
        evidence_allowed = bool(license_clear and provenance_clear and candidate["evidence_allowed"])
        status = "evidence_allowed" if evidence_allowed else "manual_review_required"
        if not license_clear:
            status = "blocked_missing_license"
        if not provenance_clear:
            status = "blocked_missing_provenance"
        record = {
            "artifact_type": "free_data_provenance_gate_results",
            "free_data_stack_version": FREE_DATA_STACK_VERSION,
            "source_name": candidate["source_name"],
            "dataset_family": candidate["dataset_family"],
            "gate_status": status,
            "license_clear": license_clear,
            "provenance_clear": provenance_clear,
            "evidence_allowed": evidence_allowed,
            "not_fetched_by_dopey": True,
            "credentials_required": False,
            "network_fetch_performed": False,
            "manual_review_required": status != "evidence_allowed",
            "paper_only": True,
            "live_blocked": True,
        }
        record["result_hash"] = stable_free_data_hash(record)
        results.append(record)
    return results


def write_free_data_provenance_gate() -> dict[str, Any]:
    candidates = free_data_candidate_records()
    results = build_free_data_provenance_gate_results(candidates)
    proof = [{
        "artifact_type": "free_data_candidate_proof",
        "free_data_stack_version": FREE_DATA_STACK_VERSION,
        "proof_id": "free-data-candidate-proof-v1",
        "free_data_candidate_count": len(candidates),
        "free_data_evidence_allowed_count": sum(1 for result in results if result["evidence_allowed"]),
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }]
    proof[0]["proof_hash"] = stable_free_data_hash(proof[0])
    _write_jsonl(FREE_DATA_PROVENANCE_GATE_RESULTS_PATH, results)
    _write_jsonl(FREE_DATA_CANDIDATE_PROOF_PATH, proof)
    return {
        "free_data_provenance_result_count": len(results),
        "free_data_evidence_allowed_count": sum(1 for result in results if result["evidence_allowed"]),
        "free_data_manual_review_required_count": sum(1 for result in results if result["manual_review_required"]),
        "artifact_paths": {
            "free_data_provenance_gate_results": str(FREE_DATA_PROVENANCE_GATE_RESULTS_PATH),
            "free_data_candidate_proof": str(FREE_DATA_CANDIDATE_PROOF_PATH),
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
