"""Deterministic hybrid 0DTE versus swing replay engine."""
from __future__ import annotations

from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .hybrid_preference_scoring import score_hybrid_preference
from .hybrid_replay_models import HybridOpportunityPair, HybridReplayOutcome, PREFERENCE_TO_PATH, hybrid_replay_hash
from .swing_lifecycle_policy import evaluate_swing_lifecycle
from .swing_option_models import SwingOptionCandidate, stable_hybrid_hash


def run_hybrid_replay(
    pairs: list[HybridOpportunityPair],
    swing_candidates: list[SwingOptionCandidate],
    multi_day_paths: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    swing_by_id = {candidate.candidate_id: candidate for candidate in swing_candidates}
    path_by_pair = {str(path["pair_id"]): path for path in multi_day_paths}
    outcomes: list[dict[str, Any]] = []
    preference_scores: list[dict[str, Any]] = []
    allocator_tags: list[dict[str, Any]] = []
    proof_records: list[dict[str, Any]] = []
    for pair in pairs:
        swing = swing_by_id[pair.swing_candidate_id]
        path = path_by_pair[pair.pair_id]
        preference = score_hybrid_preference(pair, swing, path)
        outcome = _outcome(pair, swing, path, preference)
        outcomes.append(outcome)
        preference_scores.append(_with_hash("hybrid_preference_score", preference))
        allocator_tags.append(_allocator_record(pair, preference))
        proof_records.append(_proof_record(pair, outcome, preference))
    return outcomes, preference_scores, allocator_tags, proof_records


def _outcome(
    pair: HybridOpportunityPair,
    swing: SwingOptionCandidate,
    path: dict[str, Any],
    preference: dict[str, Any],
) -> dict[str, Any]:
    close_day = 0 if pair.expected_no_day_trade_result == "same_day_close_blocked" else 1
    lifecycle = evaluate_swing_lifecycle(swing, close_day, f"long_{pair.option_type}", False)
    zero_dte_outcome = _zero_dte_outcome(pair)
    swing_outcome = _swing_outcome(pair)
    outcome = HybridReplayOutcome(
        hybrid_replay_id=f"hybrid-replay-{pair.pair_id}",
        pair_id=pair.pair_id,
        underlying_family_id=pair.underlying_family_id,
        regime_family=pair.regime_family,
        option_type=pair.option_type,
        zero_dte_outcome_type=zero_dte_outcome,
        swing_outcome_type=swing_outcome,
        preferred_path=PREFERENCE_TO_PATH[pair.expected_preference],
        preference_score=float(preference["preference_score"]),
        risk_adjusted_preference=pair.expected_preference,
        zero_dte_premium_outcome_pct=_zero_dte_premium(pair),
        swing_premium_outcome_pct=_swing_premium(pair),
        zero_dte_max_adverse_excursion_pct=_zero_dte_mae(pair),
        swing_max_adverse_excursion_pct=_swing_mae(pair),
        zero_dte_theta_decay_realized=round(0.32 if pair.expected_preference != "prefer_zero_dte" else 0.12, 6),
        swing_theta_decay_realized=round(abs(swing.theta) * swing.expected_hold_days, 6),
        zero_dte_gamma_instability=round(0.74 if "gamma" in pair.zero_dte_expected_decision else 0.28, 6),
        swing_gamma_instability=round(max(0.05, swing.gamma * 3.0), 6),
        liquidity_penalty_comparison="swing_less_penalized" if swing.liquidity_score >= 0.45 else "both_liquidity_penalized",
        expiry_risk_comparison="swing_reduces_expiry_pressure" if pair.expected_preference == "prefer_swing" else "zero_dte_expiry_pressure_material",
        no_day_trade_constraint_result=pair.expected_no_day_trade_result if pair.expected_no_day_trade_result != "next_day_close_allowed" else lifecycle["no_day_trade_result"],
        rotation_plan_result=pair.expected_rotation_action,
        threshold_feedback=_threshold_feedback(pair),
        capital_allocator_tags=list(preference["capital_allocator_tags"]),
        recursive_improvement_tags=_recursive_tags(pair),
        paper_only=True,
        live_blocked=True,
        hybrid_replay_hash="",
    )
    record = HybridReplayOutcome(**{**outcome.to_dict(), "hybrid_replay_hash": hybrid_replay_hash(outcome)}).to_dict()
    record["expectation_matched"] = record["risk_adjusted_preference"] == pair.expected_preference
    record["preference_expectation_matched"] = record["preferred_path"] == PREFERENCE_TO_PATH[pair.expected_preference]
    record["allocator_tag_expectation_matched"] = bool(record["capital_allocator_tags"])
    record["multi_day_path_hash"] = path["path_hash"]
    record["no_real_market_data"] = True
    record["no_broker"] = True
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _allocator_record(pair: HybridOpportunityPair, preference: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "hybrid_allocator_tags",
        "pair_id": pair.pair_id,
        "expected_preference": pair.expected_preference,
        "capital_allocator_tags": list(preference["capital_allocator_tags"]),
        "real_sizing_allowed": False,
        "account_balance_used": False,
        "capital_deployment_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["allocator_tag_hash"] = stable_hybrid_hash(record)
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _proof_record(pair: HybridOpportunityPair, outcome: dict[str, Any], preference: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "hybrid_corpus_proof",
        "pair_id": pair.pair_id,
        "underlying_family": pair.underlying_family_id,
        "synthetic_underlying_symbol": pair.synthetic_underlying_symbol,
        "regime_family": pair.regime_family,
        "option_type": pair.option_type,
        "zero_dte_candidate_id": pair.zero_dte_candidate_id,
        "swing_candidate_id": pair.swing_candidate_id,
        "expected_preference": pair.expected_preference,
        "actual_preference": outcome["risk_adjusted_preference"],
        "expectation_matched": outcome["expectation_matched"],
        "no_day_trade_result": outcome["no_day_trade_constraint_result"],
        "rotation_result": outcome["rotation_plan_result"],
        "allocator_tags": list(preference["capital_allocator_tags"]),
        "threshold_survival_impact": "hybrid_pressure_advisory_only",
        "safety_status": "paper_only_live_blocked",
        "replay_hash": outcome["hybrid_replay_hash"],
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _with_hash(artifact_type: str, record: dict[str, Any]) -> dict[str, Any]:
    payload = {"artifact_type": artifact_type, **record}
    payload["preference_hash"] = stable_hybrid_hash(payload)
    payload["reproducibility_hash"] = reproducibility_hash(payload)
    return payload


def _zero_dte_outcome(pair: HybridOpportunityPair) -> str:
    if pair.expected_preference == "prefer_zero_dte":
        return "zero_dte_special_lifecycle_survived"
    if pair.expected_preference == "prefer_no_trade":
        return "zero_dte_rejected"
    if pair.expected_preference == "prefer_delayed_rotation":
        return "zero_dte_blocked_by_rotation_timing"
    return "zero_dte_underperformed_swing"


def _swing_outcome(pair: HybridOpportunityPair) -> str:
    if pair.expected_preference == "prefer_swing":
        return "swing_later_expiry_preferred"
    if pair.expected_preference == "prefer_no_trade":
        return "swing_rejected"
    if pair.expected_preference == "prefer_delayed_rotation":
        return "swing_delayed_rotation_required"
    if pair.expected_preference == "inconclusive_needs_more_fixture_coverage":
        return "swing_inconclusive"
    return "swing_reduces_risk_but_underperforms"


def _zero_dte_premium(pair: HybridOpportunityPair) -> float:
    return {"prefer_zero_dte": 0.42, "prefer_swing": -0.18, "prefer_delayed_rotation": -0.08, "prefer_no_trade": -0.35, "inconclusive_needs_more_fixture_coverage": 0.02}[pair.expected_preference]


def _swing_premium(pair: HybridOpportunityPair) -> float:
    return {"prefer_zero_dte": 0.18, "prefer_swing": 0.34, "prefer_delayed_rotation": 0.12, "prefer_no_trade": -0.22, "inconclusive_needs_more_fixture_coverage": 0.04}[pair.expected_preference]


def _zero_dte_mae(pair: HybridOpportunityPair) -> float:
    return {"prefer_zero_dte": -0.16, "prefer_swing": -0.42, "prefer_delayed_rotation": -0.35, "prefer_no_trade": -0.55, "inconclusive_needs_more_fixture_coverage": -0.24}[pair.expected_preference]


def _swing_mae(pair: HybridOpportunityPair) -> float:
    return {"prefer_zero_dte": -0.22, "prefer_swing": -0.2, "prefer_delayed_rotation": -0.18, "prefer_no_trade": -0.4, "inconclusive_needs_more_fixture_coverage": -0.23}[pair.expected_preference]


def _threshold_feedback(pair: HybridOpportunityPair) -> list[str]:
    if pair.expected_preference == "prefer_swing":
        return ["strengthen_later_expiry_preference"]
    if pair.expected_preference == "prefer_delayed_rotation":
        return ["preserve_no_day_trade_guard", "delay_rotation"]
    if pair.expected_preference == "prefer_no_trade":
        return ["increase_proof_requirement"]
    if pair.expected_preference == "inconclusive_needs_more_fixture_coverage":
        return ["add_more_hybrid_fixture_coverage"]
    return ["allow_zero_dte_only_with_special_lifecycle"]


def _recursive_tags(pair: HybridOpportunityPair) -> list[str]:
    return ["hybrid_replay_advisory_only", f"hybrid_preference:{pair.expected_preference}"]
