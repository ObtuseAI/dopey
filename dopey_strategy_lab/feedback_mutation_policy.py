"""Generate deterministic replay-only mutations from failure feedback recommendations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .failure_feedback_models import ConstraintTuningRecommendation, FamilyFailureProfile
from .family_mutation_limits import FamilyMutationLimitValidator, FamilyMutationValidationResult
from .genome_mutation import MutationInstruction, apply_mutation_instruction
from .strategy_genome import StrategyGenome


FEEDBACK_MUTATION_POLICY_VERSION = "dopey-feedback-mutation-policy-v1"


@dataclass(frozen=True)
class FeedbackMutationCandidate:
    parent_genome_id: str
    feedback_mutation_id: str
    strategy_family: str
    recommendation_ids: list[str]
    targeted_failure_modes: list[str]
    genome: StrategyGenome
    validation: FamilyMutationValidationResult
    replay_only: bool
    safety_notes: list[str] = field(default_factory=list)
    version: str = FEEDBACK_MUTATION_POLICY_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["recommendation_ids"] = sorted(self.recommendation_ids)
        data["targeted_failure_modes"] = sorted(self.targeted_failure_modes)
        data["genome"] = self.genome.to_dict()
        data["validation"] = self.validation.to_dict()
        data["safety_notes"] = sorted(self.safety_notes)
        return data


@dataclass(frozen=True)
class FeedbackMutationBatch:
    batch_id: str
    seed: str
    candidates: list[FeedbackMutationCandidate]
    version: str = FEEDBACK_MUTATION_POLICY_VERSION

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "seed": self.seed,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "version": self.version,
        }

    def valid_candidates(self) -> list[FeedbackMutationCandidate]:
        return [candidate for candidate in self.candidates if candidate.validation.allowed]


def _instruction(mutation_id: str, mutation_type: str, target_path: str, value: Any, rationale: str) -> MutationInstruction:
    return MutationInstruction(mutation_id, mutation_type, target_path, None, value, rationale)


def _family_instruction_plan(family: str) -> list[MutationInstruction]:
    if family == "directional_convexity":
        return [
            _instruction("fb-liquidity-tight", "adjust_liquidity_threshold", "parameters.liquidity_threshold", 0.60, "tighten liquidity after bad-fill failures"),
            _instruction("fb-fakeout-pattern", "adjust_pattern_preference", "parameters.pattern_preference", "trend_vol_continuation", "raise confirmation after fakeout failures"),
            _instruction("fb-invalidation-tight", "adjust_invalidation_sensitivity", "parameters.invalidation_sensitivity", 0.72, "tighten invalidation after fakeout evidence"),
            _instruction("fb-holdout-weight", "adjust_holdout_consistency_weighting", "parameters.holdout_consistency_weight", 0.22, "raise holdout consistency after failure feedback"),
        ]
    if family == "volatility_expansion":
        return [
            _instruction("fb-iv-confirm", "adjust_iv_regime_preference", "parameters.iv_regime_preference", "event_vol_confirmation_required", "raise IV expansion threshold after IV crush"),
            _instruction("fb-theta-premium", "adjust_theta_tolerance", "parameters.theta_tolerance", 0.58, "increase theta premium guard after IV crush"),
            _instruction("fb-bad-fill", "adjust_bad_fill_avoidance_weighting", "parameters.bad_fill_avoidance_weight", 0.24, "raise bad-fill avoidance after spread failures"),
            _instruction("fb-holdout-weight", "adjust_holdout_consistency_weighting", "parameters.holdout_consistency_weight", 0.24, "raise holdout consistency after overfit evidence"),
        ]
    if family == "volatility_compression":
        return [
            _instruction("fb-macro-guard", "adjust_regime_filter", "parameters.regime_filter", "range_or_chop_without_macro_shock", "avoid compression in macro shock windows"),
            _instruction("fb-slippage-credit", "adjust_slippage_tolerance", "parameters.slippage_tolerance", 0.042, "tighten credit-spread slippage after bad fills"),
            _instruction("fb-bad-fill", "adjust_bad_fill_avoidance_weighting", "parameters.bad_fill_avoidance_weight", 0.25, "raise bad-fill avoidance after spread failures"),
            _instruction("fb-overfit-penalty", "adjust_overfit_penalty", "parameters.overfit_penalty", 0.018, "raise overfit penalty after train-only evidence"),
        ]
    return [
        _instruction("fb-liquidity-strict", "adjust_liquidity_threshold", "parameters.liquidity_threshold", 0.64, "tighten liquidity after decay failures"),
        _instruction("fb-slippage-strict", "adjust_slippage_tolerance", "parameters.slippage_tolerance", 0.038, "tighten slippage after bad-fill failures"),
        _instruction("fb-theta-balance", "adjust_theta_tolerance", "parameters.theta_tolerance", 0.48, "reduce theta tolerance in chop/liquidity-decay windows"),
        _instruction("fb-invalidation-tight", "adjust_invalidation_sensitivity", "parameters.invalidation_sensitivity", 0.74, "tighten short-duration invalidation"),
    ]


def _recommendations_for_family(
    family: str,
    recommendations: list[ConstraintTuningRecommendation],
) -> list[ConstraintTuningRecommendation]:
    return [recommendation for recommendation in recommendations if recommendation.strategy_family == family]


def _targeted_modes(
    family: str,
    family_profiles: list[FamilyFailureProfile],
    family_recommendations: list[ConstraintTuningRecommendation],
) -> list[str]:
    profile_modes = [
        mode
        for profile in family_profiles
        if profile.strategy_family == family
        for mode in profile.top_failure_modes
    ]
    recommendation_modes = [recommendation.failure_mode_id for recommendation in family_recommendations]
    output: list[str] = []
    for mode in profile_modes + recommendation_modes:
        if mode not in output:
            output.append(mode)
    return output[:5]


def build_feedback_mutation_batch(
    parent_genomes: list[StrategyGenome],
    family_profiles: list[FamilyFailureProfile],
    recommendations: list[ConstraintTuningRecommendation],
    seed: str,
) -> FeedbackMutationBatch:
    validator = FamilyMutationLimitValidator()
    candidates: list[FeedbackMutationCandidate] = []
    for parent in sorted(parent_genomes, key=lambda genome: genome.genome_id):
        family_recommendations = _recommendations_for_family(parent.family, recommendations)
        recommendation_ids = [recommendation.recommendation_id for recommendation in family_recommendations]
        targeted_modes = _targeted_modes(parent.family, family_profiles, family_recommendations)
        for instruction in _family_instruction_plan(parent.family):
            mutation = apply_mutation_instruction(parent, instruction)
            mutation.genome.parameters["feedback_seed"] = seed
            mutation.genome.parameters["feedback_recommendation_ids"] = recommendation_ids[:6]
            mutation.genome.parameters["targeted_failure_modes"] = targeted_modes
            mutation.genome.parameters["replay_only_feedback"] = True
            validation = validator.validate(mutation.genome)
            candidates.append(FeedbackMutationCandidate(
                parent_genome_id=parent.genome_id,
                feedback_mutation_id=instruction.mutation_id,
                strategy_family=parent.family,
                recommendation_ids=recommendation_ids[:6],
                targeted_failure_modes=targeted_modes,
                genome=mutation.genome,
                validation=validation,
                replay_only=True,
                safety_notes=[
                    "feedback mutation is replay-only",
                    "live_allowed=false preserved",
                    "defined_risk_only=true preserved",
                    "no broker path added",
                ],
            ))
    return FeedbackMutationBatch(
        batch_id=f"failure-feedback-batch-{seed}",
        seed=seed,
        candidates=candidates,
    )
