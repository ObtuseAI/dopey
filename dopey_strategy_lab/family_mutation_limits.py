"""Family-specific mutation envelopes for deterministic DOPEY mutations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .strategy_genome import StrategyGenome


FAMILY_MUTATION_LIMITS_VERSION = "dopey-family-mutation-limits-v1"


@dataclass(frozen=True)
class FamilyMutationLimit:
    family: str
    allowed_mutation_types: list[str]
    disallowed_markers: list[str]
    required_parameters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FamilyMutationValidationResult:
    genome_id: str
    family: str
    allowed: bool
    decision: str
    reasons: list[str] = field(default_factory=list)
    recommended_constraint_updates: list[str] = field(default_factory=list)
    version: str = FAMILY_MUTATION_LIMITS_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


FAMILY_ALLOWED_MUTATION_TYPES: dict[str, set[str]] = {
    "directional_convexity": {
        "adjust_delta_preference",
        "adjust_liquidity_threshold",
        "adjust_pattern_preference",
        "adjust_regime_filter",
        "adjust_spread_structure_proxy",
        "adjust_invalidation_sensitivity",
        "adjust_greek_fit_weighting",
        "adjust_pattern_confidence_weighting",
        "adjust_bad_fill_avoidance_weighting",
        "adjust_holdout_consistency_weighting",
    },
    "volatility_expansion": {
        "adjust_vega_tolerance",
        "adjust_iv_regime_preference",
        "adjust_theta_tolerance",
        "adjust_slippage_tolerance",
        "adjust_pattern_preference",
        "adjust_regime_filter",
        "adjust_spread_structure_proxy",
        "adjust_greek_fit_weighting",
        "adjust_bad_fill_avoidance_weighting",
        "adjust_holdout_consistency_weighting",
    },
    "volatility_compression": {
        "adjust_iv_regime_preference",
        "adjust_regime_filter",
        "adjust_spread_structure_proxy",
        "adjust_theta_tolerance",
        "adjust_slippage_tolerance",
        "adjust_bad_fill_avoidance_weighting",
        "adjust_pattern_confidence_weighting",
        "adjust_holdout_consistency_weighting",
        "adjust_overfit_penalty",
    },
    "short_duration_defined_risk": {
        "adjust_dte_bucket",
        "adjust_liquidity_threshold",
        "adjust_slippage_tolerance",
        "adjust_pattern_preference",
        "adjust_spread_structure_proxy",
        "adjust_theta_tolerance",
        "adjust_invalidation_sensitivity",
        "adjust_bad_fill_avoidance_weighting",
        "adjust_greek_fit_weighting",
        "adjust_holdout_consistency_weighting",
        "adjust_overfit_penalty",
    },
}


def _bool_param(parameters: dict[str, Any], key: str) -> bool:
    return bool(parameters.get(key, False))


def family_mutation_limits() -> dict[str, FamilyMutationLimit]:
    return {
        family: FamilyMutationLimit(
            family=family,
            allowed_mutation_types=sorted(types),
            disallowed_markers=[
                "live_allowed",
                "undefined_risk",
                "naked_short_options",
                "live_promotion_target",
            ],
            required_parameters=["structure_risk"],
        )
        for family, types in FAMILY_ALLOWED_MUTATION_TYPES.items()
    }


class FamilyMutationLimitValidator:
    """Validate one mutated genome against family-specific offline mutation limits."""

    def validate(self, genome: StrategyGenome) -> FamilyMutationValidationResult:
        params = dict(genome.parameters)
        family = genome.family
        mutation_type = str(params.get("mutation_type", ""))
        reasons: list[str] = []
        updates: list[str] = []

        if genome.live_allowed:
            reasons.append("live_allowed true is forbidden")
        if not genome.defined_risk_only:
            reasons.append("defined_risk_only must remain true")
        if params.get("structure_risk", "defined") != "defined":
            reasons.append("structure_risk must remain defined")
        if str(params.get("promotion_tier", "research_only")) in {
            "live_candidate", "micro_live", "adaptive_live", "live",
        }:
            reasons.append("live promotion target is forbidden")
        if _bool_param(params, "naked_short_options") or _bool_param(params, "undefined_risk_selling"):
            reasons.append("naked undefined-risk selling is forbidden")
        allowed_types = FAMILY_ALLOWED_MUTATION_TYPES.get(family, set())
        if mutation_type and mutation_type not in allowed_types:
            reasons.append(f"{mutation_type} is outside {family} mutation envelope")

        if family == "directional_convexity":
            if params.get("thesis_mutation") == "volatility_compression_only":
                reasons.append("directional convexity cannot drift into compression-only thesis")
            if params.get("directional_exposure") == "none":
                reasons.append("directional exposure cannot be removed")
            if str(params.get("spread_structure_proxy", "")).startswith("iron_condor"):
                reasons.append("directional convexity cannot mutate into compression-only iron condor")
            updates.append("keep directional delta/gamma constraints active")

        if family == "volatility_expansion":
            if params.get("iv_regime_preference") == "iv_crush_only":
                reasons.append("volatility expansion cannot mutate into IV-crush-only thesis")
            if params.get("volatility_bias") == "short":
                reasons.append("volatility expansion cannot become naked short volatility")
            if params.get("positive_vega_thesis") is False:
                reasons.append("positive vega/gamma thesis cannot be removed")
            updates.append("preserve positive vega/gamma expansion envelope")

        if family == "volatility_compression":
            if _bool_param(params, "unlimited_risk_short_vol"):
                reasons.append("unlimited-risk short volatility is forbidden")
            if params.get("volatility_bias") == "positive_vega_expansion":
                reasons.append("compression cannot drift into positive-vega expansion thesis")
            updates.append("keep defined-risk credit-spread or condor envelope")

        if family == "short_duration_defined_risk":
            if float(params.get("liquidity_threshold", 0.5)) < 0.35:
                reasons.append("short-duration mutations cannot remove liquidity constraints")
            if float(params.get("spread_width_threshold", 5.0)) > 12.0:
                reasons.append("short-duration structures cannot become wide illiquid structures")
            if _bool_param(params, "live_scalping_behavior"):
                reasons.append("live scalping behavior is forbidden")
            updates.append("keep short-duration liquidity and fakeout constraints active")

        allowed = len(reasons) == 0
        return FamilyMutationValidationResult(
            genome_id=genome.genome_id,
            family=family,
            allowed=allowed,
            decision="valid" if allowed else "unsafe_rejected",
            reasons=reasons,
            recommended_constraint_updates=updates,
        )


def validate_family_mutation(genome: StrategyGenome) -> FamilyMutationValidationResult:
    return FamilyMutationLimitValidator().validate(genome)
