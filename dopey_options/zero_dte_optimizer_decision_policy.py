"""Promotion-gated optimizer decisions for offline 0DTE threshold candidates."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .zero_dte_threshold_optimizer_models import (
    ZeroDTEShadowReplayResult,
    ZeroDTEThresholdCandidate,
    ZeroDTEThresholdFeedbackAggregate,
    ZeroDTEThresholdOptimizationDecision,
    zero_dte_optimization_decision_hash,
)


def decide_zero_dte_threshold_candidate(
    optimizer_run_id: str,
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    candidate: ZeroDTEThresholdCandidate,
    shadow_result: ZeroDTEShadowReplayResult,
    safety_reason_codes: list[str],
    source_replay_expectations_match: bool,
) -> ZeroDTEThresholdOptimizationDecision:
    reason_codes = _decision_reason_codes(aggregate, candidate, shadow_result, safety_reason_codes, source_replay_expectations_match)
    decision = _decision(candidate, shadow_result, reason_codes, source_replay_expectations_match)
    draft = ZeroDTEThresholdOptimizationDecision(
        optimizer_run_id=optimizer_run_id,
        candidate_threshold_id=candidate.candidate_threshold_id,
        decision=decision,
        decision_reason_codes=reason_codes,
        safety_status="pass" if shadow_result.safety_error_count == 0 and shadow_result.unsafe_approval_count == 0 else "fail_safety",
        overfit_status="pass" if shadow_result.overfit_warning_count == 0 else "warning",
        evidence_status=_evidence_status(aggregate, candidate, shadow_result),
        recommended_next_action=_recommended_next_action(decision),
        paper_only=True,
        live_blocked=True,
        decision_hash="",
    )
    return ZeroDTEThresholdOptimizationDecision(
        optimizer_run_id=draft.optimizer_run_id,
        candidate_threshold_id=draft.candidate_threshold_id,
        decision=draft.decision,
        decision_reason_codes=draft.decision_reason_codes,
        safety_status=draft.safety_status,
        overfit_status=draft.overfit_status,
        evidence_status=draft.evidence_status,
        recommended_next_action=draft.recommended_next_action,
        paper_only=True,
        live_blocked=True,
        decision_hash=zero_dte_optimization_decision_hash(draft),
    )


def decide_zero_dte_threshold_candidates(
    optimizer_run_id: str,
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    candidates: list[ZeroDTEThresholdCandidate],
    shadow_results: list[ZeroDTEShadowReplayResult],
    safety_reason_codes_by_candidate: dict[str, list[str]],
    source_replay_expectations_match: bool,
) -> list[ZeroDTEThresholdOptimizationDecision]:
    shadow_by_candidate = {result.candidate_threshold_id: result for result in shadow_results}
    return [
        decide_zero_dte_threshold_candidate(
            optimizer_run_id,
            aggregate,
            candidate,
            shadow_by_candidate[candidate.candidate_threshold_id],
            safety_reason_codes_by_candidate.get(candidate.candidate_threshold_id, []),
            source_replay_expectations_match,
        )
        for candidate in candidates
    ]


def recommended_threshold_profile(
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    candidates: list[ZeroDTEThresholdCandidate],
    decisions: list[ZeroDTEThresholdOptimizationDecision],
) -> dict[str, Any]:
    candidate_by_id = {candidate.candidate_threshold_id: candidate for candidate in candidates}
    research_defaults = [
        decision for decision in decisions
        if decision.decision == "promote_to_research_default_candidate"
    ]
    paper_shadow = [
        decision for decision in decisions
        if decision.decision == "promote_to_paper_shadow_candidate"
    ]
    selected = research_defaults[0] if research_defaults else (paper_shadow[0] if paper_shadow else None)
    if selected is None:
        return {
            "artifact_type": "zero_dte_recommended_threshold_profile",
            "selected_candidate_threshold_id": "current_thresholds_retained",
            "decision": "retain_current_thresholds",
            "reason_codes": ["no_candidate_passed_promotion_gate"],
            "source_replay_summary_hash": aggregate.source_replay_summary_hash,
            "advisory_only": True,
            "live_threshold_mutation_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
    candidate = candidate_by_id[selected.candidate_threshold_id]
    return {
        "artifact_type": "zero_dte_recommended_threshold_profile",
        "selected_candidate_threshold_id": candidate.candidate_threshold_id,
        "candidate_version": candidate.candidate_version,
        "candidate_hash": candidate.candidate_hash,
        "decision": selected.decision,
        "reason_codes": selected.decision_reason_codes,
        "risk_posture": candidate.risk_posture,
        "promotion_gate": candidate.promotion_gate,
        "source_replay_summary_hash": aggregate.source_replay_summary_hash,
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def retained_current_threshold_decision(
    optimizer_run_id: str,
    aggregate: ZeroDTEThresholdFeedbackAggregate,
) -> ZeroDTEThresholdOptimizationDecision:
    draft = ZeroDTEThresholdOptimizationDecision(
        optimizer_run_id=optimizer_run_id,
        candidate_threshold_id="current_thresholds",
        decision="retain_current_thresholds",
        decision_reason_codes=["no_candidate_improves_current_thresholds", f"source:{aggregate.source_replay_summary_hash}"],
        safety_status="pass",
        overfit_status="pass",
        evidence_status="current_thresholds_retained",
        recommended_next_action="keep_current_thresholds_and_expand_fixtures",
        paper_only=True,
        live_blocked=True,
        decision_hash="",
    )
    return ZeroDTEThresholdOptimizationDecision(
        optimizer_run_id=draft.optimizer_run_id,
        candidate_threshold_id=draft.candidate_threshold_id,
        decision=draft.decision,
        decision_reason_codes=draft.decision_reason_codes,
        safety_status=draft.safety_status,
        overfit_status=draft.overfit_status,
        evidence_status=draft.evidence_status,
        recommended_next_action=draft.recommended_next_action,
        paper_only=True,
        live_blocked=True,
        decision_hash=zero_dte_optimization_decision_hash(draft),
    )


def optimizer_decision_summary(decisions: list[ZeroDTEThresholdOptimizationDecision]) -> dict[str, Any]:
    counts = Counter(decision.decision for decision in decisions)
    return {
        "candidate_decision_count": len(decisions),
        "decision_distribution": dict(sorted(counts.items())),
        "rejected_count": counts.get("reject_candidate", 0),
        "advisory_only_count": counts.get("hold_advisory_only", 0),
        "needs_more_fixture_coverage_count": counts.get("needs_more_fixture_coverage", 0),
        "paper_shadow_candidate_count": counts.get("promote_to_paper_shadow_candidate", 0),
        "research_default_candidate_count": counts.get("promote_to_research_default_candidate", 0),
        "paper_only": True,
        "live_blocked": True,
    }


def _decision_reason_codes(
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    candidate: ZeroDTEThresholdCandidate,
    shadow_result: ZeroDTEShadowReplayResult,
    safety_reason_codes: list[str],
    source_replay_expectations_match: bool,
) -> list[str]:
    reasons: list[str] = [
        f"candidate:{candidate.candidate_threshold_id}",
        f"risk_posture:{candidate.risk_posture}",
        f"promotion_gate:{candidate.promotion_gate}",
    ]
    reasons.extend(safety_reason_codes)
    if shadow_result.safety_error_count > 0:
        reasons.append("shadow_replay_safety_error")
    if shadow_result.unsafe_approval_count > 0:
        reasons.append("unsafe_new_approval_detected")
    if shadow_result.validated_block_preserved_count < len(aggregate.validated_blocks):
        reasons.append("validated_block_not_preserved")
    if shadow_result.overfit_warning_count > 0:
        reasons.append("shadow_replay_overfit_warning")
    if aggregate.possible_overstrict_blocks:
        reasons.append("blocked_maybe_too_strict_requires_more_fixture_coverage")
    if not source_replay_expectations_match:
        reasons.append("source_replay_expectations_not_all_matched")
    if candidate.controls_loosened:
        reasons.append("candidate_loosened_controls")
    if candidate.controls_tightened:
        reasons.append("candidate_tightened_controls")
    return _dedupe(reasons)


def _decision(
    candidate: ZeroDTEThresholdCandidate,
    shadow_result: ZeroDTEShadowReplayResult,
    reason_codes: list[str],
    source_replay_expectations_match: bool,
) -> str:
    if shadow_result.safety_error_count > 0 or shadow_result.unsafe_approval_count > 0:
        return "reject_candidate"
    if candidate.risk_posture in {"rejected_too_loose", "rejected_overfit"}:
        return "reject_candidate"
    if candidate.promotion_gate == "reject" or candidate.controls_loosened:
        return "reject_candidate"
    if candidate.promotion_gate == "needs_more_fixture_coverage":
        return "needs_more_fixture_coverage"
    if candidate.risk_posture == "coverage_expansion_only":
        return "needs_more_fixture_coverage"
    if "blocked_maybe_too_strict_requires_more_fixture_coverage" in reason_codes and not candidate.controls_tightened:
        return "needs_more_fixture_coverage"
    if shadow_result.overfit_warning_count > 0:
        return "hold_advisory_only"
    if candidate.promotion_gate == "research_default_candidate" and source_replay_expectations_match:
        return "promote_to_research_default_candidate"
    if candidate.promotion_gate == "paper_shadow_candidate":
        return "promote_to_paper_shadow_candidate"
    return "hold_advisory_only"


def _evidence_status(
    aggregate: ZeroDTEThresholdFeedbackAggregate,
    candidate: ZeroDTEThresholdCandidate,
    shadow_result: ZeroDTEShadowReplayResult,
) -> str:
    if aggregate.feedback_records_loaded < 20 or aggregate.outcomes_loaded < 20:
        return "insufficient_fixture_coverage"
    if candidate.requires_more_fixture_coverage:
        return "coverage_expansion_needed"
    if shadow_result.unsafe_approval_count > 0:
        return "unsafe_candidate_evidence"
    if shadow_result.new_blocks > 0 or shadow_result.new_throttles > 0 or candidate.candidate_threshold_id == "balanced_research_profile":
        return "supported_by_replay_feedback"
    return "advisory_evidence_only"


def _recommended_next_action(decision: str) -> str:
    actions = {
        "reject_candidate": "retain_rejected_profile_with_reason_codes",
        "hold_advisory_only": "keep_candidate_advisory_and_expand_fixtures",
        "needs_more_fixture_coverage": "add_adversarial_0dte_fixture_coverage",
        "promote_to_paper_shadow_candidate": "use_candidate_in_next_offline_paper_shadow_replay",
        "promote_to_research_default_candidate": "write_offline_research_default_candidate_artifact_only",
        "retain_current_thresholds": "keep_current_thresholds_and_expand_fixtures",
    }
    return actions[decision]


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
