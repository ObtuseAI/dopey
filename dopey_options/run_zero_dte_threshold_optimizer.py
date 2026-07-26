"""Write deterministic offline 0DTE threshold feedback optimizer artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .zero_dte_threshold_candidate import candidate_threshold_record
from .zero_dte_threshold_optimizer import build_zero_dte_threshold_optimizer_bundle


REPO_ROOT = Path(__file__).resolve().parent.parent
ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "zero_dte_threshold_optimizer"
ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "threshold_feedback_aggregate.json"
ZERO_DTE_THRESHOLD_CANDIDATES_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "threshold_candidates.jsonl"
ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "shadow_replay_results.jsonl"
ZERO_DTE_OPTIMIZATION_DECISIONS_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "optimization_decisions.jsonl"
ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "recommended_threshold_profile.json"
ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "rejected_threshold_profiles.jsonl"
ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "threshold_optimizer_summary.json"
ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH = ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR / "threshold_optimizer_proof.jsonl"


def run_zero_dte_threshold_optimizer() -> dict[str, Any]:
    bundle = build_zero_dte_threshold_optimizer_bundle()
    base_thresholds = bundle["base_thresholds"]
    aggregate = bundle["aggregate"]
    candidates = bundle["candidates"]
    shadow_results = bundle["shadow_results"]
    decisions = bundle["decisions"]
    recommended = bundle["recommended_threshold_profile"]
    rejected = bundle["rejected_threshold_profiles"]
    proof_records = bundle["proof_records"]
    summary = dict(bundle["summary"])
    artifact_paths = zero_dte_threshold_optimizer_artifact_paths()
    summary["artifact_paths"] = artifact_paths
    summary["reproducibility_hash"] = reproducibility_hash({k: v for k, v in summary.items() if k != "reproducibility_hash"})
    ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH, {
        "artifact_type": "zero_dte_threshold_feedback_aggregate",
        **aggregate.to_dict(),
    })
    _write_jsonl(ZERO_DTE_THRESHOLD_CANDIDATES_PATH, [
        {
            "artifact_type": "zero_dte_threshold_candidate",
            **candidate.to_dict(),
            "threshold_profile": candidate_threshold_record(base_thresholds, candidate),
        }
        for candidate in candidates
    ])
    _write_jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH, [
        {
            "artifact_type": "zero_dte_shadow_replay_result",
            **result.to_dict(),
        }
        for result in shadow_results
    ])
    _write_jsonl(ZERO_DTE_OPTIMIZATION_DECISIONS_PATH, [
        {
            "artifact_type": "zero_dte_threshold_optimization_decision",
            **decision.to_dict(),
        }
        for decision in decisions
    ])
    _write_json(ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH, recommended)
    _write_jsonl(ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH, rejected)
    _write_json(ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH, summary)
    _write_jsonl(ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH, proof_records)
    return {
        "zero_dte_threshold_optimizer_status": "ok",
        "summary": summary,
        "artifact_paths": artifact_paths,
    }


def zero_dte_threshold_optimizer_artifact_paths() -> dict[str, str]:
    return {
        "zero_dte_threshold_feedback_aggregate": str(ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH),
        "zero_dte_threshold_candidates": str(ZERO_DTE_THRESHOLD_CANDIDATES_PATH),
        "zero_dte_shadow_replay_results": str(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH),
        "zero_dte_threshold_optimization_decisions": str(ZERO_DTE_OPTIMIZATION_DECISIONS_PATH),
        "zero_dte_recommended_threshold_profile": str(ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH),
        "zero_dte_rejected_threshold_profiles": str(ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH),
        "zero_dte_threshold_optimizer_summary": str(ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH),
        "zero_dte_threshold_optimizer_proof": str(ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH),
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({k: v for k, v in payload.items() if k != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        payload["reproducibility_hash"] = reproducibility_hash({k: v for k, v in payload.items() if k != "reproducibility_hash"})
        output.append(payload)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in output]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_zero_dte_threshold_optimizer()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["zero_dte_threshold_optimizer_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
