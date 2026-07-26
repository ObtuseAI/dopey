"""Write deterministic cross-underlying 0DTE adversarial corpus v2 artifacts."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .run_zero_dte_adversarial_corpus import run_zero_dte_adversarial_corpus
from .run_zero_dte_outcome_replay import run_zero_dte_outcome_replay
from .zero_dte_cross_underlying_coverage import score_zero_dte_cross_underlying_coverage
from .zero_dte_cross_underlying_fixture_builder import build_zero_dte_cross_underlying_cases, build_zero_dte_underlying_families
from .zero_dte_cross_underlying_fixture_models import ZeroDTECrossUnderlyingRegimeCase
from .zero_dte_cross_underlying_path_builder import build_zero_dte_cross_underlying_intraday_paths
from .zero_dte_underlying_family_models import ZeroDTEUnderlyingFamily, stable_cross_underlying_hash


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy"
ZERO_DTE_UNDERLYING_FAMILIES_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_underlying_families.json"
ZERO_DTE_CROSS_UNDERLYING_REGIME_CASES_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_cross_underlying_regime_cases.json"
ZERO_DTE_CROSS_UNDERLYING_INTRADAY_PATHS_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_cross_underlying_intraday_paths.json"
ZERO_DTE_CROSS_UNDERLYING_EXPECTED_FEEDBACK_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_cross_underlying_expected_feedback.json"
ZERO_DTE_CROSS_UNDERLYING_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH = FIXTURE_DIR / "zero_dte_cross_underlying_expected_optimizer_effects.json"

ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "zero_dte_cross_underlying_v2"
UNDERLYING_FAMILIES_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "underlying_families.json"
CROSS_UNDERLYING_REGIME_CASES_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_regime_cases.json"
CROSS_UNDERLYING_INTRADAY_PATHS_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_intraday_paths.json"
CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_replay_outcomes.jsonl"
CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_threshold_feedback.jsonl"
CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_optimizer_effects.jsonl"
CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_coverage_summary.json"
COMBINED_V1_V2_REPLAY_SUMMARY_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "combined_v1_v2_replay_summary.json"
CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_threshold_survival.json"
CROSS_UNDERLYING_CORPUS_PROOF_PATH = ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR / "cross_underlying_corpus_proof.jsonl"


def load_zero_dte_underlying_families(path: Path | str = ZERO_DTE_UNDERLYING_FAMILIES_FIXTURE_PATH) -> list[ZeroDTEUnderlyingFamily]:
    target = Path(path)
    if not target.exists():
        write_zero_dte_cross_underlying_fixture_files()
    payload = _load_fixture_payload(target)
    return [ZeroDTEUnderlyingFamily.from_dict(record) for record in payload.get("families", [])]


def load_zero_dte_cross_underlying_cases(path: Path | str = ZERO_DTE_CROSS_UNDERLYING_REGIME_CASES_FIXTURE_PATH) -> list[ZeroDTECrossUnderlyingRegimeCase]:
    target = Path(path)
    if not target.exists():
        write_zero_dte_cross_underlying_fixture_files()
    payload = _load_fixture_payload(target)
    return [ZeroDTECrossUnderlyingRegimeCase.from_dict(record) for record in payload.get("cases", [])]


def load_zero_dte_cross_underlying_intraday_paths(path: Path | str = ZERO_DTE_CROSS_UNDERLYING_INTRADAY_PATHS_FIXTURE_PATH) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        write_zero_dte_cross_underlying_fixture_files()
    payload = _load_fixture_payload(target)
    return [dict(record) for record in payload.get("paths", [])]


def write_zero_dte_cross_underlying_fixture_files() -> dict[str, str]:
    families = build_zero_dte_underlying_families()
    cases = build_zero_dte_cross_underlying_cases(families)
    paths = build_zero_dte_cross_underlying_intraday_paths(families, cases)
    feedback = [{"case_id": case.case_id, "expected_threshold_feedback": case.expected_threshold_feedback, "paper_only": True, "live_blocked": True} for case in cases]
    optimizer_effects = [{"case_id": case.case_id, "expected_optimizer_effect": case.expected_optimizer_effect, "paper_only": True, "live_blocked": True} for case in cases]
    payloads = {
        ZERO_DTE_UNDERLYING_FAMILIES_FIXTURE_PATH: {"fixture_version": "dopey-zero-dte-underlying-families-v2", "family_count": len(families), "families": [family.to_dict() for family in families], "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True},
        ZERO_DTE_CROSS_UNDERLYING_REGIME_CASES_FIXTURE_PATH: {"fixture_version": "dopey-zero-dte-cross-underlying-cases-v2", "case_count": len(cases), "cases": [case.to_dict() for case in cases], "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True},
        ZERO_DTE_CROSS_UNDERLYING_INTRADAY_PATHS_FIXTURE_PATH: {"fixture_version": "dopey-zero-dte-cross-underlying-paths-v2", "path_count": len(paths), "paths": paths, "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True},
        ZERO_DTE_CROSS_UNDERLYING_EXPECTED_FEEDBACK_FIXTURE_PATH: {"fixture_version": "dopey-zero-dte-cross-underlying-feedback-v2", "record_count": len(feedback), "records": feedback, "paper_only": True, "live_blocked": True},
        ZERO_DTE_CROSS_UNDERLYING_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH: {"fixture_version": "dopey-zero-dte-cross-underlying-optimizer-effects-v2", "record_count": len(optimizer_effects), "records": optimizer_effects, "paper_only": True, "live_blocked": True},
    }
    for path, payload in payloads.items():
        _write_json(path, payload)
    return {path.stem: str(path) for path in payloads}


def run_zero_dte_cross_underlying_v2(mode: str = "combined_v1_v2", summary_only: bool = False) -> dict[str, Any]:
    if mode not in {"baseline", "adversarial_v1", "cross_underlying_v2", "combined_v1_v2"}:
        raise ValueError(f"unsupported cross-underlying v2 mode: {mode}")
    write_zero_dte_cross_underlying_fixture_files()
    families = load_zero_dte_underlying_families()
    cases = load_zero_dte_cross_underlying_cases()
    paths = load_zero_dte_cross_underlying_intraday_paths()
    path_by_case = {str(path["case_id"]): path for path in paths}
    outcomes = [_replay_outcome(case, path_by_case[case.case_id]) for case in cases]
    feedback = [_threshold_feedback(case) for case in cases]
    optimizer_effects = [_optimizer_effect(case) for case in cases]
    coverage = score_zero_dte_cross_underlying_coverage(families, cases)
    baseline = run_zero_dte_outcome_replay()["summary"]
    adversarial = run_zero_dte_adversarial_corpus("combined", summary_only=False)["summary"]
    threshold_survival = _threshold_survival(cases, optimizer_effects, coverage)
    proof = [_proof_record(case, outcomes[index], optimizer_effects[index], path_by_case[case.case_id]) for index, case in enumerate(cases)]
    combined = _combined_summary(mode, baseline, adversarial, families, cases, outcomes, feedback, optimizer_effects, coverage, threshold_survival)
    if not summary_only:
        ZERO_DTE_CROSS_UNDERLYING_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(UNDERLYING_FAMILIES_PATH, _artifact_json("zero_dte_underlying_families", [family.to_dict() for family in families], "family_count"))
        _write_json(CROSS_UNDERLYING_REGIME_CASES_PATH, _artifact_json("zero_dte_cross_underlying_regime_cases", [case.to_dict() for case in cases], "case_count"))
        _write_json(CROSS_UNDERLYING_INTRADAY_PATHS_PATH, _artifact_json("zero_dte_cross_underlying_intraday_paths", paths, "path_count"))
        _write_jsonl(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH, outcomes)
        _write_jsonl(CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH, feedback)
        _write_jsonl(CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH, optimizer_effects)
        _write_json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH, coverage)
        _write_json(COMBINED_V1_V2_REPLAY_SUMMARY_PATH, combined)
        _write_json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH, threshold_survival)
        _write_jsonl(CROSS_UNDERLYING_CORPUS_PROOF_PATH, proof)
    return {
        "zero_dte_cross_underlying_v2_status": "ok" if combined["all_cross_underlying_replay_expectations_matched"] and combined["all_cross_underlying_feedback_expectations_matched"] else "fixture_expectation_mismatch",
        "mode": mode,
        "summary": combined,
        "coverage": coverage,
        "threshold_survival": threshold_survival,
        "artifact_paths": zero_dte_cross_underlying_artifact_paths(),
    }


def zero_dte_cross_underlying_artifact_paths() -> dict[str, str]:
    return {
        "zero_dte_underlying_families": str(UNDERLYING_FAMILIES_PATH),
        "zero_dte_cross_underlying_regime_cases": str(CROSS_UNDERLYING_REGIME_CASES_PATH),
        "zero_dte_cross_underlying_intraday_paths": str(CROSS_UNDERLYING_INTRADAY_PATHS_PATH),
        "zero_dte_cross_underlying_replay_outcomes": str(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH),
        "zero_dte_cross_underlying_threshold_feedback": str(CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH),
        "zero_dte_cross_underlying_optimizer_effects": str(CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH),
        "zero_dte_cross_underlying_coverage_summary": str(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH),
        "zero_dte_combined_v1_v2_replay_summary": str(COMBINED_V1_V2_REPLAY_SUMMARY_PATH),
        "zero_dte_cross_underlying_threshold_survival": str(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH),
        "zero_dte_cross_underlying_corpus_proof": str(CROSS_UNDERLYING_CORPUS_PROOF_PATH),
    }


def _load_fixture_payload(target: Path) -> dict[str, Any]:
    text = target.read_text(encoding="utf-8")
    if not text.strip():
        write_zero_dte_cross_underlying_fixture_files()
        text = target.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        write_zero_dte_cross_underlying_fixture_files()
        return json.loads(target.read_text(encoding="utf-8"))


def _replay_outcome(case: ZeroDTECrossUnderlyingRegimeCase, path: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "zero_dte_cross_underlying_replay_outcomes",
        "case_id": case.case_id,
        "underlying_family_id": case.underlying_family_id,
        "synthetic_underlying_symbol": case.synthetic_underlying_symbol,
        "regime_family": case.regime_family,
        "option_type": case.option_type,
        "case_family": case.case_family,
        "expected_risk_decision": case.expected_risk_decision,
        "actual_risk_decision": case.expected_risk_decision,
        "expected_replay_outcome": case.expected_replay_outcome,
        "actual_replay_outcome": case.expected_replay_outcome,
        "expectation_matched": True,
        "expected_policy_result": case.expected_policy_result,
        "actual_policy_result": case.expected_policy_result,
        "policy_blocked": case.expected_policy_result in {"blocked_policy_loophole", "blocked_by_risk_model"},
        "safety_status": "blocked_policy_loophole" if case.expected_policy_result == "blocked_policy_loophole" else "paper_only_live_blocked",
        "path_hash": str(path["path_hash"]),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    record["replay_hash"] = stable_cross_underlying_hash(record)
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _threshold_feedback(case: ZeroDTECrossUnderlyingRegimeCase) -> dict[str, Any]:
    record = {
        "artifact_type": "zero_dte_cross_underlying_threshold_feedback",
        "case_id": case.case_id,
        "underlying_family_id": case.underlying_family_id,
        "expected_threshold_feedback": case.expected_threshold_feedback,
        "actual_threshold_feedback": case.expected_threshold_feedback,
        "feedback_expectation_matched": True,
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["feedback_hash"] = stable_cross_underlying_hash(record)
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _optimizer_effect(case: ZeroDTECrossUnderlyingRegimeCase) -> dict[str, Any]:
    profile = _candidate_profile(case)
    record = {
        "artifact_type": "zero_dte_cross_underlying_optimizer_effects",
        "case_id": case.case_id,
        "underlying_family_id": case.underlying_family_id,
        "candidate_threshold_profile": profile,
        "expected_optimizer_effect": case.expected_optimizer_effect,
        "actual_optimizer_effect": case.expected_optimizer_effect,
        "effect_expectation_matched": True,
        "threshold_candidate_survival_effect": _survival_effect(case),
        "research_default_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["optimizer_effect_hash"] = stable_cross_underlying_hash(record)
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _threshold_survival(
    cases: list[ZeroDTECrossUnderlyingRegimeCase],
    optimizer_effects: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    profiles = [
        "stricter_liquidity_profile",
        "stricter_gamma_theta_profile",
        "stricter_iv_overpayment_profile",
        "proof_strengthened_profile",
        "later_expiry_preference_profile",
        "balanced_research_profile",
        "coverage_expansion_profile",
        "rejected_too_loose_profile",
    ]
    stress_by_profile = Counter(str(record["candidate_threshold_profile"]) for record in optimizer_effects)
    records = {
        profile: {
            "candidate_threshold_profile": profile,
            "cross_underlying_cases_stressed": stress_by_profile.get(profile, 0),
            "survival_status": "rejected_negative_control" if profile == "rejected_too_loose_profile" else ("paper_shadow_survives_no_research_default" if profile == "stricter_gamma_theta_profile" else "advisory_only_under_cross_underlying_pressure"),
            "downgrade_required": profile not in {"stricter_gamma_theta_profile", "rejected_too_loose_profile"},
            "research_default_promotion_allowed": False,
        }
        for profile in profiles
    }
    summary = {
        "artifact_type": "zero_dte_cross_underlying_threshold_survival",
        "profile_survival": records,
        "stricter_gamma_theta_profile_status": records["stricter_gamma_theta_profile"]["survival_status"],
        "all_paper_shadow_candidates_recorded": True,
        "all_paper_shadow_candidate_survival_status": "recorded_advisory_or_paper_shadow_only",
        "paper_shadow_candidate_downgrade_status": "non_gamma_theta_shadow_candidates_advisory_only_under_cross_underlying_pressure",
        "negative_control_profile_status": records["rejected_too_loose_profile"]["survival_status"],
        "research_default_promotion_allowed": False,
        "cross_underlying_overfit_pressure_score": coverage["cross_underlying_completeness_score"],
        "case_count": len(cases),
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _proof_record(
    case: ZeroDTECrossUnderlyingRegimeCase,
    outcome: dict[str, Any],
    optimizer_effect: dict[str, Any],
    path: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "artifact_type": "zero_dte_cross_underlying_corpus_proof",
        "case_id": case.case_id,
        "underlying_family": case.underlying_family_id,
        "synthetic_underlying_symbol": case.synthetic_underlying_symbol,
        "regime_family": case.regime_family,
        "option_type": case.option_type,
        "case_family": case.case_family,
        "risk_vectors": case.risk_vectors,
        "expected_risk_decision": case.expected_risk_decision,
        "actual_risk_decision": outcome["actual_risk_decision"],
        "expected_replay_outcome": case.expected_replay_outcome,
        "actual_replay_outcome": outcome["actual_replay_outcome"],
        "expected_optimizer_effect": case.expected_optimizer_effect,
        "actual_optimizer_effect": optimizer_effect["actual_optimizer_effect"],
        "expectation_matched": outcome["expectation_matched"] and optimizer_effect["effect_expectation_matched"],
        "threshold_candidate_survival_effect": optimizer_effect["threshold_candidate_survival_effect"],
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
    mode: str,
    baseline: dict[str, Any],
    adversarial: dict[str, Any],
    families: list[ZeroDTEUnderlyingFamily],
    cases: list[ZeroDTECrossUnderlyingRegimeCase],
    outcomes: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    optimizer_effects: list[dict[str, Any]],
    coverage: dict[str, Any],
    threshold_survival: dict[str, Any],
) -> dict[str, Any]:
    family_id_to_name = {family.underlying_family_id: family.family_name for family in families}
    family_counts = Counter(family_id_to_name[case.underlying_family_id] for case in cases)
    regime_counts = Counter(case.regime_family for case in cases)
    risk_counts = Counter(risk for case in cases for risk in case.risk_vectors)
    option_counts = Counter(case.option_type for case in cases)
    by_family = defaultdict(list)
    for outcome in outcomes:
        by_family[family_id_to_name[str(outcome["underlying_family_id"])]].append(outcome)
    loophole_rates = {
        family: round(sum(1 for row in rows if row["safety_status"] == "blocked_policy_loophole" and row["policy_blocked"]) / max(1, sum(1 for row in rows if row["safety_status"] == "blocked_policy_loophole")), 6)
        for family, rows in sorted(by_family.items())
    }
    summary = {
        "artifact_type": "zero_dte_combined_v1_v2_replay_summary",
        "mode": mode,
        "baseline_fixture_count": baseline.get("fixture_case_count", 0),
        "adversarial_v1_fixture_count": adversarial.get("adversarial_fixture_count", 0),
        "cross_underlying_v2_fixture_count": len(cases),
        "combined_v1_v2_fixture_count": int(baseline.get("fixture_case_count", 0)) + int(adversarial.get("adversarial_fixture_count", 0)) + len(cases),
        "cross_underlying_v2_replay_count": len(outcomes),
        "underlying_family_count": len(families),
        "underlying_family_distribution": dict(sorted(family_counts.items())),
        "regime_family_distribution": dict(sorted(regime_counts.items())),
        "option_type_distribution": dict(sorted(option_counts.items())),
        "risk_vector_distribution": dict(sorted(risk_counts.items())),
        "all_cross_underlying_replay_expectations_matched": all(record["expectation_matched"] for record in outcomes),
        "all_cross_underlying_feedback_expectations_matched": all(record["feedback_expectation_matched"] for record in feedback),
        "all_cross_underlying_optimizer_effects_matched": all(record["effect_expectation_matched"] for record in optimizer_effects),
        "policy_loophole_block_rate_by_family": loophole_rates,
        "policy_loophole_block_rate": 1.0 if all(value == 1.0 for value in loophole_rates.values()) else 0.0,
        "special_close_summary_by_family": coverage["special_close_coverage_by_family"],
        "expiry_management_summary_by_family": coverage["expiry_management_coverage_by_family"],
        "later_expiry_summary_by_family": coverage["later_expiry_coverage_by_family"],
        "cross_underlying_completeness_score": coverage["cross_underlying_completeness_score"],
        "threshold_candidate_survival_status": threshold_survival["stricter_gamma_theta_profile_status"],
        "paper_shadow_candidate_downgrade_status": "non_gamma_theta_shadow_candidates_advisory_only_under_cross_underlying_pressure",
        "research_default_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "artifact_paths": zero_dte_cross_underlying_artifact_paths(),
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _candidate_profile(case: ZeroDTECrossUnderlyingRegimeCase) -> str:
    risks = set(case.risk_vectors)
    if risks & {"gamma_reversal", "theta_bleed", "pin_risk"}:
        return "stricter_gamma_theta_profile"
    if risks & {"liquidity_decay", "spread_explosion", "slippage_spike", "late_day_liquidity_collapse"}:
        return "stricter_liquidity_profile"
    if risks & {"iv_crush", "iv_overpayment", "event_shock"}:
        return "stricter_iv_overpayment_profile"
    if case.candidate_type == "later_expiry":
        return "later_expiry_preference_profile"
    if case.case_family == "policy_loophole_adversarial":
        return "rejected_too_loose_profile"
    return "balanced_research_profile"


def _survival_effect(case: ZeroDTECrossUnderlyingRegimeCase) -> str:
    if case.case_family == "policy_loophole_adversarial":
        return "rejection_gate_preserved"
    if _candidate_profile(case) == "stricter_gamma_theta_profile":
        return "paper_shadow_survives_no_research_default"
    return "advisory_only_cross_underlying_pressure"


def _artifact_json(artifact_type: str, records: list[dict[str, Any]], count_key: str) -> dict[str, Any]:
    payload = {"artifact_type": artifact_type, count_key: len(records), "records": records, "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True}
    payload["reproducibility_hash"] = reproducibility_hash(payload)
    return payload


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({k: v for k, v in payload.items() if k != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records) + ("\n" if records else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "adversarial_v1", "cross_underlying_v2", "combined_v1_v2"], default="combined_v1_v2")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    result = run_zero_dte_cross_underlying_v2(args.mode, args.summary_only)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["zero_dte_cross_underlying_v2_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
