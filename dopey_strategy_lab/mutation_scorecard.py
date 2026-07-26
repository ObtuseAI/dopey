"""Scorecard for expanded offline mutation-population candidates."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .family_mutation_limits import FamilyMutationValidationResult
from .mutation_constraints import MutationConstraintUpdate, score_penalty_from_constraint_updates


MUTATION_SCORECARD_VERSION = "dopey-mutation-scorecard-v1"

MUTATION_RESULT_CATEGORIES: frozenset[str] = frozenset({
    "improved",
    "flat",
    "degraded",
    "overfit",
    "unsafe_rejected",
    "paper_research_candidate",
    "offline_mutation_champion",
})

MIN_IMPROVED_MUTATION_DELTA = 0.005


@dataclass(frozen=True)
class MutationPopulationScorecard:
    strategy_id: str
    parent_strategy_id: str
    family: str
    base_score: float
    adjusted_score: float
    score_delta: float
    result_category: str
    promotion_decision: str
    reasons: list[str] = field(default_factory=list)
    failure_constraint_penalty: float = 0.0
    version: str = MUTATION_SCORECARD_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _weight_adjustment(parameters: dict, row: dict) -> float:
    adjustment = 0.0
    if "delta_preference" in parameters:
        adjustment += 0.010 if 0.35 <= float(parameters["delta_preference"]) <= 0.70 else -0.012
    if "liquidity_threshold" in parameters:
        adjustment += 0.012 if row.get("average_liquidity_score", 0.0) >= float(parameters["liquidity_threshold"]) - 0.08 else -0.018
    if "slippage_tolerance" in parameters:
        adjustment += 0.010 if row.get("average_expected_slippage_pct", 1.0) <= float(parameters["slippage_tolerance"]) else -0.016
    if "theta_tolerance" in parameters:
        adjustment += 0.008 if row.get("average_theta_fit_score", 0.0) >= float(parameters["theta_tolerance"]) else -0.014
    if "vega_tolerance" in parameters:
        adjustment += 0.008 if row.get("average_vega_fit_score", 0.0) >= float(parameters["vega_tolerance"]) else -0.014
    if "greek_fit_weight" in parameters:
        adjustment += 0.012 if row.get("average_greek_fit_score", 0.0) >= 0.60 else -0.018
    if "pattern_confidence_weight" in parameters:
        adjustment += 0.010 if row.get("average_pattern_fixture_score", 0.0) >= 0.55 else -0.016
    if "bad_fill_avoidance_weight" in parameters:
        adjustment += 0.014 if row.get("average_expected_slippage_pct", 1.0) <= 0.055 else -0.025
    if "holdout_consistency_weight" in parameters:
        adjustment += 0.012 if row.get("overfit_level", "high") in {"none", "low"} else -0.024
    if "iv_regime_preference" in parameters:
        adjustment += 0.012 if row.get("average_family_iv_fit_score", 0.0) >= 0.52 else -0.018
        if row.get("average_premium_overpayment_score", 0.0) >= 0.62:
            adjustment -= 0.014
        if row.get("average_iv_crush_score", 0.0) >= 0.70 and str(parameters.get("iv_regime_preference", "")).startswith("event"):
            adjustment -= 0.016
    if "macro_event_guard" in parameters:
        macro_fit = row.get("average_macro_fit_score", 0.5)
        macro_risk = row.get("average_macro_risk_score", 0.5)
        adjustment += 0.012 if macro_fit >= 0.55 else -0.018
        if macro_risk >= 0.62:
            adjustment -= 0.016
        if row.get("average_event_gap_risk_penalty", 0.0) >= 0.60:
            adjustment -= 0.012
    return round(adjustment, 6)


def score_population_candidate(
    row: dict,
    parent_score: float,
    validation: FamilyMutationValidationResult,
    constraint_updates: list[MutationConstraintUpdate],
    is_best_candidate: bool,
) -> MutationPopulationScorecard:
    if not validation.allowed:
        return MutationPopulationScorecard(
            strategy_id=row.get("strategy_id", validation.genome_id),
            parent_strategy_id=row.get("parent_genome_id", ""),
            family=validation.family,
            base_score=0.0,
            adjusted_score=0.0,
            score_delta=0.0,
            result_category="unsafe_rejected",
            promotion_decision="rejected",
            reasons=validation.reasons,
        )
    params = dict(row.get("parameters", {}))
    base = float(row.get("combined_score", 0.0))
    constraint_penalty = score_penalty_from_constraint_updates(validation.family, constraint_updates)
    adjusted = round(max(0.0, min(1.0, base + _weight_adjustment(params, row) - constraint_penalty)), 6)
    delta = round(adjusted - parent_score, 6)
    reasons: list[str] = []
    if row.get("overfit_level") == "high":
        return MutationPopulationScorecard(
            strategy_id=row["strategy_id"],
            parent_strategy_id=row.get("parent_genome_id", ""),
            family=validation.family,
            base_score=base,
            adjusted_score=adjusted,
            score_delta=delta,
            result_category="overfit",
            promotion_decision="rejected",
            reasons=["high overfit"],
            failure_constraint_penalty=constraint_penalty,
        )
    if is_best_candidate and delta > MIN_IMPROVED_MUTATION_DELTA:
        category = "offline_mutation_champion"
        decision = "offline_mutation_champion"
        reasons.append("best valid population mutation beat parent after constraints")
    elif delta > MIN_IMPROVED_MUTATION_DELTA:
        category = "improved"
        decision = "paper_research_candidate"
        reasons.append("mutation improved deterministic paper score")
    elif delta < -0.005:
        category = "degraded"
        decision = "degraded"
        reasons.append("mutation degraded deterministic paper score")
    else:
        category = "flat"
        decision = "research_only"
        reasons.append("mutation remained near parent score")
    return MutationPopulationScorecard(
        strategy_id=row["strategy_id"],
        parent_strategy_id=row.get("parent_genome_id", ""),
        family=validation.family,
        base_score=base,
        adjusted_score=adjusted,
        score_delta=delta,
        result_category=category,
        promotion_decision=decision,
        reasons=reasons,
        failure_constraint_penalty=constraint_penalty,
    )
