"""Cost, fill, timing, and tail stress mechanics for paper-only candidate evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields

from .gates import GateDecision


@dataclass(frozen=True, slots=True)
class PaperEconomics:
    gross_utility: float
    spread_cost: float
    commission_cost: float
    slippage_cost: float
    market_impact_cost: float
    funding_cost: float
    borrow_cost: float
    assignment_and_exercise_cost: float


@dataclass(frozen=True, slots=True)
class StressScenario:
    scenario_id: str
    spread_multiplier: float
    commission_multiplier: float
    slippage_multiplier: float
    impact_multiplier: float
    fill_fraction: float
    timing_penalty: float
    tail_loss: float


@dataclass(frozen=True, slots=True)
class StressResult:
    scenario_id: str
    stressed_net_utility: float
    survived_floor: bool


@dataclass(frozen=True, slots=True)
class RequiredStressEvidence:
    scenario_id: str
    family: str
    completed: bool
    passed: bool
    evidence_id: str


V1_REQUIRED_STRESS_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "cost",
        (
            "doubled_spread",
            "tripled_spread",
            "higher_commission",
            "worse_price_improvement",
            "leg_by_leg_fills",
            "package_fill_degradation",
            "increased_market_impact",
        ),
    ),
    (
        "timing",
        (
            "delayed_entry",
            "delayed_exit",
            "missed_first_quote",
            "missed_best_quote",
            "slower_data",
            "stale_signal",
            "event_timestamp_shift",
        ),
    ),
    (
        "liquidity",
        (
            "reduced_size",
            "reduced_depth",
            "rejected_orders",
            "partial_fills",
            "widened_markets",
            "unavailable_strikes",
            "unavailable_expirations",
            "inability_to_close",
        ),
    ),
    (
        "volatility",
        (
            "implied_volatility_spike",
            "implied_volatility_collapse",
            "skew_steepening",
            "skew_flattening",
            "term_structure_inversion",
            "correlation_spike",
            "vol_of_vol_shock",
        ),
    ),
    (
        "price_path",
        (
            "immediate_adverse_move",
            "overnight_gap",
            "reversal_after_entry",
            "slow_drift",
            "violent_mean_reversion",
            "pinning_near_strike",
            "discontinuous_jump",
        ),
    ),
    (
        "operational",
        (
            "broker_or_venue_outage",
            "duplicate_order",
            "lost_acknowledgement",
            "stale_market_data",
            "clock_drift",
            "corporate_action_mismatch",
            "incorrect_multiplier",
            "missed_expiration_action",
            "unexpected_assignment",
        ),
    ),
    (
        "portfolio",
        (
            "all_positions_correlated",
            "simultaneous_short_gamma_loss",
            "concentrated_vega",
            "liquidity_disappearance",
            "sector_shock",
            "macro_shock",
            "event_clustering",
            "margin_expansion",
        ),
    ),
    (
        "statistical",
        (
            "alternate_temporal_blocks",
            "removed_best_period",
            "removed_best_underlying",
            "different_random_seeds",
            "parameter_perturbations",
            "feature_ablations",
            "different_cleaning_rules",
            "selection_aware_corrections",
            "simpler_competing_models",
        ),
    ),
    (
        "behavioral",
        (
            "loss_streak",
            "win_streak",
            "drawdown",
            "missed_trade",
            "post_loss_size_temptation",
            "fomo_environment",
            "increased_trade_frequency",
            "rule_change_temptation",
        ),
    ),
)


def v1_required_stress_requirements() -> tuple[tuple[str, str], ...]:
    return tuple(
        (family, scenario_id)
        for family, scenario_ids in V1_REQUIRED_STRESS_FAMILIES
        for scenario_id in scenario_ids
    )


def evaluate_required_stress_evidence(
    results: tuple[RequiredStressEvidence, ...],
) -> GateDecision:
    required = v1_required_stress_requirements()
    required_by_id = {scenario_id: family for family, scenario_id in required}
    if len(required_by_id) != len(required):
        raise ValueError("required stress identities must be globally unique")
    observed_by_id = {result.scenario_id: result for result in results}
    reasons: list[str] = []
    if len(observed_by_id) != len(results):
        reasons.append("duplicate_stress_scenario_id")
    for scenario_id, family in sorted(required_by_id.items()):
        result = observed_by_id.get(scenario_id)
        if result is None:
            reasons.append(f"missing_required_stress:{scenario_id}")
            continue
        if result.family != family:
            reasons.append(f"stress_family_mismatch:{scenario_id}")
        if not result.completed:
            reasons.append(f"stress_incomplete:{scenario_id}")
        if not result.passed:
            reasons.append(f"stress_failed:{scenario_id}")
        if not result.evidence_id:
            reasons.append(f"stress_evidence_missing:{scenario_id}")
    unexpected = sorted(set(observed_by_id).difference(required_by_id))
    reasons.extend(f"unexpected_stress_scenario:{scenario_id}" for scenario_id in unexpected)
    return GateDecision(
        passed=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
        automatic_effect="promotion_review_allowed" if not reasons else "certification_blocked",
    )


def v1_required_stress_scenarios() -> tuple[StressScenario, ...]:
    return (
        StressScenario("base_complete_costs", 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        StressScenario("doubled_spread", 2.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        StressScenario("tripled_spread", 3.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        StressScenario("slippage_and_impact_shock", 1.0, 1.0, 2.0, 3.0, 1.0, 0.0, 0.0),
        StressScenario("partial_fill_opportunity_cost", 1.5, 1.0, 1.5, 2.0, 0.5, 0.01, 0.0),
        StressScenario("delayed_entry", 1.0, 1.0, 1.5, 1.0, 1.0, 0.02, 0.0),
        StressScenario("gap_and_tail_loss", 2.0, 1.0, 2.0, 3.0, 1.0, 0.0, 0.05),
    )


def evaluate_stress_matrix(
    economics: PaperEconomics,
    scenarios: tuple[StressScenario, ...],
    minimum_net_utility: float,
) -> tuple[StressResult, ...]:
    economic_values = tuple(float(getattr(economics, field.name)) for field in fields(economics))
    if any(not math.isfinite(value) for value in economic_values):
        raise ValueError("stress economics must be finite")
    if any(value < 0.0 for value in economic_values[1:]):
        raise ValueError("stress cost components cannot be negative")
    if not math.isfinite(minimum_net_utility):
        raise ValueError("stress utility floor must be finite")
    if not scenarios or len({scenario.scenario_id for scenario in scenarios}) != len(scenarios):
        raise ValueError("stress scenarios require unique non-empty identities")
    results: list[StressResult] = []
    for scenario in scenarios:
        multipliers = (
            scenario.spread_multiplier,
            scenario.commission_multiplier,
            scenario.slippage_multiplier,
            scenario.impact_multiplier,
        )
        if (
            not scenario.scenario_id
            or any(not math.isfinite(value) or value < 1.0 for value in multipliers)
            or not math.isfinite(scenario.fill_fraction)
            or not 0.0 <= scenario.fill_fraction <= 1.0
            or not math.isfinite(scenario.timing_penalty)
            or scenario.timing_penalty < 0.0
            or not math.isfinite(scenario.tail_loss)
            or scenario.tail_loss < 0.0
        ):
            raise ValueError(f"stress scenario is invalid: scenario_id={scenario.scenario_id!r}")
        gross_after_fill = economics.gross_utility * scenario.fill_fraction
        costs = (
            economics.spread_cost * scenario.spread_multiplier
            + economics.commission_cost * scenario.commission_multiplier
            + economics.slippage_cost * scenario.slippage_multiplier
            + economics.market_impact_cost * scenario.impact_multiplier
            + economics.funding_cost
            + economics.borrow_cost
            + economics.assignment_and_exercise_cost
            + scenario.timing_penalty
            + scenario.tail_loss
        )
        net = gross_after_fill - costs
        results.append(StressResult(scenario.scenario_id, net, net >= minimum_net_utility))
    return tuple(results)
