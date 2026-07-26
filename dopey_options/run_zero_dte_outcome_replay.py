"""Write deterministic offline 0DTE expiry/outcome replay artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .zero_dte_replay_engine import (
    ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH,
    ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH,
    evaluate_zero_dte_replay_fixture_cases,
    load_zero_dte_intraday_paths,
    load_zero_dte_outcome_replay_cases,
    replay_proof_records,
    zero_dte_replay_summary,
)
from .zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds


REPO_ROOT = Path(__file__).resolve().parent.parent
ZERO_DTE_REPLAY_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "zero_dte_replay"
ZERO_DTE_REPLAY_INPUTS_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_replay_inputs.jsonl"
ZERO_DTE_INTRADAY_STATES_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_intraday_states.jsonl"
ZERO_DTE_REPLAY_DECISION_POINTS_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_replay_decision_points.jsonl"
ZERO_DTE_REPLAY_OUTCOMES_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_replay_outcomes.jsonl"
ZERO_DTE_EXPIRY_MANAGEMENT_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_expiry_management.jsonl"
ZERO_DTE_THRESHOLD_FEEDBACK_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_threshold_feedback.jsonl"
ZERO_DTE_REPLAY_SUMMARY_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_replay_summary.json"
ZERO_DTE_REPLAY_PROOF_PATH = ZERO_DTE_REPLAY_ARTIFACT_DIR / "zero_dte_replay_proof.jsonl"


def run_zero_dte_outcome_replay() -> dict[str, Any]:
    thresholds = load_default_zero_dte_risk_thresholds()
    cases = load_zero_dte_outcome_replay_cases(ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH)
    paths = load_zero_dte_intraday_paths(ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH)
    evaluated = evaluate_zero_dte_replay_fixture_cases(cases, paths, thresholds)
    details = evaluated["replay_details"]
    inputs = [record["replay"]["input"].to_dict() for record in details]
    state_records = _state_records(details)
    decision_points = _decision_point_records(details)
    outcomes = [record["replay"]["outcome"].to_dict() for record in details]
    expiry_records = [record["replay"]["expiry_management"].to_dict() for record in details]
    feedback_records = [record["replay"]["threshold_feedback"].to_dict() for record in details]
    proof_records = replay_proof_records(details)
    summary = zero_dte_replay_summary(details)
    summary["artifact_type"] = "zero_dte_replay_summary"
    summary["source_fixture_paths"] = {
        "cases": str(ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH),
        "intraday_paths": str(ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH),
    }
    summary["artifact_paths"] = zero_dte_replay_artifact_paths()
    summary["reproducibility_hash"] = reproducibility_hash({k: v for k, v in summary.items() if k != "reproducibility_hash"})
    ZERO_DTE_REPLAY_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(ZERO_DTE_REPLAY_INPUTS_PATH, _with_hashes(inputs))
    _write_jsonl(ZERO_DTE_INTRADAY_STATES_PATH, _with_hashes(state_records))
    _write_jsonl(ZERO_DTE_REPLAY_DECISION_POINTS_PATH, _with_hashes(decision_points))
    _write_jsonl(ZERO_DTE_REPLAY_OUTCOMES_PATH, _with_hashes(outcomes))
    _write_jsonl(ZERO_DTE_EXPIRY_MANAGEMENT_PATH, _with_hashes(expiry_records))
    _write_jsonl(ZERO_DTE_THRESHOLD_FEEDBACK_PATH, _with_hashes(feedback_records))
    _write_json(ZERO_DTE_REPLAY_SUMMARY_PATH, summary)
    _write_jsonl(ZERO_DTE_REPLAY_PROOF_PATH, _with_hashes(proof_records))
    return {
        "zero_dte_outcome_replay_status": "ok" if summary["all_expectations_matched"] and summary["all_feedback_expectations_matched"] else "fixture_expectation_mismatch",
        "summary": summary,
        "artifact_paths": zero_dte_replay_artifact_paths(),
    }


def zero_dte_replay_artifact_paths() -> dict[str, str]:
    return {
        "zero_dte_replay_inputs": str(ZERO_DTE_REPLAY_INPUTS_PATH),
        "zero_dte_intraday_states": str(ZERO_DTE_INTRADAY_STATES_PATH),
        "zero_dte_replay_decision_points": str(ZERO_DTE_REPLAY_DECISION_POINTS_PATH),
        "zero_dte_replay_outcomes": str(ZERO_DTE_REPLAY_OUTCOMES_PATH),
        "zero_dte_expiry_management": str(ZERO_DTE_EXPIRY_MANAGEMENT_PATH),
        "zero_dte_threshold_feedback": str(ZERO_DTE_THRESHOLD_FEEDBACK_PATH),
        "zero_dte_replay_summary": str(ZERO_DTE_REPLAY_SUMMARY_PATH),
        "zero_dte_replay_proof": str(ZERO_DTE_REPLAY_PROOF_PATH),
    }


def _state_records(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in details:
        replay_input = record["replay"]["input"]
        for state in record["replay"]["states"]:
            records.append({
                "replay_id": replay_input.replay_id,
                "candidate_id": replay_input.candidate_id,
                "fixture_path_id": replay_input.fixture_path_id,
                **state.to_dict(),
                "paper_only": True,
                "live_blocked": True,
                "no_real_market_data": True,
                "no_broker": True,
            })
    return records


def _decision_point_records(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in details:
        replay_input = record["replay"]["input"]
        for point in record["replay"]["decision_points"]:
            records.append({
                "replay_id": replay_input.replay_id,
                "candidate_id": replay_input.candidate_id,
                "fixture_path_id": replay_input.fixture_path_id,
                **point.to_dict(),
                "no_real_market_data": True,
                "no_broker": True,
            })
    return records


def _with_hashes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item["reproducibility_hash"] = reproducibility_hash({k: v for k, v in item.items() if k != "reproducibility_hash"})
        output.append(item)
    return output


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({k: v for k, v in payload.items() if k != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_zero_dte_outcome_replay()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["zero_dte_outcome_replay_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
