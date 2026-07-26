"""Write deterministic portfolio stress ladder artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .stress_ladder_replay_engine import build_stress_ladder_bundle


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "portfolio"
STRESS_LADDER_POLICY_FIXTURE_PATH = FIXTURE_DIR / "stress_ladder_policy.json"
CRISIS_MODE_THROTTLE_PROFILES_FIXTURE_PATH = FIXTURE_DIR / "crisis_mode_throttle_profiles.json"
STRESS_LADDER_REPLAY_CASES_FIXTURE_PATH = FIXTURE_DIR / "stress_ladder_replay_cases.json"
EXPECTED_STRESS_TRANSITIONS_FIXTURE_PATH = FIXTURE_DIR / "expected_stress_transitions.json"
EXPECTED_CRISIS_THROTTLES_FIXTURE_PATH = FIXTURE_DIR / "expected_crisis_throttles.json"
EXPECTED_STRESS_LADDER_SUMMARY_FIXTURE_PATH = FIXTURE_DIR / "expected_stress_ladder_summary.json"

PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "portfolio_stress_ladder"
STRESS_LADDER_POLICY_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "stress_ladder_policy.json"
CRISIS_MODE_THROTTLE_PROFILES_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "crisis_mode_throttle_profiles.json"
STRESS_LADDER_REPLAY_CASES_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "stress_ladder_replay_cases.json"
STRESS_LEVEL_EVALUATIONS_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "stress_level_evaluations.jsonl"
STRESS_TRANSITION_DECISIONS_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "stress_transition_decisions.jsonl"
CRISIS_THROTTLE_RESULTS_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "crisis_throttle_results.jsonl"
CRISIS_RECOVERY_RESULTS_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "crisis_recovery_results.jsonl"
CRISIS_ALLOCATOR_FEEDBACK_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "crisis_allocator_feedback.jsonl"
CRISIS_THRESHOLD_FEEDBACK_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "crisis_threshold_feedback.jsonl"
STRESS_LADDER_SUMMARY_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "stress_ladder_summary.json"
STRESS_LADDER_PROOF_PATH = PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR / "stress_ladder_proof.jsonl"
INCIDENT_STRESS_LADDER_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "incident_response" / "incident_stress_ladder_feedback.jsonl"
LIFECYCLE_STRESS_LADDER_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "lifecycle" / "lifecycle_feedback_stress_ladder.jsonl"


def run_portfolio_stress_ladder() -> dict[str, Any]:
    bundle = build_stress_ladder_bundle()
    ladder = bundle["ladder"].to_dict()
    profiles = [record.to_dict() for record in bundle["throttle_profiles"]]
    cases = list(bundle["cases"])
    evaluations = list(bundle["stress_level_evaluations"])
    transitions = [record.to_dict() for record in bundle["transition_decisions"]]
    throttles = list(bundle["crisis_throttle_results"])
    recoveries = list(bundle["crisis_recovery_results"])
    allocator_feedback = list(bundle["crisis_allocator_feedback"])
    threshold_feedback = list(bundle["crisis_threshold_feedback"])
    proof_records = list(bundle["stress_ladder_proof"])
    summary = dict(bundle["summary"])
    summary["incident_feedback_summary"] = incident_feedback_summary()
    summary["incident_feedback_loaded"] = bool(summary["incident_feedback_summary"].get("incident_feedback_loaded", False))
    summary["incident_feedback_actions"] = summary["incident_feedback_summary"].get("feedback_action_distribution", {})
    summary["lifecycle_feedback_summary"] = lifecycle_feedback_summary()
    summary["lifecycle_feedback_loaded"] = bool(summary["lifecycle_feedback_summary"].get("lifecycle_feedback_loaded", False))
    summary["lifecycle_feedback_actions"] = summary["lifecycle_feedback_summary"].get("feedback_action_distribution", {})
    summary["reproducibility_hash"] = reproducibility_hash({key: value for key, value in summary.items() if key != "reproducibility_hash"})
    write_stress_ladder_fixture_files(ladder, profiles, cases, transitions, throttles, summary)
    PORTFOLIO_STRESS_LADDER_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(STRESS_LADDER_POLICY_PATH, {"artifact_type": "portfolio_stress_ladder_policy", **ladder})
    _write_json(CRISIS_MODE_THROTTLE_PROFILES_PATH, {"artifact_type": "crisis_mode_throttle_profiles", "profiles": profiles, "profile_count": len(profiles), "paper_only": True, "live_blocked": True})
    _write_json(STRESS_LADDER_REPLAY_CASES_PATH, {"artifact_type": "stress_ladder_replay_cases", "records": cases, "stress_case_count": len(cases), "paper_only": True, "live_blocked": True})
    _write_jsonl(STRESS_LEVEL_EVALUATIONS_PATH, evaluations)
    _write_jsonl(STRESS_TRANSITION_DECISIONS_PATH, transitions)
    _write_jsonl(CRISIS_THROTTLE_RESULTS_PATH, throttles)
    _write_jsonl(CRISIS_RECOVERY_RESULTS_PATH, recoveries)
    _write_jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH, allocator_feedback)
    _write_jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH, threshold_feedback)
    _write_json(STRESS_LADDER_SUMMARY_PATH, summary)
    _write_jsonl(STRESS_LADDER_PROOF_PATH, proof_records)
    result = {
        "portfolio_stress_ladder_status": "ok",
        "summary": summary,
        "artifact_paths": portfolio_stress_ladder_artifact_paths(),
    }
    result["reproducibility_hash"] = reproducibility_hash(result)
    return result


def write_stress_ladder_fixture_files(
    ladder: dict[str, Any],
    profiles: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    throttles: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, str]:
    payloads = {
        STRESS_LADDER_POLICY_FIXTURE_PATH: {"fixture_version": "dopey-stress-ladder-policy-v1", **ladder},
        CRISIS_MODE_THROTTLE_PROFILES_FIXTURE_PATH: {"fixture_version": "dopey-crisis-mode-throttle-profiles-v1", "profile_count": len(profiles), "records": profiles, "paper_only": True, "live_blocked": True},
        STRESS_LADDER_REPLAY_CASES_FIXTURE_PATH: {"fixture_version": "dopey-stress-ladder-replay-cases-v1", "stress_case_count": len(cases), "records": cases, "paper_only": True, "live_blocked": True},
        EXPECTED_STRESS_TRANSITIONS_FIXTURE_PATH: {"fixture_version": "dopey-expected-stress-transitions-v1", "transition_count": len(transitions), "records": transitions, "paper_only": True, "live_blocked": True},
        EXPECTED_CRISIS_THROTTLES_FIXTURE_PATH: {"fixture_version": "dopey-expected-crisis-throttles-v1", "throttle_count": len(throttles), "records": throttles, "paper_only": True, "live_blocked": True},
        EXPECTED_STRESS_LADDER_SUMMARY_FIXTURE_PATH: {"fixture_version": "dopey-expected-stress-ladder-summary-v1", "summary": summary, "paper_only": True, "live_blocked": True},
    }
    for path, payload in payloads.items():
        _write_json(path, payload)
    return {path.stem: str(path) for path in payloads}


def portfolio_stress_ladder_artifact_paths() -> dict[str, str]:
    return {
        "portfolio_stress_ladder_policy": str(STRESS_LADDER_POLICY_PATH),
        "crisis_mode_throttle_profiles": str(CRISIS_MODE_THROTTLE_PROFILES_PATH),
        "stress_ladder_replay_cases": str(STRESS_LADDER_REPLAY_CASES_PATH),
        "stress_level_evaluations": str(STRESS_LEVEL_EVALUATIONS_PATH),
        "stress_transition_decisions": str(STRESS_TRANSITION_DECISIONS_PATH),
        "crisis_throttle_results": str(CRISIS_THROTTLE_RESULTS_PATH),
        "crisis_recovery_results": str(CRISIS_RECOVERY_RESULTS_PATH),
        "crisis_allocator_feedback": str(CRISIS_ALLOCATOR_FEEDBACK_PATH),
        "crisis_threshold_feedback": str(CRISIS_THRESHOLD_FEEDBACK_PATH),
        "stress_ladder_summary": str(STRESS_LADDER_SUMMARY_PATH),
        "stress_ladder_proof": str(STRESS_LADDER_PROOF_PATH),
    }


def incident_feedback_summary() -> dict[str, Any]:
    if not INCIDENT_STRESS_LADDER_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "portfolio_stress_ladder_incident_feedback",
            "incident_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_stress_ladder_mutation_allowed": False,
        }
    records = _read_jsonl(INCIDENT_STRESS_LADDER_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        actions = record.get("stress_ladder_actions", [])
        if not isinstance(actions, list):
            actions = []
        for action_value in actions:
            action = str(action_value)
            action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "portfolio_stress_ladder_incident_feedback",
        "incident_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_stress_ladder_mutation_allowed": False,
    }


def lifecycle_feedback_summary() -> dict[str, Any]:
    if not LIFECYCLE_STRESS_LADDER_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "portfolio_stress_ladder_lifecycle_feedback",
            "lifecycle_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_stress_ladder_mutation_allowed": False,
        }
    records = _read_jsonl(LIFECYCLE_STRESS_LADDER_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        action = str(record.get("feedback_action", record.get("feedback_type", "")))
        action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "portfolio_stress_ladder_lifecycle_feedback",
        "lifecycle_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_stress_ladder_mutation_allowed": False,
    }


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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    result = run_portfolio_stress_ladder()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["portfolio_stress_ladder_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
