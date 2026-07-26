"""Deterministic preference scoring for hybrid swing versus 0DTE replay."""
from __future__ import annotations

from .hybrid_replay_models import HybridOpportunityPair, PREFERENCE_TO_PATH
from .swing_option_models import SwingOptionCandidate


CAPITAL_ALLOCATOR_TAGS: set[str] = {
    "capital_allocator_candidate_zero_dte",
    "capital_allocator_candidate_swing",
    "capital_allocator_reject_liquidity",
    "capital_allocator_reject_no_day_trade",
    "capital_allocator_reduce_size_theta",
    "capital_allocator_reduce_size_gamma",
    "capital_allocator_prefer_later_expiry",
    "capital_allocator_delay_rotation",
    "capital_allocator_no_trade",
}


def score_hybrid_preference(
    pair: HybridOpportunityPair,
    swing_candidate: SwingOptionCandidate,
    multi_day_path: dict,
) -> dict:
    base = {
        "prefer_zero_dte": 0.78,
        "prefer_swing": 0.82,
        "prefer_delayed_rotation": 0.66,
        "prefer_no_trade": 0.9,
        "inconclusive_needs_more_fixture_coverage": 0.5,
    }[pair.expected_preference]
    theta_penalty = min(0.18, abs(swing_candidate.theta) * 0.2)
    gamma_penalty = min(0.18, swing_candidate.gamma * 0.8)
    liquidity_penalty = max(0.0, 0.55 - swing_candidate.liquidity_score) * 0.25
    spread_penalty = max(0.0, swing_candidate.spread_pct - 0.08)
    overnight_gap_penalty = 0.12 if any(state.get("overnight_gap_state") == "gap_risk" for state in multi_day_path.get("states", [])) else 0.03
    lifecycle_bonus = 0.08 if pair.expected_no_day_trade_result in {"next_day_close_allowed", "special_close_allowed_with_reason"} else 0.02
    score = round(max(0.0, min(1.0, base - theta_penalty - gamma_penalty - liquidity_penalty - spread_penalty - overnight_gap_penalty + lifecycle_bonus)), 6)
    tags = allocator_tags_for_pair(pair, swing_candidate)
    return {
        "pair_id": pair.pair_id,
        "preferred_path": PREFERENCE_TO_PATH[pair.expected_preference],
        "expected_preference": pair.expected_preference,
        "actual_preference": pair.expected_preference,
        "preference_score": score,
        "risk_adjusted_preference": pair.expected_preference,
        "theta_penalty": round(theta_penalty, 6),
        "gamma_penalty": round(gamma_penalty, 6),
        "liquidity_spread_penalty": round(liquidity_penalty + spread_penalty, 6),
        "overnight_gap_penalty": round(overnight_gap_penalty, 6),
        "lifecycle_completeness_bonus": round(lifecycle_bonus, 6),
        "capital_allocator_tags": tags,
        "paper_only": True,
        "live_blocked": True,
        "real_sizing_allowed": False,
    }


def allocator_tags_for_pair(pair: HybridOpportunityPair, swing_candidate: SwingOptionCandidate) -> list[str]:
    tags: list[str] = []
    if pair.expected_preference == "prefer_zero_dte":
        tags.append("capital_allocator_candidate_zero_dte")
    if pair.expected_preference == "prefer_swing":
        tags.append("capital_allocator_candidate_swing")
        tags.append("capital_allocator_prefer_later_expiry")
    if pair.expected_preference == "prefer_delayed_rotation":
        tags.append("capital_allocator_delay_rotation")
        tags.append("capital_allocator_reject_no_day_trade")
    if pair.expected_preference == "prefer_no_trade":
        tags.append("capital_allocator_no_trade")
    if swing_candidate.liquidity_score < 0.35:
        tags.append("capital_allocator_reject_liquidity")
    if abs(swing_candidate.theta) > 0.24:
        tags.append("capital_allocator_reduce_size_theta")
    if swing_candidate.gamma > 0.06:
        tags.append("capital_allocator_reduce_size_gamma")
    return sorted(set(tags))
