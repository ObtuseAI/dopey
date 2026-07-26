"""Write deterministic incident response rehearsal fixtures and artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .kill_switch_rehearsal_engine import build_incident_response_bundle


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "incident"
INCIDENT_TAXONOMY_FIXTURE_PATH = FIXTURE_DIR / "incident_taxonomy.json"
INCIDENT_REHEARSAL_CASES_FIXTURE_PATH = FIXTURE_DIR / "incident_rehearsal_cases.json"
EXPECTED_KILL_SWITCH_STATES_FIXTURE_PATH = FIXTURE_DIR / "expected_kill_switch_states.json"
EXPECTED_INCIDENT_RESPONSES_FIXTURE_PATH = FIXTURE_DIR / "expected_incident_responses.json"
EXPECTED_RECOVERY_PLANS_FIXTURE_PATH = FIXTURE_DIR / "expected_recovery_plans.json"
EXPECTED_INCIDENT_SUMMARY_FIXTURE_PATH = FIXTURE_DIR / "expected_incident_summary.json"

INCIDENT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "incident_response"
INCIDENT_TAXONOMY_PATH = INCIDENT_ARTIFACT_DIR / "incident_taxonomy.json"
INCIDENT_REHEARSAL_CASES_PATH = INCIDENT_ARTIFACT_DIR / "incident_rehearsal_cases.json"
INCIDENT_SIGNALS_PATH = INCIDENT_ARTIFACT_DIR / "incident_signals.jsonl"
KILL_SWITCH_STATES_PATH = INCIDENT_ARTIFACT_DIR / "kill_switch_states.jsonl"
INCIDENT_RESPONSE_DECISIONS_PATH = INCIDENT_ARTIFACT_DIR / "incident_response_decisions.jsonl"
INCIDENT_RECOVERY_PLANS_PATH = INCIDENT_ARTIFACT_DIR / "incident_recovery_plans.jsonl"
INCIDENT_ALLOCATOR_FEEDBACK_PATH = INCIDENT_ARTIFACT_DIR / "incident_allocator_feedback.jsonl"
INCIDENT_THRESHOLD_FEEDBACK_PATH = INCIDENT_ARTIFACT_DIR / "incident_threshold_feedback.jsonl"
INCIDENT_STRESS_LADDER_FEEDBACK_PATH = INCIDENT_ARTIFACT_DIR / "incident_stress_ladder_feedback.jsonl"
INCIDENT_REHEARSAL_SUMMARY_PATH = INCIDENT_ARTIFACT_DIR / "incident_rehearsal_summary.json"
INCIDENT_RESPONSE_PROOF_PATH = INCIDENT_ARTIFACT_DIR / "incident_response_proof.jsonl"
LIFECYCLE_INCIDENT_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "lifecycle" / "lifecycle_feedback_incident.jsonl"


def run_incident_response_rehearsal() -> dict[str, Any]:
    bundle = build_incident_response_bundle()
    taxonomy = list(bundle["taxonomy"])
    cases = list(bundle["cases"])
    signals = list(bundle["incident_signals"])
    states = list(bundle["kill_switch_states"])
    responses = list(bundle["incident_response_decisions"])
    recoveries = list(bundle["incident_recovery_plans"])
    allocator_feedback = list(bundle["incident_allocator_feedback"])
    threshold_feedback = list(bundle["incident_threshold_feedback"])
    stress_ladder_feedback = list(bundle["incident_stress_ladder_feedback"])
    proof_records = list(bundle["incident_response_proof"])
    summary = dict(bundle["summary"])
    summary["lifecycle_feedback_summary"] = lifecycle_feedback_summary()
    summary["lifecycle_feedback_loaded"] = bool(summary["lifecycle_feedback_summary"].get("lifecycle_feedback_loaded", False))
    summary["lifecycle_feedback_actions"] = summary["lifecycle_feedback_summary"].get("feedback_action_distribution", {})
    write_incident_fixture_files(taxonomy, cases, states, responses, recoveries, summary)
    INCIDENT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(INCIDENT_TAXONOMY_PATH, {"artifact_type": "incident_taxonomy", "taxonomy_version": summary["incident_response_version"], "records": taxonomy, "taxonomy_count": len(taxonomy), "paper_only": True, "live_blocked": True})
    _write_json(INCIDENT_REHEARSAL_CASES_PATH, {"artifact_type": "incident_rehearsal_cases", "records": cases, "incident_case_count": len(cases), "paper_only": True, "live_blocked": True})
    _write_jsonl(INCIDENT_SIGNALS_PATH, signals)
    _write_jsonl(KILL_SWITCH_STATES_PATH, states)
    _write_jsonl(INCIDENT_RESPONSE_DECISIONS_PATH, responses)
    _write_jsonl(INCIDENT_RECOVERY_PLANS_PATH, recoveries)
    _write_jsonl(INCIDENT_ALLOCATOR_FEEDBACK_PATH, allocator_feedback)
    _write_jsonl(INCIDENT_THRESHOLD_FEEDBACK_PATH, threshold_feedback)
    _write_jsonl(INCIDENT_STRESS_LADDER_FEEDBACK_PATH, stress_ladder_feedback)
    _write_json(INCIDENT_REHEARSAL_SUMMARY_PATH, summary)
    _write_jsonl(INCIDENT_RESPONSE_PROOF_PATH, proof_records)
    result = {
        "incident_response_rehearsal_status": "ok",
        "summary": summary,
        "artifact_paths": incident_response_artifact_paths(),
    }
    result["reproducibility_hash"] = reproducibility_hash(result)
    return result


def write_incident_fixture_files(
    taxonomy: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    states: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    recoveries: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, str]:
    payloads = {
        INCIDENT_TAXONOMY_FIXTURE_PATH: {"fixture_version": "dopey-incident-taxonomy-v1", "records": taxonomy, "taxonomy_count": len(taxonomy), "paper_only": True, "live_blocked": True},
        INCIDENT_REHEARSAL_CASES_FIXTURE_PATH: {"fixture_version": "dopey-incident-rehearsal-cases-v1", "records": cases, "incident_case_count": len(cases), "paper_only": True, "live_blocked": True},
        EXPECTED_KILL_SWITCH_STATES_FIXTURE_PATH: {"fixture_version": "dopey-expected-kill-switch-states-v1", "records": states, "kill_switch_state_count": len(states), "paper_only": True, "live_blocked": True},
        EXPECTED_INCIDENT_RESPONSES_FIXTURE_PATH: {"fixture_version": "dopey-expected-incident-responses-v1", "records": responses, "incident_response_decision_count": len(responses), "paper_only": True, "live_blocked": True},
        EXPECTED_RECOVERY_PLANS_FIXTURE_PATH: {"fixture_version": "dopey-expected-recovery-plans-v1", "records": recoveries, "incident_recovery_plan_count": len(recoveries), "paper_only": True, "live_blocked": True},
        EXPECTED_INCIDENT_SUMMARY_FIXTURE_PATH: {"fixture_version": "dopey-expected-incident-summary-v1", "summary": summary, "paper_only": True, "live_blocked": True},
    }
    for path, payload in payloads.items():
        _write_json(path, payload)
    return {path.stem: str(path) for path in payloads}


def incident_response_artifact_paths() -> dict[str, str]:
    return {
        "incident_taxonomy": str(INCIDENT_TAXONOMY_PATH),
        "incident_rehearsal_cases": str(INCIDENT_REHEARSAL_CASES_PATH),
        "incident_signals": str(INCIDENT_SIGNALS_PATH),
        "kill_switch_states": str(KILL_SWITCH_STATES_PATH),
        "incident_response_decisions": str(INCIDENT_RESPONSE_DECISIONS_PATH),
        "incident_recovery_plans": str(INCIDENT_RECOVERY_PLANS_PATH),
        "incident_allocator_feedback": str(INCIDENT_ALLOCATOR_FEEDBACK_PATH),
        "incident_threshold_feedback": str(INCIDENT_THRESHOLD_FEEDBACK_PATH),
        "incident_stress_ladder_feedback": str(INCIDENT_STRESS_LADDER_FEEDBACK_PATH),
        "incident_rehearsal_summary": str(INCIDENT_REHEARSAL_SUMMARY_PATH),
        "incident_response_proof": str(INCIDENT_RESPONSE_PROOF_PATH),
    }


def lifecycle_feedback_summary() -> dict[str, Any]:
    if not LIFECYCLE_INCIDENT_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "incident_response_lifecycle_feedback",
            "lifecycle_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_incident_mutation_allowed": False,
        }
    records = _read_jsonl(LIFECYCLE_INCIDENT_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        action = str(record.get("feedback_action", record.get("feedback_type", "")))
        action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "incident_response_lifecycle_feedback",
        "lifecycle_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_incident_mutation_allowed": False,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    output = []
    for record in records:
        payload = dict(record)
        payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
        output.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in output) + ("\n" if output else ""), encoding="utf-8")


def main() -> int:
    result = run_incident_response_rehearsal()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["incident_response_rehearsal_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
