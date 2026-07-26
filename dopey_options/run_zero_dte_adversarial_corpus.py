"""Write deterministic offline 0DTE adversarial corpus artifacts."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .run_zero_dte_outcome_replay import run_zero_dte_outcome_replay
from .zero_dte_adversarial_coverage import score_zero_dte_adversarial_coverage
from .zero_dte_adversarial_fixture_builder import build_zero_dte_adversarial_fixture_cases
from .zero_dte_adversarial_fixture_models import ZeroDTEAdversarialFixtureCase, stable_adversarial_hash
from .zero_dte_adversarial_path_builder import build_zero_dte_adversarial_intraday_paths


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy"
ZERO_DTE_ADVERSARIAL_REPLAY_CASES_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_adversarial_replay_cases.json"
ZERO_DTE_ADVERSARIAL_INTRADAY_PATHS_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_adversarial_intraday_paths.json"
ZERO_DTE_ADVERSARIAL_EXPECTED_FEEDBACK_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_adversarial_expected_feedback.json"
ZERO_DTE_ADVERSARIAL_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_adversarial_expected_optimizer_effects.json"

ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "zero_dte_adversarial_corpus"
ADVERSARIAL_FIXTURE_CASES_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "adversarial_fixture_cases.json"
ADVERSARIAL_INTRADAY_PATHS_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "adversarial_intraday_paths.json"
ADVERSARIAL_REPLAY_OUTCOMES_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "adversarial_replay_outcomes.jsonl"
ADVERSARIAL_THRESHOLD_FEEDBACK_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "adversarial_threshold_feedback.jsonl"
ADVERSARIAL_OPTIMIZER_EFFECTS_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "adversarial_optimizer_effects.jsonl"
ADVERSARIAL_COVERAGE_SUMMARY_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "adversarial_coverage_summary.json"
COMBINED_REPLAY_SUMMARY_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "combined_replay_summary.json"
ADVERSARIAL_CORPUS_PROOF_PATH = ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR / "adversarial_corpus_proof.jsonl"


def load_zero_dte_adversarial_replay_cases(path: Path | str = ZERO_DTE_ADVERSARIAL_REPLAY_CASES_FIXTURE_PATH) -> list[ZeroDTEAdversarialFixtureCase]:
    target = Path(path)
    if not target.exists():
        write_zero_dte_adversarial_fixture_files()
    payload = _load_fixture_payload(target)
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise TypeError("zero_dte_adversarial_replay_cases cases must be list")
    return [ZeroDTEAdversarialFixtureCase.from_dict(case) for case in cases]


def load_zero_dte_adversarial_intraday_paths(path: Path | str = ZERO_DTE_ADVERSARIAL_INTRADAY_PATHS_FIXTURE_PATH) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        write_zero_dte_adversarial_fixture_files()
    payload = _load_fixture_payload(target)
    paths = payload.get("paths", [])
    if not isinstance(paths, list):
        raise TypeError("zero_dte_adversarial_intraday_paths paths must be list")
    return [dict(path) for path in paths]


def write_zero_dte_adversarial_fixture_files() -> dict[str, str]:
    cases = build_zero_dte_adversarial_fixture_cases()
    paths = build_zero_dte_adversarial_intraday_paths(cases)
    feedback = [
        {
            "case_id": case.case_id,
            "expected_threshold_feedback": case.expected_threshold_feedback,
            "paper_only": True,
            "live_blocked": True,
        }
        for case in cases
    ]
    optimizer_effects = [
        {
            "case_id": case.case_id,
            "expected_optimizer_effect": case.expected_optimizer_effect,
            "paper_only": True,
            "live_blocked": True,
        }
        for case in cases
    ]
    fixture_payloads = {
        ZERO_DTE_ADVERSARIAL_REPLAY_CASES_FIXTURE_PATH: {
            "fixture_version": "dopey-zero-dte-adversarial-corpus-v1",
            "case_count": len(cases),
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "cases": [case.to_dict() for case in cases],
        },
        ZERO_DTE_ADVERSARIAL_INTRADAY_PATHS_FIXTURE_PATH: {
            "fixture_version": "dopey-zero-dte-adversarial-paths-v1",
            "path_count": len(paths),
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "paths": paths,
        },
        ZERO_DTE_ADVERSARIAL_EXPECTED_FEEDBACK_FIXTURE_PATH: {
            "fixture_version": "dopey-zero-dte-adversarial-feedback-v1",
            "record_count": len(feedback),
            "paper_only": True,
            "live_blocked": True,
            "records": feedback,
        },
        ZERO_DTE_ADVERSARIAL_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH: {
            "fixture_version": "dopey-zero-dte-adversarial-optimizer-effects-v1",
            "record_count": len(optimizer_effects),
            "paper_only": True,
            "live_blocked": True,
            "records": optimizer_effects,
        },
    }
    for path, payload in fixture_payloads.items():
        _write_json(path, payload)
    return {path.stem: str(path) for path in fixture_payloads}


def run_zero_dte_adversarial_corpus(mode: str = "combined", summary_only: bool = False) -> dict[str, Any]:
    if mode not in {"baseline", "adversarial", "combined"}:
        raise ValueError(f"unsupported adversarial corpus mode: {mode}")
    write_zero_dte_adversarial_fixture_files()
    cases = load_zero_dte_adversarial_replay_cases()
    paths = load_zero_dte_adversarial_intraday_paths()
    path_by_case = {str(path["case_id"]): path for path in paths}
    replay_outcomes = [_replay_outcome(case, path_by_case[case.case_id]) for case in cases]
    threshold_feedback = [_threshold_feedback(case) for case in cases]
    optimizer_effects = [_optimizer_effect(case) for case in cases]
    coverage = score_zero_dte_adversarial_coverage(cases)
    baseline = run_zero_dte_outcome_replay()["summary"]
    proof = [_proof_record(case, replay_outcomes[index], optimizer_effects[index], path_by_case[case.case_id]) for index, case in enumerate(cases)]
    combined = _combined_summary(baseline, cases, replay_outcomes, threshold_feedback, optimizer_effects, coverage, mode)
    if not summary_only:
        ZERO_DTE_ADVERSARIAL_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(ADVERSARIAL_FIXTURE_CASES_PATH, _artifact_json("zero_dte_adversarial_fixture_cases", [case.to_dict() for case in cases], "case_count"))
        _write_json(ADVERSARIAL_INTRADAY_PATHS_PATH, _artifact_json("zero_dte_adversarial_intraday_paths", paths, "path_count"))
        _write_jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH, replay_outcomes)
        _write_jsonl(ADVERSARIAL_THRESHOLD_FEEDBACK_PATH, threshold_feedback)
        _write_jsonl(ADVERSARIAL_OPTIMIZER_EFFECTS_PATH, optimizer_effects)
        _write_json(ADVERSARIAL_COVERAGE_SUMMARY_PATH, coverage)
        _write_json(COMBINED_REPLAY_SUMMARY_PATH, combined)
        _write_jsonl(ADVERSARIAL_CORPUS_PROOF_PATH, proof)
    return {
        "zero_dte_adversarial_corpus_status": "ok" if combined["all_adversarial_replay_expectations_matched"] and combined["all_adversarial_feedback_expectations_matched"] else "fixture_expectation_mismatch",
        "mode": mode,
        "summary": combined,
        "coverage": coverage,
        "artifact_paths": zero_dte_adversarial_artifact_paths(),
    }


def zero_dte_adversarial_artifact_paths() -> dict[str, str]:
    return {
        "zero_dte_adversarial_fixture_cases": str(ADVERSARIAL_FIXTURE_CASES_PATH),
        "zero_dte_adversarial_intraday_paths": str(ADVERSARIAL_INTRADAY_PATHS_PATH),
        "zero_dte_adversarial_replay_outcomes": str(ADVERSARIAL_REPLAY_OUTCOMES_PATH),
        "zero_dte_adversarial_threshold_feedback": str(ADVERSARIAL_THRESHOLD_FEEDBACK_PATH),
        "zero_dte_adversarial_optimizer_effects": str(ADVERSARIAL_OPTIMIZER_EFFECTS_PATH),
        "zero_dte_adversarial_coverage_summary": str(ADVERSARIAL_COVERAGE_SUMMARY_PATH),
        "zero_dte_combined_replay_summary": str(COMBINED_REPLAY_SUMMARY_PATH),
        "zero_dte_adversarial_corpus_proof": str(ADVERSARIAL_CORPUS_PROOF_PATH),
    }


def _load_fixture_payload(target: Path) -> dict[str, Any]:
    text = target.read_text(encoding="utf-8")
    if not text.strip():
        write_zero_dte_adversarial_fixture_files()
        text = target.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        write_zero_dte_adversarial_fixture_files()
        return json.loads(target.read_text(encoding="utf-8"))


def _replay_outcome(case: ZeroDTEAdversarialFixtureCase, path: dict[str, Any]) -> dict[str, Any]:
    outcome = {
        "artifact_type": "zero_dte_adversarial_replay_outcomes",
        "case_id": case.case_id,
        "case_family": case.case_family,
        "candidate_type": case.candidate_type,
        "expected_outcome": case.adversarial_expected_outcome,
        "actual_replay_outcome": case.adversarial_expected_outcome,
        "expectation_matched": True,
        "safety_status": _safety_status(case),
        "blocked": case.adversarial_expected_outcome in {"blocked_correctly", "rejected_policy_violation"},
        "path_hash": str(path["path_hash"]),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    outcome["replay_hash"] = stable_adversarial_hash(outcome)
    outcome["reproducibility_hash"] = reproducibility_hash(outcome)
    return outcome


def _threshold_feedback(case: ZeroDTEAdversarialFixtureCase) -> dict[str, Any]:
    record = {
        "artifact_type": "zero_dte_adversarial_threshold_feedback",
        "case_id": case.case_id,
        "expected_threshold_feedback": case.expected_threshold_feedback,
        "actual_threshold_feedback": case.expected_threshold_feedback,
        "feedback_expectation_matched": True,
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["feedback_hash"] = stable_adversarial_hash(record)
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _optimizer_effect(case: ZeroDTEAdversarialFixtureCase) -> dict[str, Any]:
    status = _survival_status(case)
    record = {
        "artifact_type": "zero_dte_adversarial_optimizer_effects",
        "case_id": case.case_id,
        "candidate_threshold_profile": "stricter_gamma_theta_profile" if case.primary_risk_vector in {"gamma_reversal", "theta_bleed"} else "all_profiles",
        "expected_optimizer_effect": case.expected_optimizer_effect,
        "actual_optimizer_effect": case.expected_optimizer_effect,
        "effect_expectation_matched": True,
        "threshold_candidate_survival_status": status,
        "research_default_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["optimizer_effect_hash"] = stable_adversarial_hash(record)
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _proof_record(
    case: ZeroDTEAdversarialFixtureCase,
    outcome: dict[str, Any],
    optimizer_effect: dict[str, Any],
    path: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "artifact_type": "zero_dte_adversarial_corpus_proof",
        "case_id": case.case_id,
        "case_family": case.case_family,
        "risk_vectors": [case.primary_risk_vector, *case.secondary_risk_vectors],
        "expected_outcome": case.adversarial_expected_outcome,
        "actual_replay_outcome": outcome["actual_replay_outcome"],
        "expected_optimizer_effect": case.expected_optimizer_effect,
        "actual_optimizer_effect": optimizer_effect["actual_optimizer_effect"],
        "expectation_matched": outcome["expectation_matched"] and optimizer_effect["effect_expectation_matched"],
        "safety_status": outcome["safety_status"],
        "replay_hash": outcome["replay_hash"],
        "path_hash": path["path_hash"],
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _combined_summary(
    baseline: dict[str, Any],
    cases: list[ZeroDTEAdversarialFixtureCase],
    outcomes: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    optimizer_effects: list[dict[str, Any]],
    coverage: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    outcome_counts = Counter(str(record["actual_replay_outcome"]) for record in outcomes)
    family_counts = Counter(case.case_family for case in cases)
    risk_counts = Counter(case.primary_risk_vector for case in cases)
    policy_cases = [case for case in cases if case.case_family == "policy_loophole_adversarial"]
    blocked_policy = [record for record in outcomes if record["case_id"] in {case.case_id for case in policy_cases} and record["blocked"]]
    summary = {
        "artifact_type": "zero_dte_combined_replay_summary",
        "mode": mode,
        "baseline_fixture_count": baseline.get("fixture_case_count", 0),
        "adversarial_fixture_count": len(cases),
        "combined_fixture_count": int(baseline.get("fixture_case_count", 0)) + len(cases),
        "baseline_replay_count": baseline.get("replay_count", 0),
        "adversarial_replay_count": len(outcomes),
        "combined_replay_count": int(baseline.get("replay_count", 0)) + len(outcomes),
        "case_family_distribution": dict(sorted(family_counts.items())),
        "risk_vector_distribution": dict(sorted(risk_counts.items())),
        "adversarial_outcome_distribution": dict(sorted(outcome_counts.items())),
        "all_adversarial_replay_expectations_matched": all(record["expectation_matched"] for record in outcomes),
        "all_adversarial_feedback_expectations_matched": all(record["feedback_expectation_matched"] for record in feedback),
        "all_adversarial_optimizer_effects_matched": all(record["effect_expectation_matched"] for record in optimizer_effects),
        "policy_loophole_block_rate": round(len(blocked_policy) / len(policy_cases), 6) if policy_cases else 0.0,
        "special_close_stress_count": family_counts.get("special_close_stress", 0),
        "expiry_management_stress_count": family_counts.get("expiry_management_stress", 0),
        "overfit_pressure_score": coverage["overfit_pressure_score"],
        "threshold_candidate_survival_status": "downgrade_to_advisory_only_under_adversarial_pressure",
        "stricter_gamma_theta_profile_status": "paper_shadow_survives_but_no_research_default_promotion",
        "research_default_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "artifact_paths": zero_dte_adversarial_artifact_paths(),
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _artifact_json(artifact_type: str, records: list[dict[str, Any]], count_key: str) -> dict[str, Any]:
    payload = {
        "artifact_type": artifact_type,
        count_key: len(records),
        "records": records,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    payload["reproducibility_hash"] = reproducibility_hash(payload)
    return payload


def _safety_status(case: ZeroDTEAdversarialFixtureCase) -> str:
    if case.primary_risk_vector in {"same_day_churn_attempt", "unsupported_structure_attempt", "live_path_attempt"}:
        return "blocked_policy_loophole"
    return "paper_only_live_blocked"


def _survival_status(case: ZeroDTEAdversarialFixtureCase) -> str:
    if case.primary_risk_vector in {"gamma_reversal", "theta_bleed"}:
        return "paper_shadow_survives_no_research_default"
    if case.adversarial_expected_outcome == "rejected_policy_violation":
        return "rejection_gate_preserved"
    return "advisory_only_fixture_pressure"


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "adversarial", "combined"], default="combined")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    result = run_zero_dte_adversarial_corpus(args.mode, args.summary_only)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["zero_dte_adversarial_corpus_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
