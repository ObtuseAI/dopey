"""Write deterministic portfolio-level paper replay artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .exposure_stress_replay import build_exposure_stress_results
from .portfolio_replay_engine import build_portfolio_replay_bundle


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "portfolio"
PORTFOLIO_REPLAY_POLICY_FIXTURE_PATH = FIXTURE_DIR / "portfolio_replay_policy.json"
PORTFOLIO_REPLAY_OPPORTUNITIES_FIXTURE_PATH = FIXTURE_DIR / "portfolio_replay_opportunities.json"
PORTFOLIO_REPLAY_TIMELINE_CASES_FIXTURE_PATH = FIXTURE_DIR / "portfolio_replay_timeline_cases.json"
EXPECTED_PORTFOLIO_ROTATION_DECISIONS_FIXTURE_PATH = FIXTURE_DIR / "expected_portfolio_rotation_decisions.json"
EXPECTED_PORTFOLIO_EXPOSURE_SNAPSHOTS_FIXTURE_PATH = FIXTURE_DIR / "expected_portfolio_exposure_snapshots.json"
EXPECTED_PORTFOLIO_REPLAY_SUMMARY_FIXTURE_PATH = FIXTURE_DIR / "expected_portfolio_replay_summary.json"

PORTFOLIO_REPLAY_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "portfolio_replay"
PORTFOLIO_REPLAY_POLICY_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_replay_policy.json"
PORTFOLIO_REPLAY_OPPORTUNITIES_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_replay_opportunities.jsonl"
PORTFOLIO_STATES_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_states.jsonl"
PORTFOLIO_POSITIONS_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_positions.jsonl"
PORTFOLIO_ROTATION_DECISIONS_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_rotation_decisions.jsonl"
PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_exposure_snapshots.jsonl"
EXPOSURE_STRESS_RESULTS_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "exposure_stress_results.jsonl"
PORTFOLIO_ALLOCATOR_FEEDBACK_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_allocator_feedback.jsonl"
PORTFOLIO_THRESHOLD_FEEDBACK_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_threshold_feedback.jsonl"
PORTFOLIO_REPLAY_SUMMARY_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_replay_summary.json"
PORTFOLIO_REPLAY_PROOF_PATH = PORTFOLIO_REPLAY_ARTIFACT_DIR / "portfolio_replay_proof.jsonl"
LIFECYCLE_PORTFOLIO_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "lifecycle" / "lifecycle_feedback_portfolio.jsonl"


def run_portfolio_replay() -> dict[str, Any]:
    bundle = build_portfolio_replay_bundle()
    policy = bundle["policy"].to_dict()
    opportunities = bundle["portfolio_opportunities"]
    states = [record.to_dict() for record in bundle["states"]]
    positions = [record.to_dict() for record in bundle["positions"]]
    rotation_decisions = [record.to_dict() for record in bundle["rotation_decisions"]]
    exposure_snapshots = [record.to_dict() for record in bundle["exposure_snapshots"]]
    allocator_feedback = list(bundle["allocator_feedback"])
    threshold_feedback = list(bundle["threshold_feedback"])
    proof_records = list(bundle["proof_records"])
    summary = dict(bundle["summary"])
    summary["lifecycle_feedback_summary"] = lifecycle_feedback_summary()
    summary["lifecycle_feedback_loaded"] = bool(summary["lifecycle_feedback_summary"].get("lifecycle_feedback_loaded", False))
    summary["lifecycle_feedback_actions"] = summary["lifecycle_feedback_summary"].get("feedback_action_distribution", {})
    summary["reproducibility_hash"] = reproducibility_hash({key: value for key, value in summary.items() if key != "reproducibility_hash"})
    stress_results = build_exposure_stress_results(opportunities, rotation_decisions, exposure_snapshots)

    write_portfolio_replay_fixture_files(
        policy,
        opportunities,
        rotation_decisions,
        exposure_snapshots,
        summary,
    )
    PORTFOLIO_REPLAY_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(PORTFOLIO_REPLAY_POLICY_PATH, {"artifact_type": "portfolio_replay_policy", **policy})
    _write_jsonl(PORTFOLIO_REPLAY_OPPORTUNITIES_PATH, opportunities)
    _write_jsonl(PORTFOLIO_STATES_PATH, states)
    _write_jsonl(PORTFOLIO_POSITIONS_PATH, positions)
    _write_jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH, rotation_decisions)
    _write_jsonl(PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH, exposure_snapshots)
    _write_jsonl(EXPOSURE_STRESS_RESULTS_PATH, stress_results)
    _write_jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH, allocator_feedback)
    _write_jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH, threshold_feedback)
    _write_json(PORTFOLIO_REPLAY_SUMMARY_PATH, summary)
    _write_jsonl(PORTFOLIO_REPLAY_PROOF_PATH, proof_records)
    result = {
        "portfolio_replay_status": "ok",
        "summary": summary,
        "artifact_paths": portfolio_replay_artifact_paths(),
        "stress_result_count": len(stress_results),
    }
    result["reproducibility_hash"] = reproducibility_hash(result)
    return result


def write_portfolio_replay_fixture_files(
    policy: dict[str, Any],
    opportunities: list[dict[str, Any]],
    rotation_decisions: list[dict[str, Any]],
    exposure_snapshots: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, str]:
    payloads = {
        PORTFOLIO_REPLAY_POLICY_FIXTURE_PATH: {"fixture_version": "dopey-portfolio-replay-policy-fixture-v1", **policy},
        PORTFOLIO_REPLAY_OPPORTUNITIES_FIXTURE_PATH: {"fixture_version": "dopey-portfolio-replay-opportunities-v1", "case_count": len(opportunities), "records": opportunities, "paper_only": True, "live_blocked": True},
        PORTFOLIO_REPLAY_TIMELINE_CASES_FIXTURE_PATH: {"fixture_version": "dopey-portfolio-replay-timeline-cases-v1", "case_count": len(opportunities), "records": opportunities, "paper_only": True, "live_blocked": True},
        EXPECTED_PORTFOLIO_ROTATION_DECISIONS_FIXTURE_PATH: {"fixture_version": "dopey-expected-portfolio-rotation-decisions-v1", "decision_count": len(rotation_decisions), "records": rotation_decisions, "paper_only": True, "live_blocked": True},
        EXPECTED_PORTFOLIO_EXPOSURE_SNAPSHOTS_FIXTURE_PATH: {"fixture_version": "dopey-expected-portfolio-exposure-snapshots-v1", "snapshot_count": len(exposure_snapshots), "records": exposure_snapshots, "paper_only": True, "live_blocked": True},
        EXPECTED_PORTFOLIO_REPLAY_SUMMARY_FIXTURE_PATH: {"fixture_version": "dopey-expected-portfolio-replay-summary-v1", "summary": summary, "paper_only": True, "live_blocked": True},
    }
    for path, payload in payloads.items():
        _write_json(path, payload)
    return {path.stem: str(path) for path in payloads}


def portfolio_replay_artifact_paths() -> dict[str, str]:
    return {
        "portfolio_replay_policy": str(PORTFOLIO_REPLAY_POLICY_PATH),
        "portfolio_replay_opportunities": str(PORTFOLIO_REPLAY_OPPORTUNITIES_PATH),
        "portfolio_states": str(PORTFOLIO_STATES_PATH),
        "portfolio_positions": str(PORTFOLIO_POSITIONS_PATH),
        "portfolio_rotation_decisions": str(PORTFOLIO_ROTATION_DECISIONS_PATH),
        "portfolio_exposure_snapshots": str(PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH),
        "exposure_stress_results": str(EXPOSURE_STRESS_RESULTS_PATH),
        "portfolio_allocator_feedback": str(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH),
        "portfolio_threshold_feedback": str(PORTFOLIO_THRESHOLD_FEEDBACK_PATH),
        "portfolio_replay_summary": str(PORTFOLIO_REPLAY_SUMMARY_PATH),
        "portfolio_replay_proof": str(PORTFOLIO_REPLAY_PROOF_PATH),
    }


def lifecycle_feedback_summary() -> dict[str, Any]:
    if not LIFECYCLE_PORTFOLIO_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "portfolio_replay_lifecycle_feedback",
            "lifecycle_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_portfolio_mutation_allowed": False,
        }
    records = _read_jsonl(LIFECYCLE_PORTFOLIO_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        action = str(record.get("feedback_action", record.get("feedback_type", "")))
        action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "portfolio_replay_lifecycle_feedback",
        "lifecycle_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_portfolio_mutation_allowed": False,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
        output.append(payload)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in output) + ("\n" if output else ""), encoding="utf-8")


def main() -> int:
    result = run_portfolio_replay()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["portfolio_replay_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
