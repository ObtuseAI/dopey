"""Larger deterministic mutation population builder for DOPEY."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

from .family_mutation_limits import FamilyMutationLimitValidator, FamilyMutationValidationResult
from .genome_mutation import MutationInstruction, MutatedStrategyGenome, apply_mutation_instruction
from .population_sampler import sample_population_parents
from .strategy_genome import StrategyGenome


MUTATION_POPULATION_VERSION = "dopey-mutation-population-v1"
MUTATION_POPULATION_BATCH_PREFIX = "mutation-population-batch"

POPULATION_MUTATION_TYPES: tuple[str, ...] = (
    "adjust_delta_preference",
    "adjust_dte_bucket",
    "adjust_liquidity_threshold",
    "adjust_slippage_tolerance",
    "adjust_iv_regime_preference",
    "adjust_pattern_preference",
    "adjust_invalidation_sensitivity",
    "adjust_regime_filter",
    "adjust_spread_structure_proxy",
    "adjust_theta_tolerance",
    "adjust_vega_tolerance",
    "adjust_overfit_penalty",
    "adjust_greek_fit_weighting",
    "adjust_pattern_confidence_weighting",
    "adjust_bad_fill_avoidance_weighting",
    "adjust_holdout_consistency_weighting",
)


@dataclass(frozen=True)
class PopulationMutationRecord:
    parent_genome_id: str
    mutation_id: str
    mutation_type: str
    genome: StrategyGenome
    validation: FamilyMutationValidationResult
    result_category: str
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["genome"] = self.genome.to_dict()
        data["validation"] = self.validation.to_dict()
        return data


@dataclass(frozen=True)
class MutationPopulationBatch:
    batch_id: str
    seed: str
    parent_genome_ids: list[str]
    records: list[PopulationMutationRecord]
    version: str = MUTATION_POPULATION_VERSION

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "seed": self.seed,
            "parent_genome_ids": self.parent_genome_ids,
            "records": [record.to_dict() for record in self.records],
            "version": self.version,
        }

    def valid_records(self) -> list[PopulationMutationRecord]:
        return [record for record in self.records if record.validation.allowed]

    def rejected_records(self) -> list[PopulationMutationRecord]:
        return [record for record in self.records if not record.validation.allowed]


def _instruction(mutation_id: str, mutation_type: str, target_path: str, value: Any, rationale: str) -> MutationInstruction:
    return MutationInstruction(mutation_id, mutation_type, target_path, None, value, rationale)


def _family_instructions(family: str) -> list[MutationInstruction]:
    common_holdout = _instruction("mut-holdout-weight", "adjust_holdout_consistency_weighting", "parameters.holdout_consistency_weight", 0.18, "raise holdout consistency weighting offline")
    if family == "directional_convexity":
        return [
            _instruction("mut-delta-bull", "adjust_delta_preference", "parameters.delta_preference", 0.62, "tune directional delta range"),
            _instruction("mut-liq-tight", "adjust_liquidity_threshold", "parameters.liquidity_threshold", 0.58, "tighten liquidity threshold"),
            _instruction("mut-pattern-fakeout", "adjust_pattern_preference", "parameters.pattern_preference", "trend_vol_continuation", "prefer continuation patterns"),
            _instruction("mut-regime-breakout", "adjust_regime_filter", "parameters.regime_filter", "breakout_or_breakdown_only", "favor breakout regimes"),
            _instruction("mut-vertical-narrow", "adjust_spread_structure_proxy", "parameters.spread_structure_proxy", "narrow_defined_risk_vertical", "prefer narrow verticals"),
            _instruction("mut-greek-gamma", "adjust_greek_fit_weighting", "parameters.greek_fit_weight", 0.16, "raise useful gamma weighting"),
            _instruction("mut-pattern-confidence", "adjust_pattern_confidence_weighting", "parameters.pattern_confidence_weight", 0.14, "raise pattern confidence weighting"),
            common_holdout,
        ]
    if family == "volatility_expansion":
        return [
            _instruction("mut-vega-fit", "adjust_vega_tolerance", "parameters.vega_tolerance", 0.70, "preserve positive vega thesis"),
            _instruction("mut-iv-expansion", "adjust_iv_regime_preference", "parameters.iv_regime_preference", "event_or_macro_expansion", "favor IV expansion regimes"),
            _instruction("mut-theta-tolerance", "adjust_theta_tolerance", "parameters.theta_tolerance", 0.55, "control theta bleed"),
            _instruction("mut-slippage-premium", "adjust_slippage_tolerance", "parameters.slippage_tolerance", 0.055, "penalize premium overpayment"),
            _instruction("mut-pattern-vol", "adjust_pattern_preference", "parameters.pattern_preference", "volatility_expansion_setup", "favor vol expansion patterns"),
            _instruction("mut-strangle", "adjust_spread_structure_proxy", "parameters.spread_structure_proxy", "long_strangle_proxy", "preserve long premium proxy"),
            _instruction("mut-bad-fill", "adjust_bad_fill_avoidance_weighting", "parameters.bad_fill_avoidance_weight", 0.20, "raise bad-fill avoidance"),
            common_holdout,
        ]
    if family == "volatility_compression":
        return [
            _instruction("mut-iv-crush", "adjust_iv_regime_preference", "parameters.iv_regime_preference", "iv_crush_or_range", "favor IV crush context"),
            _instruction("mut-range", "adjust_regime_filter", "parameters.regime_filter", "range_or_chop_only", "favor range/chop regimes"),
            _instruction("mut-condor", "adjust_spread_structure_proxy", "parameters.spread_structure_proxy", "iron_condor_proxy", "preserve defined-risk condor"),
            _instruction("mut-theta-carry", "adjust_theta_tolerance", "parameters.theta_tolerance", 0.72, "raise theta carry weighting"),
            _instruction("mut-slippage-credit", "adjust_slippage_tolerance", "parameters.slippage_tolerance", 0.045, "tighten credit-spread slippage"),
            _instruction("mut-bad-fill", "adjust_bad_fill_avoidance_weighting", "parameters.bad_fill_avoidance_weight", 0.22, "avoid bad-fill credit entries"),
            _instruction("mut-pattern-confidence", "adjust_pattern_confidence_weighting", "parameters.pattern_confidence_weight", 0.13, "raise pattern confidence"),
            common_holdout,
        ]
    return [
        _instruction("mut-dte-short", "adjust_dte_bucket", "parameters.dte_bucket", "7_14", "tune short duration DTE"),
        _instruction("mut-liq-strict", "adjust_liquidity_threshold", "parameters.liquidity_threshold", 0.62, "tighten short-duration liquidity"),
        _instruction("mut-slippage-strict", "adjust_slippage_tolerance", "parameters.slippage_tolerance", 0.040, "tighten slippage sensitivity"),
        _instruction("mut-intraday-pattern", "adjust_pattern_preference", "parameters.pattern_preference", "bullish_breakout_continuation", "prefer clean intraday continuation"),
        _instruction("mut-short-dte-spread", "adjust_spread_structure_proxy", "parameters.spread_structure_proxy", "short_dte_debit_spread_proxy", "prefer defined-risk short-DTE debit spread"),
        _instruction("mut-theta-balance", "adjust_theta_tolerance", "parameters.theta_tolerance", 0.50, "balance gamma/theta risk"),
        _instruction("mut-bad-fill", "adjust_bad_fill_avoidance_weighting", "parameters.bad_fill_avoidance_weight", 0.24, "avoid bad-fill short-duration entries"),
        common_holdout,
    ]


def _unsafe_record(parent: StrategyGenome, unsafe_id: str, mutation_type: str, updates: dict[str, Any]) -> StrategyGenome:
    data = copy.deepcopy(parent.to_dict())
    data["genome_id"] = f"{parent.genome_id}-{unsafe_id}"
    data["version"] = int(parent.version) + 1
    params = data.setdefault("parameters", {})
    params.update(updates)
    params["mutation_parent_id"] = parent.genome_id
    params["mutation_id"] = unsafe_id
    params["mutation_type"] = mutation_type
    params["mutation_rationale"] = "intentional unsafe drift probe for validator"
    return StrategyGenome.from_dict(data)


def _unsafe_family_probe(parent: StrategyGenome) -> StrategyGenome:
    if parent.family == "directional_convexity":
        return _unsafe_record(parent, "mut-unsafe-drift", "adjust_spread_structure_proxy", {
            "spread_structure_proxy": "iron_condor_proxy",
            "thesis_mutation": "volatility_compression_only",
            "directional_exposure": "none",
            "structure_risk": "defined",
        })
    if parent.family == "volatility_expansion":
        return _unsafe_record(parent, "mut-unsafe-short-vol", "adjust_iv_regime_preference", {
            "iv_regime_preference": "iv_crush_only",
            "volatility_bias": "short",
            "positive_vega_thesis": False,
            "structure_risk": "defined",
        })
    if parent.family == "volatility_compression":
        return _unsafe_record(parent, "mut-unsafe-unlimited", "adjust_spread_structure_proxy", {
            "unlimited_risk_short_vol": True,
            "structure_risk": "undefined",
        })
    return _unsafe_record(parent, "mut-unsafe-low-liq", "adjust_liquidity_threshold", {
        "liquidity_threshold": 0.10,
        "spread_width_threshold": 25.0,
        "live_scalping_behavior": True,
        "structure_risk": "defined",
    })


def build_mutation_population(
    parent_genomes: list[StrategyGenome],
    seed: str,
) -> MutationPopulationBatch:
    parents = sample_population_parents(parent_genomes, seed)
    validator = FamilyMutationLimitValidator()
    records: list[PopulationMutationRecord] = []
    for parent in parents:
        for instruction in _family_instructions(parent.family):
            mutation = apply_mutation_instruction(parent, instruction)
            validation = validator.validate(mutation.genome)
            records.append(PopulationMutationRecord(
                parent_genome_id=parent.genome_id,
                mutation_id=mutation.mutation_id,
                mutation_type=mutation.mutation_type,
                genome=mutation.genome,
                validation=validation,
                result_category="paper_research_candidate" if validation.allowed else "unsafe_rejected",
                safety_notes=mutation.safety_notes,
            ))
        unsafe = _unsafe_family_probe(parent)
        validation = validator.validate(unsafe)
        records.append(PopulationMutationRecord(
            parent_genome_id=parent.genome_id,
            mutation_id=str(unsafe.parameters.get("mutation_id", "unsafe")),
            mutation_type=str(unsafe.parameters.get("mutation_type", "unsafe")),
            genome=unsafe,
            validation=validation,
            result_category="unsafe_rejected",
            safety_notes=["intentional unsafe probe rejected by validator"],
        ))
    return MutationPopulationBatch(
        batch_id=f"{MUTATION_POPULATION_BATCH_PREFIX}-{seed}",
        seed=seed,
        parent_genome_ids=[parent.genome_id for parent in parents],
        records=records,
    )
