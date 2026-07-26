"""Offline 0DTE threshold feedback optimizer orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .run_zero_dte_outcome_replay import run_zero_dte_outcome_replay
from .run_zero_dte_adversarial_corpus import run_zero_dte_adversarial_corpus
from .run_hybrid_swing_0dte_v3 import run_hybrid_swing_0dte_v3
from .run_zero_dte_cross_underlying_v2 import run_zero_dte_cross_underlying_v2
from .run_zero_dte_risk_model import run_zero_dte_risk_model
from .zero_dte_feedback_aggregator import (
    build_zero_dte_threshold_feedback_aggregate,
    source_replay_summary_expectations_match,
)
from .zero_dte_optimizer_decision_policy import (
    decide_zero_dte_threshold_candidates,
    optimizer_decision_summary,
    recommended_threshold_profile,
)
from .zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds
from .zero_dte_shadow_replay import (
    run_zero_dte_shadow_replay_for_candidates,
    shadow_replay_summary,
)
from .zero_dte_threshold_candidate import candidate_threshold_record
from .zero_dte_threshold_candidate_generator import generate_zero_dte_threshold_candidates
from .zero_dte_threshold_optimizer_models import (
    ZERO_DTE_THRESHOLD_OPTIMIZER_VERSION,
    ZeroDTEThresholdCandidate,
    ZeroDTEShadowReplayResult,
    ZeroDTEThresholdFeedbackAggregate,
    ZeroDTEThresholdOptimizationDecision,
    stable_zero_dte_optimizer_hash,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
PAPER_ALLOCATION_PLAN_PATH = REPO_ROOT / "artifacts" / "dopey" / "allocation" / "paper_allocation_plan.json"
ALLOCATION_EXPOSURE_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "allocation" / "allocation_exposure_summary.json"
PORTFOLIO_THRESHOLD_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "portfolio_replay" / "portfolio_threshold_feedback.jsonl"
CRISIS_THRESHOLD_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "portfolio_stress_ladder" / "crisis_threshold_feedback.jsonl"
INCIDENT_THRESHOLD_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "incident_response" / "incident_threshold_feedback.jsonl"


def build_zero_dte_threshold_optimizer_bundle() -> dict[str, Any]:
    run_zero_dte_risk_model()
    run_zero_dte_outcome_replay()
    adversarial = run_zero_dte_adversarial_corpus()
    cross_underlying = run_zero_dte_cross_underlying_v2()
    hybrid = run_hybrid_swing_0dte_v3()
    base_thresholds = load_default_zero_dte_risk_thresholds()
    aggregate = build_zero_dte_threshold_feedback_aggregate()
    candidates = generate_zero_dte_threshold_candidates(aggregate, base_thresholds)
    optimizer_run_id = _optimizer_run_id(aggregate, candidates)
    shadow_results, safety_reason_codes_by_candidate = run_zero_dte_shadow_replay_for_candidates(
        candidates,
        base_thresholds,
        aggregate.validated_blocks,
    )
    decisions = decide_zero_dte_threshold_candidates(
        optimizer_run_id,
        aggregate,
        candidates,
        shadow_results,
        safety_reason_codes_by_candidate,
        source_replay_summary_expectations_match(),
    )
    recommended = recommended_threshold_profile(aggregate, candidates, decisions)
    if recommended["selected_candidate_threshold_id"] in {candidate.candidate_threshold_id for candidate in candidates}:
        candidate_by_id = {candidate.candidate_threshold_id: candidate for candidate in candidates}
        selected_candidate = candidate_by_id[str(recommended["selected_candidate_threshold_id"])]
        recommended["threshold_profile"] = candidate_threshold_record(base_thresholds, selected_candidate)
    rejected = rejected_threshold_profiles(candidates, decisions)
    allocation_feedback = _allocation_feedback_summary()
    portfolio_feedback = _portfolio_feedback_summary()
    crisis_feedback = _crisis_feedback_summary()
    incident_feedback = _incident_feedback_summary()
    proof = threshold_optimizer_proof_records(
        optimizer_run_id,
        aggregate,
        base_thresholds.threshold_version,
        candidates,
        shadow_results,
        decisions,
    )
    summary = threshold_optimizer_summary(
        optimizer_run_id,
        aggregate,
        candidates,
        shadow_results,
        decisions,
        recommended,
        rejected,
        adversarial["summary"],
        cross_underlying["summary"],
        cross_underlying["threshold_survival"],
        hybrid["summary"],
        hybrid["threshold_survival"],
        allocation_feedback,
        portfolio_feedback,
        crisis_feedback,
        incident_feedback,
    )
    return {
        "optimizer_run_id": optimizer_run_id,
        "base_thresholds": base_thresholds,
        "aggregate": aggregate,
        "candidates": candidates,
        "shadow_results": shadow_results,
        "decisions": decisions,
        "recommended_threshold_profile": recommended,
        "rejected_threshold_profiles": rejected,
        "proof_records": proof,
        "summary": summary,
        "allocation_feedback_summary": allocation_feedback,
        "portfolio_feedback_summary": portfolio_feedback,
        "crisis_feedback_summary": crisis_feedback,
        "incident_feedback_summary": incident_feedback,
        "adversarial_summary": adversarial["summary"],
        "cross_underlying_v2_summary": cross_underlying["summary"],
        "cross_underlying_v2_threshold_survival": cross_underlying["threshold_survival"],
        "hybrid_swing_0dte_v3_summary": hybrid["summary"],
        "hybrid_swing_0dte_v3_threshold_survival": hybrid["threshold_survival"],
    }


def threshold_optimizer_summary(
    optimizer_run_id: str,
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    candidates: list[ZeroDTEThresholdCandidate],
    shadow_results: list[ZeroDTEShadowReplayResult],
    decisions: list[ZeroDTEThresholdOptimizationDecision],
    recommended: dict[str, Any],
    rejected: list[dict[str, Any]],
    adversarial_summary: dict[str, Any] | None = None,
    cross_underlying_v2_summary: dict[str, Any] | None = None,
    cross_underlying_v2_threshold_survival: dict[str, Any] | None = None,
    hybrid_swing_0dte_v3_summary: dict[str, Any] | None = None,
    hybrid_swing_0dte_v3_threshold_survival: dict[str, Any] | None = None,
    allocation_feedback_summary: dict[str, Any] | None = None,
    portfolio_feedback_summary: dict[str, Any] | None = None,
    crisis_feedback_summary: dict[str, Any] | None = None,
    incident_feedback_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision_summary = optimizer_decision_summary(decisions)
    shadow_summary = shadow_replay_summary(shadow_results)
    allocation_feedback = allocation_feedback_summary or _empty_allocation_feedback()
    portfolio_feedback = portfolio_feedback_summary or _empty_portfolio_feedback()
    crisis_feedback = crisis_feedback_summary or _empty_crisis_feedback()
    incident_feedback = incident_feedback_summary or _empty_incident_feedback()
    summary = {
        "artifact_type": "zero_dte_threshold_optimizer_summary",
        "zero_dte_threshold_optimizer_version": ZERO_DTE_THRESHOLD_OPTIMIZER_VERSION,
        "optimizer_run_id": optimizer_run_id,
        "source_replay_summary_hash": aggregate.source_replay_summary_hash,
        "feedback_records_loaded": aggregate.feedback_records_loaded,
        "outcomes_loaded": aggregate.outcomes_loaded,
        "candidate_count": len(candidates),
        "candidate_threshold_ids": [candidate.candidate_threshold_id for candidate in candidates],
        "rejected_count": len(rejected),
        "paper_shadow_candidate_count": decision_summary["paper_shadow_candidate_count"],
        "research_default_candidate_count": decision_summary["research_default_candidate_count"],
        "recommended_threshold_profile": recommended.get("selected_candidate_threshold_id", ""),
        "unsafe_approval_count": shadow_summary["unsafe_approval_count"],
        "overfit_warning_count": shadow_summary["overfit_warning_count"],
        "fixture_coverage_gap_count": sum(len(candidate.requires_more_fixture_coverage) for candidate in candidates),
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "decision_summary": decision_summary,
        "shadow_replay_summary": shadow_summary,
        "adversarial_corpus_summary": adversarial_summary or {},
        "adversarial_fixture_count": (adversarial_summary or {}).get("adversarial_fixture_count", 0),
        "combined_fixture_count": (adversarial_summary or {}).get("combined_fixture_count", 0),
        "post_adversarial_threshold_candidate_survival_status": (adversarial_summary or {}).get("stricter_gamma_theta_profile_status", "not_evaluated"),
        "post_adversarial_research_default_promotion_allowed": bool((adversarial_summary or {}).get("research_default_promotion_allowed", False)),
        "post_adversarial_recommendation": "paper_shadow_only_no_research_default_promotion",
        "cross_underlying_v2_summary": cross_underlying_v2_summary or {},
        "cross_underlying_v2_fixture_count": (cross_underlying_v2_summary or {}).get("cross_underlying_v2_fixture_count", 0),
        "combined_v1_v2_fixture_count": (cross_underlying_v2_summary or {}).get("combined_v1_v2_fixture_count", 0),
        "post_v2_threshold_candidate_survival_status": (cross_underlying_v2_threshold_survival or {}).get("stricter_gamma_theta_profile_status", "not_evaluated"),
        "post_v2_all_paper_shadow_candidate_survival_status": (cross_underlying_v2_threshold_survival or {}).get("all_paper_shadow_candidate_survival_status", "not_evaluated"),
        "post_v2_paper_shadow_candidate_downgrade_status": (cross_underlying_v2_threshold_survival or {}).get("paper_shadow_candidate_downgrade_status", "not_evaluated"),
        "post_v2_negative_control_profile_status": (cross_underlying_v2_threshold_survival or {}).get("negative_control_profile_status", "not_evaluated"),
        "post_v2_research_default_promotion_allowed": bool((cross_underlying_v2_threshold_survival or {}).get("research_default_promotion_allowed", False)),
        "post_v2_recommendation": "paper_shadow_only_cross_underlying_v2_no_research_default_promotion",
        "hybrid_v3_summary": hybrid_swing_0dte_v3_summary or {},
        "hybrid_v3_pair_count": (hybrid_swing_0dte_v3_summary or {}).get("hybrid_pair_count", 0),
        "hybrid_zero_dte_vs_swing_preference_distribution": (hybrid_swing_0dte_v3_summary or {}).get("preference_distribution", {}),
        "post_hybrid_threshold_candidate_survival_status": (hybrid_swing_0dte_v3_threshold_survival or {}).get("hybrid_stricter_gamma_theta_profile_status", "not_evaluated"),
        "post_hybrid_later_expiry_preference_status": (hybrid_swing_0dte_v3_threshold_survival or {}).get("later_expiry_preference_status", "not_evaluated"),
        "post_hybrid_paper_shadow_candidate_downgrade_status": (hybrid_swing_0dte_v3_threshold_survival or {}).get("paper_shadow_candidate_downgrade_status", "not_evaluated"),
        "post_hybrid_research_default_promotion_allowed": bool((hybrid_swing_0dte_v3_threshold_survival or {}).get("research_default_promotion_allowed", False)),
        "post_hybrid_recommendation": "paper_shadow_only_hybrid_v3_no_research_default_promotion",
        "allocation_feedback_summary": allocation_feedback,
        "allocation_feedback_loaded": bool(allocation_feedback.get("allocation_feedback_loaded", False)),
        "allocation_feedback_0dte_cap_status": allocation_feedback.get("zero_dte_cap_status", "not_loaded"),
        "allocation_feedback_swing_preferred_units": allocation_feedback.get("swing_paper_premium_risk_units", 0.0),
        "allocation_feedback_zero_dte_units": allocation_feedback.get("zero_dte_paper_premium_risk_units", 0.0),
        "allocation_feedback_threshold_action": allocation_feedback.get("threshold_action", "keep_0dte_caps_strict_paper_shadow_only"),
        "allocation_feedback_live_threshold_mutation_allowed": False,
        "portfolio_feedback_summary": portfolio_feedback,
        "portfolio_feedback_loaded": bool(portfolio_feedback.get("portfolio_feedback_loaded", False)),
        "portfolio_feedback_records_loaded": portfolio_feedback.get("feedback_records_loaded", 0),
        "portfolio_feedback_threshold_action_distribution": portfolio_feedback.get("feedback_action_distribution", {}),
        "portfolio_feedback_live_threshold_mutation_allowed": False,
        "crisis_feedback_summary": crisis_feedback,
        "crisis_feedback_loaded": bool(crisis_feedback.get("crisis_feedback_loaded", False)),
        "crisis_feedback_records_loaded": crisis_feedback.get("feedback_records_loaded", 0),
        "crisis_feedback_threshold_action_distribution": crisis_feedback.get("feedback_action_distribution", {}),
        "crisis_feedback_live_threshold_mutation_allowed": False,
        "incident_feedback_summary": incident_feedback,
        "incident_feedback_loaded": bool(incident_feedback.get("incident_feedback_loaded", False)),
        "incident_feedback_records_loaded": incident_feedback.get("feedback_records_loaded", 0),
        "incident_feedback_threshold_action_distribution": incident_feedback.get("feedback_action_distribution", {}),
        "incident_feedback_live_threshold_mutation_allowed": False,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _allocation_feedback_summary() -> dict[str, Any]:
    if not PAPER_ALLOCATION_PLAN_PATH.exists():
        return _empty_allocation_feedback()
    plan = json.loads(PAPER_ALLOCATION_PLAN_PATH.read_text(encoding="utf-8"))
    exposure = {}
    if ALLOCATION_EXPOSURE_SUMMARY_PATH.exists():
        exposure = json.loads(ALLOCATION_EXPOSURE_SUMMARY_PATH.read_text(encoding="utf-8"))
    return {
        "artifact_type": "zero_dte_threshold_optimizer_allocation_feedback",
        "allocation_feedback_loaded": True,
        "plan_id": str(plan.get("plan_id", "")),
        "opportunity_count": int(plan.get("opportunity_count", 0)),
        "allocated_count": int(plan.get("allocated_count", 0)),
        "throttled_count": int(plan.get("throttled_count", 0)),
        "shadow_only_count": int(plan.get("shadow_only_count", 0)),
        "delayed_rotation_count": int(plan.get("delayed_rotation_count", 0)),
        "zero_dte_paper_premium_risk_units": float(exposure.get("zero_dte_paper_premium_risk_units", 0.0)),
        "swing_paper_premium_risk_units": float(exposure.get("swing_paper_premium_risk_units", 0.0)),
        "zero_dte_exposure_share": float(exposure.get("zero_dte_exposure_share", 0.0)),
        "zero_dte_cap_status": str(exposure.get("zero_dte_share_status", exposure.get("zero_dte_cap_status", "not_loaded"))),
        "paper_shadow_profile_remains_shadow_only": int(plan.get("shadow_only_count", 0)) > 0,
        "hybrid_evidence_prefers_swing_over_0dte": float(exposure.get("swing_paper_premium_risk_units", 0.0)) >= float(exposure.get("zero_dte_paper_premium_risk_units", 0.0)),
        "threshold_action": "keep_0dte_caps_strict_paper_shadow_only",
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _empty_allocation_feedback() -> dict[str, Any]:
    return {
        "artifact_type": "zero_dte_threshold_optimizer_allocation_feedback",
        "allocation_feedback_loaded": False,
        "plan_id": "",
        "opportunity_count": 0,
        "allocated_count": 0,
        "throttled_count": 0,
        "shadow_only_count": 0,
        "delayed_rotation_count": 0,
        "zero_dte_paper_premium_risk_units": 0.0,
        "swing_paper_premium_risk_units": 0.0,
        "zero_dte_exposure_share": 0.0,
        "zero_dte_cap_status": "not_loaded",
        "paper_shadow_profile_remains_shadow_only": False,
        "hybrid_evidence_prefers_swing_over_0dte": False,
        "threshold_action": "keep_0dte_caps_strict_paper_shadow_only",
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _portfolio_feedback_summary() -> dict[str, Any]:
    if not PORTFOLIO_THRESHOLD_FEEDBACK_PATH.exists():
        return _empty_portfolio_feedback()
    records = [
        json.loads(line)
        for line in PORTFOLIO_THRESHOLD_FEEDBACK_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    action_distribution: dict[str, int] = {}
    same_day_pressure = 0
    for record in records:
        action = str(record.get("feedback_action", record.get("feedback_type", "")))
        action_distribution[action] = action_distribution.get(action, 0) + 1
        if record.get("same_day_churn_pressure") is True:
            same_day_pressure += 1
    return {
        "artifact_type": "zero_dte_threshold_optimizer_portfolio_feedback",
        "portfolio_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "same_day_churn_pressure_count": same_day_pressure,
        "threshold_action": "preserve_paper_shadow_or_advisory_strengthening_only",
        "live_threshold_mutation_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _empty_portfolio_feedback() -> dict[str, Any]:
    return {
        "artifact_type": "zero_dte_threshold_optimizer_portfolio_feedback",
        "portfolio_feedback_loaded": False,
        "feedback_records_loaded": 0,
        "feedback_action_distribution": {},
        "same_day_churn_pressure_count": 0,
        "threshold_action": "preserve_paper_shadow_or_advisory_strengthening_only",
        "live_threshold_mutation_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _crisis_feedback_summary() -> dict[str, Any]:
    if not CRISIS_THRESHOLD_FEEDBACK_PATH.exists():
        return _empty_crisis_feedback()
    records = [
        json.loads(line)
        for line in CRISIS_THRESHOLD_FEEDBACK_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    action_distribution: dict[str, int] = {}
    for record in records:
        actions = record.get("feedback_actions", [])
        if not isinstance(actions, list):
            actions = [record.get("primary_feedback_action", "")]
        for action_value in actions:
            action = str(action_value)
            action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "zero_dte_threshold_optimizer_crisis_feedback",
        "crisis_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "threshold_action": "downgrade_crisis_increasing_profiles_preserve_advisory_only",
        "live_threshold_mutation_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _empty_crisis_feedback() -> dict[str, Any]:
    return {
        "artifact_type": "zero_dte_threshold_optimizer_crisis_feedback",
        "crisis_feedback_loaded": False,
        "feedback_records_loaded": 0,
        "feedback_action_distribution": {},
        "threshold_action": "downgrade_crisis_increasing_profiles_preserve_advisory_only",
        "live_threshold_mutation_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _incident_feedback_summary() -> dict[str, Any]:
    if not INCIDENT_THRESHOLD_FEEDBACK_PATH.exists():
        return _empty_incident_feedback()
    records = [
        json.loads(line)
        for line in INCIDENT_THRESHOLD_FEEDBACK_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    action_distribution: dict[str, int] = {}
    for record in records:
        actions = record.get("threshold_actions", [])
        if not isinstance(actions, list):
            actions = []
        for action_value in actions:
            action = str(action_value)
            action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "zero_dte_threshold_optimizer_incident_feedback",
        "incident_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "threshold_action": "preserve_incident_blocks_as_paper_advisory_gates",
        "live_threshold_mutation_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _empty_incident_feedback() -> dict[str, Any]:
    return {
        "artifact_type": "zero_dte_threshold_optimizer_incident_feedback",
        "incident_feedback_loaded": False,
        "feedback_records_loaded": 0,
        "feedback_action_distribution": {},
        "threshold_action": "preserve_incident_blocks_as_paper_advisory_gates",
        "live_threshold_mutation_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
    }


def rejected_threshold_profiles(
    candidates: list[ZeroDTEThresholdCandidate],
    decisions: list[ZeroDTEThresholdOptimizationDecision],
) -> list[dict[str, Any]]:
    candidate_by_id = {candidate.candidate_threshold_id: candidate for candidate in candidates}
    return [
        {
            "artifact_type": "zero_dte_rejected_threshold_profile",
            "candidate_threshold_id": decision.candidate_threshold_id,
            "candidate_hash": candidate_by_id[decision.candidate_threshold_id].candidate_hash,
            "decision": decision.decision,
            "decision_reason_codes": decision.decision_reason_codes,
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
        }
        for decision in decisions
        if decision.decision == "reject_candidate"
    ]


def threshold_optimizer_proof_records(
    optimizer_run_id: str,
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    source_threshold_version: str,
    candidates: list[ZeroDTEThresholdCandidate],
    shadow_results: list[ZeroDTEShadowReplayResult],
    decisions: list[ZeroDTEThresholdOptimizationDecision],
) -> list[dict[str, Any]]:
    candidate_by_id = {candidate.candidate_threshold_id: candidate for candidate in candidates}
    shadow_by_id = {result.candidate_threshold_id: result for result in shadow_results}
    proof_records: list[dict[str, Any]] = []
    for decision in decisions:
        candidate = candidate_by_id[decision.candidate_threshold_id]
        shadow = shadow_by_id[decision.candidate_threshold_id]
        record = {
            "artifact_type": "zero_dte_threshold_optimizer_proof",
            "optimizer_run_id": optimizer_run_id,
            "source_replay_summary_hash": aggregate.source_replay_summary_hash,
            "source_threshold_version": source_threshold_version,
            "candidate_threshold_id": candidate.candidate_threshold_id,
            "candidate_hash": candidate.candidate_hash,
            "shadow_replay_hash": shadow.shadow_replay_hash,
            "decision": decision.decision,
            "reason_codes": decision.decision_reason_codes,
            "safety_status": decision.safety_status,
            "overfit_status": decision.overfit_status,
            "promotion_gate": candidate.promotion_gate,
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
        }
        record["reproducibility_hash"] = reproducibility_hash(record)
        proof_records.append(record)
    return proof_records


def _optimizer_run_id(
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    candidates: list[ZeroDTEThresholdCandidate],
) -> str:
    seed = {
        "version": ZERO_DTE_THRESHOLD_OPTIMIZER_VERSION,
        "aggregate_hash": aggregate.aggregate_hash,
        "candidate_hashes": [candidate.candidate_hash for candidate in candidates],
    }
    return f"zero-dte-threshold-optimizer-run-{stable_zero_dte_optimizer_hash(seed)[:12]}"
