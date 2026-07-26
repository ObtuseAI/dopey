"""Deterministic offline 0DTE expiry/outcome replay engine."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .run_zero_dte_risk_model import evaluate_zero_dte_fixture_cases, load_zero_dte_risk_cases
from .zero_dte_expiry_management import simulate_zero_dte_expiry_management
from .zero_dte_outcome_models import (
    ZERO_DTE_REPLAY_MODEL_VERSION,
    ZeroDTEExpiryManagementRecord,
    ZeroDTEIntradayState,
    ZeroDTEReplayDecisionPoint,
    ZeroDTEReplayInput,
    ZeroDTEReplayOutcome,
    ZeroDTEThresholdFeedbackRecord,
    stable_zero_dte_replay_hash,
    zero_dte_replay_hash,
    zero_dte_replay_input_from_risk_decision,
)
from .zero_dte_risk_model import ZERO_DTE_OPEN_APPROVAL_DECISIONS
from .zero_dte_risk_thresholds import ZeroDTERiskThresholds, load_default_zero_dte_risk_thresholds
from .zero_dte_threshold_feedback import build_zero_dte_threshold_feedback


REPO_ROOT = Path(__file__).resolve().parent.parent
ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH = (
    REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy" / "zero_dte_outcome_replay_cases.json"
)
ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH = (
    REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy" / "zero_dte_intraday_paths.json"
)


def load_zero_dte_outcome_replay_cases(path: Path | str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise TypeError("zero_dte_outcome_replay_cases cases must be list")
    records: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("zero_dte_outcome_replay case must be object")
        records.append({
            "replay_id": str(case["replay_id"]),
            "source_case_id": str(case["source_case_id"]),
            "fixture_path_id": str(case["fixture_path_id"]),
            "expected_outcome_type": str(case["expected_outcome_type"]),
            "expected_threshold_feedback": [str(item) for item in case.get("expected_threshold_feedback", [])],
        })
    return records


def load_zero_dte_intraday_paths(path: Path | str) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    defaults = payload.get("state_defaults", {})
    if not isinstance(defaults, dict):
        raise TypeError("zero_dte_intraday_paths state_defaults must be object")
    paths = payload.get("paths", [])
    if not isinstance(paths, list):
        raise TypeError("zero_dte_intraday_paths paths must be list")
    records: dict[str, dict[str, Any]] = {}
    for path_record in paths:
        if not isinstance(path_record, dict):
            raise TypeError("zero_dte intraday path must be object")
        raw_states = path_record.get("states", [])
        if not isinstance(raw_states, list):
            raise TypeError("zero_dte intraday path states must be list")
        states: list[dict[str, Any]] = []
        for raw_state in raw_states:
            if not isinstance(raw_state, dict):
                raise TypeError("zero_dte intraday state must be object")
            states.append({**defaults, **raw_state})
        path_id = str(path_record["path_id"])
        records[path_id] = {**path_record, "path_id": path_id, "states": states}
    return records


def replay_zero_dte_candidate(
    replay_input: ZeroDTEReplayInput,
    intraday_path: dict[str, Any],
    thresholds: ZeroDTERiskThresholds,
    lifecycle_policy: dict[str, Any],
) -> ZeroDTEReplayOutcome:
    details = build_zero_dte_replay_details(replay_input, intraday_path, thresholds, lifecycle_policy)
    return details["outcome"]


def build_zero_dte_replay_details(
    replay_input: ZeroDTEReplayInput,
    intraday_path: dict[str, Any],
    thresholds: ZeroDTERiskThresholds,
    lifecycle_policy: dict[str, Any],
) -> dict[str, Any]:
    states = [ZeroDTEIntradayState.from_dict(record) for record in intraday_path["states"]]
    decision_points = build_replay_decision_points(replay_input, states, intraday_path, thresholds, lifecycle_policy)
    special_close_point = next(
        (point for point in decision_points if point.action == "special_close_simulated" and point.allowed),
        None,
    )
    special_close_used = special_close_point is not None
    special_close_would_reduce_risk = bool(intraday_path["special_close_would_reduce_risk"])
    expiry_record = simulate_zero_dte_expiry_management(
        replay_input,
        states,
        special_close_used,
        special_close_would_reduce_risk,
    )
    metrics = replay_path_metrics(replay_input, states, special_close_point)
    outcome_type = classify_zero_dte_replay_outcome(replay_input, intraday_path, decision_points, metrics, expiry_record)
    threshold_feedback = [str(item) for item in intraday_path.get("expected_threshold_feedback", [])]
    seed = ZeroDTEReplayOutcome(
        replay_id=replay_input.replay_id,
        candidate_id=replay_input.candidate_id,
        decision=replay_input.decision,
        outcome_type=outcome_type,
        outcome_score=outcome_score(outcome_type, metrics),
        premium_outcome_pct=metrics["premium_outcome_pct"],
        max_adverse_excursion_pct=metrics["max_adverse_excursion_pct"],
        max_favorable_excursion_pct=metrics["max_favorable_excursion_pct"],
        theta_decay_realized=metrics["theta_decay_realized"],
        gamma_opportunity_realized=metrics["gamma_opportunity_realized"],
        slippage_realized=metrics["slippage_realized"],
        expiry_state=expiry_record.expiry_state,
        special_close_used=special_close_used,
        special_close_reason=special_close_point.reason_codes[0] if special_close_point and special_close_point.reason_codes else "",
        blocked_reason_codes=blocked_reason_codes(decision_points, replay_input),
        risk_model_alignment=risk_model_alignment(outcome_type),
        threshold_feedback=threshold_feedback,
        recursive_improvement_tags=recursive_improvement_tags(outcome_type, threshold_feedback),
        paper_only=True,
        live_blocked=True,
        replay_hash="",
    )
    outcome = ZeroDTEReplayOutcome(
        replay_id=seed.replay_id,
        candidate_id=seed.candidate_id,
        decision=seed.decision,
        outcome_type=seed.outcome_type,
        outcome_score=seed.outcome_score,
        premium_outcome_pct=seed.premium_outcome_pct,
        max_adverse_excursion_pct=seed.max_adverse_excursion_pct,
        max_favorable_excursion_pct=seed.max_favorable_excursion_pct,
        theta_decay_realized=seed.theta_decay_realized,
        gamma_opportunity_realized=seed.gamma_opportunity_realized,
        slippage_realized=seed.slippage_realized,
        expiry_state=seed.expiry_state,
        special_close_used=seed.special_close_used,
        special_close_reason=seed.special_close_reason,
        blocked_reason_codes=seed.blocked_reason_codes,
        risk_model_alignment=seed.risk_model_alignment,
        threshold_feedback=seed.threshold_feedback,
        recursive_improvement_tags=seed.recursive_improvement_tags,
        paper_only=True,
        live_blocked=True,
        replay_hash=zero_dte_replay_hash(seed),
    )
    feedback = build_zero_dte_threshold_feedback(replay_input, states, outcome, thresholds, threshold_feedback)
    outcome_with_feedback = ZeroDTEReplayOutcome(
        replay_id=outcome.replay_id,
        candidate_id=outcome.candidate_id,
        decision=outcome.decision,
        outcome_type=outcome.outcome_type,
        outcome_score=outcome.outcome_score,
        premium_outcome_pct=outcome.premium_outcome_pct,
        max_adverse_excursion_pct=outcome.max_adverse_excursion_pct,
        max_favorable_excursion_pct=outcome.max_favorable_excursion_pct,
        theta_decay_realized=outcome.theta_decay_realized,
        gamma_opportunity_realized=outcome.gamma_opportunity_realized,
        slippage_realized=outcome.slippage_realized,
        expiry_state=outcome.expiry_state,
        special_close_used=outcome.special_close_used,
        special_close_reason=outcome.special_close_reason,
        blocked_reason_codes=outcome.blocked_reason_codes,
        risk_model_alignment=outcome.risk_model_alignment,
        threshold_feedback=feedback.recommendations,
        recursive_improvement_tags=recursive_improvement_tags(outcome.outcome_type, feedback.recommendations),
        paper_only=True,
        live_blocked=True,
        replay_hash="",
    )
    final_outcome = ZeroDTEReplayOutcome(
        replay_id=outcome_with_feedback.replay_id,
        candidate_id=outcome_with_feedback.candidate_id,
        decision=outcome_with_feedback.decision,
        outcome_type=outcome_with_feedback.outcome_type,
        outcome_score=outcome_with_feedback.outcome_score,
        premium_outcome_pct=outcome_with_feedback.premium_outcome_pct,
        max_adverse_excursion_pct=outcome_with_feedback.max_adverse_excursion_pct,
        max_favorable_excursion_pct=outcome_with_feedback.max_favorable_excursion_pct,
        theta_decay_realized=outcome_with_feedback.theta_decay_realized,
        gamma_opportunity_realized=outcome_with_feedback.gamma_opportunity_realized,
        slippage_realized=outcome_with_feedback.slippage_realized,
        expiry_state=outcome_with_feedback.expiry_state,
        special_close_used=outcome_with_feedback.special_close_used,
        special_close_reason=outcome_with_feedback.special_close_reason,
        blocked_reason_codes=outcome_with_feedback.blocked_reason_codes,
        risk_model_alignment=outcome_with_feedback.risk_model_alignment,
        threshold_feedback=outcome_with_feedback.threshold_feedback,
        recursive_improvement_tags=outcome_with_feedback.recursive_improvement_tags,
        paper_only=True,
        live_blocked=True,
        replay_hash=zero_dte_replay_hash(outcome_with_feedback),
    )
    return {
        "input": replay_input,
        "states": states,
        "decision_points": decision_points,
        "expiry_management": expiry_record,
        "threshold_feedback": feedback,
        "outcome": final_outcome,
        "metrics": metrics,
    }


def build_replay_decision_points(
    replay_input: ZeroDTEReplayInput,
    states: list[ZeroDTEIntradayState],
    intraday_path: dict[str, Any],
    thresholds: ZeroDTERiskThresholds,
    lifecycle_policy: dict[str, Any],
) -> list[ZeroDTEReplayDecisionPoint]:
    if not states:
        raise ValueError("replay requires at least one intraday state")
    points: list[ZeroDTEReplayDecisionPoint] = []
    for state in states:
        point = _decision_point_for_state(replay_input, state, states[-1], intraday_path, thresholds, lifecycle_policy)
        points.append(point)
    return points


def replay_path_metrics(
    replay_input: ZeroDTEReplayInput,
    states: list[ZeroDTEIntradayState],
    special_close_point: ZeroDTEReplayDecisionPoint | None,
) -> dict[str, float]:
    if not states:
        raise ValueError("replay path metrics require intraday states")
    open_price = max(replay_input.open_price, 0.01)
    mid_values = [state.option_mid for state in states]
    exit_state = _exit_state(states, special_close_point)
    exit_value = exit_state.option_bid
    premium_outcome_pct = round(((exit_value - open_price) / open_price) * 100.0, 6)
    max_adverse = round(((min(mid_values) - open_price) / open_price) * 100.0, 6)
    max_favorable = round(((max(mid_values) - open_price) / open_price) * 100.0, 6)
    theta_decay = round(max(0.0, ((open_price - min(mid_values)) / open_price) * 100.0), 6)
    gamma_opportunity = round(max(0.0, max_favorable), 6)
    slippage = round(max(state.estimated_slippage for state in states), 6)
    return {
        "premium_outcome_pct": premium_outcome_pct,
        "max_adverse_excursion_pct": max_adverse,
        "max_favorable_excursion_pct": max_favorable,
        "theta_decay_realized": theta_decay,
        "gamma_opportunity_realized": gamma_opportunity,
        "slippage_realized": slippage,
    }


def classify_zero_dte_replay_outcome(
    replay_input: ZeroDTEReplayInput,
    intraday_path: dict[str, Any],
    decision_points: list[ZeroDTEReplayDecisionPoint],
    metrics: dict[str, float],
    expiry_record: ZeroDTEExpiryManagementRecord,
) -> str:
    if replay_input.paper_only is not True or replay_input.live_blocked is not True:
        return "rejected_policy_violation"
    if any(point.action in {"blocked_close_missing_reason", "blocked_close_liquidity", "blocked_close_risk_cap"} for point in decision_points):
        if replay_input.decision not in ZERO_DTE_OPEN_APPROVAL_DECISIONS:
            return "rejected_policy_violation"
    decision = replay_input.decision
    shape = str(intraday_path["fixture_shape"])
    if decision == "prefer_non_zero_dte_alternative":
        return "prefer_later_expiry_confirmed" if bool(intraday_path["later_expiry_alternative_better"]) else "prefer_later_expiry_missed_opportunity"
    if decision == "expiry_managed_only":
        return "approved_expiry_managed_failure" if expiry_record.expiry_state == "pin_risk_simulated" else "approved_expiry_managed_success"
    if decision == "approved_with_throttle":
        return "throttled_correctly"
    if decision not in ZERO_DTE_OPEN_APPROVAL_DECISIONS:
        if bool(intraday_path["blocked_candidate_unexpectedly_worked"]):
            return "blocked_maybe_too_strict"
        if "policy_violation" in decision or decision == "blocked_live_path":
            return "rejected_policy_violation"
        return "blocked_correctly"
    if any(point.action == "special_close_simulated" and point.allowed for point in decision_points):
        return "approved_special_close_helped"
    if shape in {"early_spike_then_fade", "gamma_squeeze_then_reversal"}:
        return "approved_spiked_then_failed"
    if shape in {"wide_spread_exit_trap", "liquidity_dries_near_close", "iv_crush_after_entry"}:
        return "approved_should_have_been_throttled_more"
    if shape in {"immediate_theta_bleed", "midday_chop_decay", "false_breakout_call_failure", "false_breakdown_put_failure"}:
        return "approved_decayed"
    if shape in {"late_day_rescue_move", "itm_expiry_intrinsic_value"}:
        return "approved_expiry_managed_success"
    if shape == "deep_otm_expires_worthless":
        return "approved_expiry_managed_failure"
    if metrics["premium_outcome_pct"] > 0.0:
        return "approved_survived_fixture"
    return "inconclusive_fixture"


def evaluate_zero_dte_replay_fixture_cases(
    cases: list[dict[str, Any]],
    intraday_paths: dict[str, dict[str, Any]],
    thresholds: ZeroDTERiskThresholds,
) -> dict[str, Any]:
    risk_cases = load_zero_dte_risk_cases()
    risk_records = evaluate_zero_dte_fixture_cases(risk_cases, thresholds)
    risk_by_case = {str(record["case_id"]): record["decision"] for record in risk_records}
    details: list[dict[str, Any]] = []
    for case in cases:
        source_case_id = str(case["source_case_id"])
        fixture_path_id = str(case["fixture_path_id"])
        if source_case_id not in risk_by_case:
            raise KeyError(f"missing 0DTE source risk case: {source_case_id}")
        if fixture_path_id not in intraday_paths:
            raise KeyError(f"missing 0DTE intraday fixture path: {fixture_path_id}")
        replay_input = zero_dte_replay_input_from_risk_decision(
            str(case["replay_id"]),
            fixture_path_id,
            risk_by_case[source_case_id],
        )
        replay = build_zero_dte_replay_details(replay_input, intraday_paths[fixture_path_id], thresholds, _default_lifecycle_policy())
        details.append({
            "case": case,
            "replay": replay,
            "expectation_matched": replay["outcome"].outcome_type == case["expected_outcome_type"],
            "feedback_expectation_matched": set(case["expected_threshold_feedback"]).issubset(set(replay["threshold_feedback"].recommendations)),
        })
    return {
        "risk_records": risk_records,
        "replay_details": details,
    }


def zero_dte_replay_summary(details: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = [record["replay"]["outcome"] for record in details]
    feedback = [
        item
        for record in details
        for item in record["replay"]["threshold_feedback"].recommendations
    ]
    outcome_counts = Counter(outcome.outcome_type for outcome in outcomes)
    feedback_counts = Counter(feedback)
    special_close_used = [outcome for outcome in outcomes if outcome.special_close_used]
    expiry_states = Counter(outcome.expiry_state for outcome in outcomes)
    summary = {
        "zero_dte_replay_model_version": ZERO_DTE_REPLAY_MODEL_VERSION,
        "fixture_case_count": len(details),
        "fixture_path_count": len({record["case"]["fixture_path_id"] for record in details}),
        "replay_count": len(outcomes),
        "outcome_distribution": dict(sorted(outcome_counts.items())),
        "threshold_feedback_distribution": dict(sorted(feedback_counts.items())),
        "approved_outcomes": sum(1 for outcome in outcomes if outcome.decision in ZERO_DTE_OPEN_APPROVAL_DECISIONS),
        "blocked_correctly_count": outcome_counts.get("blocked_correctly", 0),
        "blocked_maybe_too_strict_count": outcome_counts.get("blocked_maybe_too_strict", 0),
        "throttle_feedback_count": outcome_counts.get("throttled_correctly", 0),
        "special_close_used_count": len(special_close_used),
        "expiry_management_distribution": dict(sorted(expiry_states.items())),
        "later_expiry_feedback_count": outcome_counts.get("prefer_later_expiry_confirmed", 0) + outcome_counts.get("prefer_later_expiry_missed_opportunity", 0),
        "all_expectations_matched": all(record["expectation_matched"] for record in details),
        "all_feedback_expectations_matched": all(record["feedback_expectation_matched"] for record in details),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def replay_proof_records(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in details:
        replay = record["replay"]
        outcome: ZeroDTEReplayOutcome = replay["outcome"]
        feedback: ZeroDTEThresholdFeedbackRecord = replay["threshold_feedback"]
        proof = {
            "artifact_type": "zero_dte_replay_proof",
            "replay_id": outcome.replay_id,
            "candidate_id": outcome.candidate_id,
            "source_risk_decision": outcome.decision,
            "fixture_path_id": record["case"]["fixture_path_id"],
            "outcome_type": outcome.outcome_type,
            "key_metrics": {
                "premium_outcome_pct": outcome.premium_outcome_pct,
                "max_adverse_excursion_pct": outcome.max_adverse_excursion_pct,
                "max_favorable_excursion_pct": outcome.max_favorable_excursion_pct,
                "theta_decay_realized": outcome.theta_decay_realized,
                "gamma_opportunity_realized": outcome.gamma_opportunity_realized,
                "slippage_realized": outcome.slippage_realized,
            },
            "threshold_feedback": feedback.recommendations,
            "recursive_improvement_tags": outcome.recursive_improvement_tags,
            "replay_hash": outcome.replay_hash,
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
        }
        proof["reproducibility_hash"] = reproducibility_hash(proof)
        records.append(proof)
    return records


def _decision_point_for_state(
    replay_input: ZeroDTEReplayInput,
    state: ZeroDTEIntradayState,
    final_state: ZeroDTEIntradayState,
    intraday_path: dict[str, Any],
    thresholds: ZeroDTERiskThresholds,
    lifecycle_policy: dict[str, Any],
) -> ZeroDTEReplayDecisionPoint:
    if replay_input.paper_only is not True or replay_input.live_blocked is not True:
        return _point(replay_input, state, "reject_replay", False, ["live_or_non_paper_replay_rejected"], False, False, False, "")
    if replay_input.decision == "prefer_non_zero_dte_alternative":
        return _point(replay_input, state, "prefer_non_zero_dte_alternative", True, ["prefer_later_expiry_more_often"], False, False, False, "")
    if state.close_signal:
        return _special_close_point(replay_input, state, intraday_path, thresholds, lifecycle_policy)
    if replay_input.decision not in ZERO_DTE_OPEN_APPROVAL_DECISIONS and replay_input.decision != "expiry_managed_only":
        return _point(replay_input, state, "reject_replay", False, replay_input.reason_codes, False, False, False, "")
    if state.state_id == final_state.state_id:
        if replay_input.decision == "expiry_managed_only":
            return _point(replay_input, state, "expiry_manage", True, ["expiry_managed_only_no_discretionary_intraday_close"], False, False, True, "zero_dte_expiry_managed")
        if state.option_bid <= 0.05:
            return _point(replay_input, state, "expire_worthless_simulated", True, ["expires_worthless_simulated"], False, False, True, "zero_dte_expiry_managed")
        return _point(replay_input, state, "expire_intrinsic_value_simulated", True, ["expires_intrinsic_value_simulated"], False, False, True, "zero_dte_expiry_managed")
    return _point(replay_input, state, "hold", True, ["zero_dte_replay_hold"], False, False, True, "zero_dte_special_lifecycle")


def _special_close_point(
    replay_input: ZeroDTEReplayInput,
    state: ZeroDTEIntradayState,
    intraday_path: dict[str, Any],
    thresholds: ZeroDTERiskThresholds,
    lifecycle_policy: dict[str, Any],
) -> ZeroDTEReplayDecisionPoint:
    reason = str(intraday_path["special_close_reason"])
    liquidity_approved = bool(intraday_path["special_close_liquidity_approved"])
    risk_cap_approved = bool(intraday_path["special_close_risk_cap_approved"])
    if bool(lifecycle_policy["special_close_reason_required"]) and not reason:
        return _point(replay_input, state, "blocked_close_missing_reason", False, ["missing_special_close_reason"], True, False, False, "")
    if not liquidity_approved or state.liquidity_score < thresholds.minimum_liquidity_score:
        return _point(replay_input, state, "blocked_close_liquidity", False, ["missing_liquidity_approval"], True, False, False, "")
    if not risk_cap_approved:
        return _point(replay_input, state, "blocked_close_risk_cap", False, ["missing_risk_cap_approval"], True, False, False, "")
    return _point(replay_input, state, "special_close_simulated", True, [reason], True, True, True, "zero_dte_expiry_managed")


def _point(
    replay_input: ZeroDTEReplayInput,
    state: ZeroDTEIntradayState,
    action: str,
    allowed: bool,
    reason_codes: list[str],
    special_close_required: bool,
    special_close_allowed: bool,
    expiry_manage_allowed: bool,
    no_day_trade_exception_type: str,
) -> ZeroDTEReplayDecisionPoint:
    return ZeroDTEReplayDecisionPoint(
        decision_point_id=f"{replay_input.replay_id}-{state.state_id}-{action}",
        minute_index=state.minute_index,
        state_id=state.state_id,
        action=action,
        allowed=allowed,
        reason_codes=_dedupe(reason_codes),
        special_close_required=special_close_required,
        special_close_allowed=special_close_allowed,
        expiry_manage_allowed=expiry_manage_allowed,
        no_day_trade_exception_type=no_day_trade_exception_type,
        paper_only=True,
        live_blocked=True,
    )


def _exit_state(
    states: list[ZeroDTEIntradayState],
    special_close_point: ZeroDTEReplayDecisionPoint | None,
) -> ZeroDTEIntradayState:
    if special_close_point is None:
        return states[-1]
    for state in states:
        if state.state_id == special_close_point.state_id:
            return state
    return states[-1]


def outcome_score(outcome_type: str, metrics: dict[str, float]) -> float:
    base = {
        "approved_survived_fixture": 0.82,
        "approved_decayed": 0.25,
        "approved_spiked_then_failed": 0.28,
        "approved_special_close_helped": 0.76,
        "approved_expiry_managed_success": 0.70,
        "approved_expiry_managed_failure": 0.18,
        "approved_should_have_been_throttled_more": 0.35,
        "throttled_correctly": 0.68,
        "blocked_correctly": 0.72,
        "blocked_maybe_too_strict": 0.44,
        "prefer_later_expiry_confirmed": 0.74,
        "prefer_later_expiry_missed_opportunity": 0.38,
        "rejected_policy_violation": 0.12,
        "inconclusive_fixture": 0.40,
    }[outcome_type]
    metric_adjustment = max(-0.08, min(0.08, metrics["premium_outcome_pct"] / 1000.0))
    return round(max(0.0, min(1.0, base + metric_adjustment)), 6)


def risk_model_alignment(outcome_type: str) -> str:
    if outcome_type in {"approved_survived_fixture", "approved_special_close_helped", "approved_expiry_managed_success", "throttled_correctly", "blocked_correctly", "prefer_later_expiry_confirmed"}:
        return "risk_model_aligned"
    if outcome_type in {"approved_decayed", "approved_spiked_then_failed", "approved_should_have_been_throttled_more", "approved_expiry_managed_failure"}:
        return "risk_model_too_permissive_fixture_signal"
    if outcome_type == "blocked_maybe_too_strict":
        return "risk_model_too_restrictive_fixture_signal"
    if outcome_type == "prefer_later_expiry_missed_opportunity":
        return "alternative_policy_needs_more_fixture_coverage"
    return "policy_rejection_valid_or_inconclusive"


def recursive_improvement_tags(outcome_type: str, threshold_feedback: list[str]) -> list[str]:
    tags = ["zero_dte_fixture_only_learning", f"outcome:{outcome_type}"]
    tags.extend(f"feedback:{item}" for item in threshold_feedback)
    if outcome_type in {"approved_decayed", "approved_spiked_then_failed", "approved_should_have_been_throttled_more"}:
        tags.append("candidate_family_requires_stricter_replay_filter")
    if outcome_type == "blocked_maybe_too_strict":
        tags.append("blocked_family_requires_more_fixture_coverage_before_promotion")
    return _dedupe(tags)


def blocked_reason_codes(decision_points: list[ZeroDTEReplayDecisionPoint], replay_input: ZeroDTEReplayInput) -> list[str]:
    reasons = [
        reason
        for point in decision_points
        if not point.allowed
        for reason in point.reason_codes
    ]
    if not reasons and replay_input.decision not in ZERO_DTE_OPEN_APPROVAL_DECISIONS:
        reasons.extend(replay_input.reason_codes)
    return _dedupe(reasons)


def replay_record_hash(record: dict[str, Any]) -> str:
    return stable_zero_dte_replay_hash(record)


def _default_lifecycle_policy() -> dict[str, Any]:
    return {
        "special_close_reason_required": True,
        "liquidity_approval_required": True,
        "risk_cap_approval_required": True,
        "normal_same_day_close_blocked": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
