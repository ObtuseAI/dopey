"""Advisory-only 0DTE replay threshold feedback."""
from __future__ import annotations

from typing import Any

from .zero_dte_outcome_models import (
    ZERO_DTE_THRESHOLD_FEEDBACK_ACTIONS,
    ZeroDTEIntradayState,
    ZeroDTEReplayInput,
    ZeroDTEReplayOutcome,
    ZeroDTEThresholdFeedbackRecord,
    stable_zero_dte_replay_hash,
)
from .zero_dte_risk_thresholds import ZeroDTERiskThresholds


def build_zero_dte_threshold_feedback(
    replay_input: ZeroDTEReplayInput,
    states: list[ZeroDTEIntradayState],
    outcome: ZeroDTEReplayOutcome,
    thresholds: ZeroDTERiskThresholds,
    fixture_feedback: list[str],
) -> ZeroDTEThresholdFeedbackRecord:
    recommendations = _dedupe([*fixture_feedback, *_metric_feedback(states, outcome, thresholds), *_outcome_feedback(outcome)])
    invalid = [item for item in recommendations if item not in ZERO_DTE_THRESHOLD_FEEDBACK_ACTIONS]
    if invalid:
        raise ValueError(f"unsupported 0DTE threshold feedback actions: {invalid}")
    rationale_codes = _rationale_codes(replay_input, states, outcome, recommendations)
    seed = {
        "replay_id": replay_input.replay_id,
        "candidate_id": replay_input.candidate_id,
        "outcome_type": outcome.outcome_type,
        "recommendations": recommendations,
        "rationale_codes": rationale_codes,
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "feedback_hash": "",
    }
    return ZeroDTEThresholdFeedbackRecord(
        replay_id=replay_input.replay_id,
        candidate_id=replay_input.candidate_id,
        outcome_type=outcome.outcome_type,
        recommendations=recommendations,
        rationale_codes=rationale_codes,
        advisory_only=True,
        live_threshold_mutation_allowed=False,
        paper_only=True,
        live_blocked=True,
        feedback_hash=stable_zero_dte_replay_hash(seed),
    )


def threshold_feedback_from_dict(record: dict[str, Any]) -> ZeroDTEThresholdFeedbackRecord:
    return ZeroDTEThresholdFeedbackRecord(
        replay_id=str(record["replay_id"]),
        candidate_id=str(record["candidate_id"]),
        outcome_type=str(record["outcome_type"]),
        recommendations=[str(item) for item in record["recommendations"]],
        rationale_codes=[str(item) for item in record["rationale_codes"]],
        advisory_only=bool(record["advisory_only"]),
        live_threshold_mutation_allowed=bool(record["live_threshold_mutation_allowed"]),
        paper_only=bool(record["paper_only"]),
        live_blocked=bool(record["live_blocked"]),
        feedback_hash=str(record.get("feedback_hash", "")),
    )


def _metric_feedback(
    states: list[ZeroDTEIntradayState],
    outcome: ZeroDTEReplayOutcome,
    thresholds: ZeroDTERiskThresholds,
) -> list[str]:
    if not states:
        raise ValueError("threshold feedback requires intraday states")
    max_spread = max(state.spread_pct for state in states)
    min_liquidity = min(state.liquidity_score for state in states)
    max_gamma_instability = max(abs(state.gamma) * 8.5 for state in states)
    max_theta_pressure = max(max(0.0, -state.theta) / 0.32 for state in states)
    iv_drop = max(state.implied_volatility for state in states) - min(state.implied_volatility for state in states)
    feedback: list[str] = []
    if max_spread > thresholds.max_spread_pct and outcome.outcome_type != "blocked_correctly":
        feedback.append("tighten_spread_threshold")
    if min_liquidity < thresholds.minimum_liquidity_score:
        feedback.append("tighten_liquidity_threshold")
    if max_gamma_instability > thresholds.max_gamma_instability_score:
        feedback.append("tighten_gamma_instability_threshold")
    if max_theta_pressure > thresholds.max_theta_decay_pressure:
        feedback.append("tighten_theta_decay_threshold")
    if iv_drop >= 0.18:
        feedback.append("tighten_iv_overpayment_threshold")
    return feedback


def _outcome_feedback(outcome: ZeroDTEReplayOutcome) -> list[str]:
    if outcome.outcome_type == "blocked_correctly":
        return ["keep_block_reason_validated"]
    if outcome.outcome_type == "blocked_maybe_too_strict":
        return ["mark_inconclusive_needs_more_fixture_coverage"]
    if outcome.outcome_type in {"prefer_later_expiry_confirmed", "prefer_later_expiry_missed_opportunity"}:
        return ["prefer_later_expiry_more_often"]
    if outcome.outcome_type == "throttled_correctly":
        return ["allow_throttle_not_full_block"]
    if outcome.outcome_type == "approved_should_have_been_throttled_more":
        return ["allow_throttle_not_full_block"]
    if outcome.outcome_type == "inconclusive_fixture":
        return ["mark_inconclusive_needs_more_fixture_coverage"]
    return []


def _rationale_codes(
    replay_input: ZeroDTEReplayInput,
    states: list[ZeroDTEIntradayState],
    outcome: ZeroDTEReplayOutcome,
    recommendations: list[str],
) -> list[str]:
    codes = [
        f"source_decision:{replay_input.decision}",
        f"outcome:{outcome.outcome_type}",
    ]
    if states:
        codes.append(f"max_spread:{round(max(state.spread_pct for state in states), 6)}")
        codes.append(f"min_liquidity:{round(min(state.liquidity_score for state in states), 6)}")
        codes.append(f"max_gamma:{round(max(abs(state.gamma) for state in states), 6)}")
    for item in recommendations:
        codes.append(f"feedback:{item}")
    return codes


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
