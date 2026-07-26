"""Matched, cost-complete comparison of a candidate with simple baselines."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .baselines import BASELINE_IDS


@dataclass(frozen=True, slots=True)
class MatchedUtilityObservation:
    opportunity_id: str
    candidate_id: str
    baseline_id: str
    candidate_net_utility: float
    baseline_net_utility: float
    complete_cost_stack: bool
    same_frozen_opportunity: bool


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    baseline_id: str
    matched_pairs: int
    mean_incremental_utility: float
    standard_error: float
    lower_confidence_bound: float
    passed: bool


@dataclass(frozen=True, slots=True)
class SuperiorityDecision:
    candidate_id: str
    comparisons: tuple[BaselineComparison, ...]
    passed_all_required_baselines: bool
    reason_codes: tuple[str, ...]


def evaluate_matched_baseline_superiority(
    observations: tuple[MatchedUtilityObservation, ...],
    required_baseline_ids: frozenset[str],
    minimum_pairs_per_baseline: int,
    one_sided_z_score: float,
) -> SuperiorityDecision:
    if not observations:
        raise ValueError("matched baseline evaluation requires observations")
    if not required_baseline_ids or not required_baseline_ids.issubset(BASELINE_IDS):
        raise ValueError("required baseline IDs must use the canonical vocabulary")
    if minimum_pairs_per_baseline < 2:
        raise ValueError("matched baseline evaluation requires at least two pairs per baseline")
    if not math.isfinite(one_sided_z_score) or one_sided_z_score <= 0.0:
        raise ValueError("one-sided z score must be positive and finite")
    candidate_ids = {observation.candidate_id for observation in observations}
    if len(candidate_ids) != 1 or "" in candidate_ids:
        raise ValueError("matched baseline evaluation requires exactly one candidate identity")
    seen_pairs: set[tuple[str, str]] = set()
    for observation in observations:
        if observation.baseline_id not in BASELINE_IDS:
            raise ValueError(f"unknown baseline ID: baseline_id={observation.baseline_id}")
        if not observation.opportunity_id:
            raise ValueError("matched observation lacks opportunity identity")
        pair = (observation.opportunity_id, observation.baseline_id)
        if pair in seen_pairs:
            raise ValueError(f"matched observation is duplicated: pair={pair}")
        seen_pairs.add(pair)
        if not observation.complete_cost_stack or not observation.same_frozen_opportunity:
            raise ValueError("candidate and baseline must use the same opportunity and complete costs")
        if not all(
            math.isfinite(value)
            for value in (observation.candidate_net_utility, observation.baseline_net_utility)
        ):
            raise ValueError("matched utility values must be finite")
    comparisons: list[BaselineComparison] = []
    reasons: list[str] = []
    for baseline_id in sorted(required_baseline_ids):
        differences = [
            observation.candidate_net_utility - observation.baseline_net_utility
            for observation in observations
            if observation.baseline_id == baseline_id
        ]
        pair_count = len(differences)
        if pair_count < minimum_pairs_per_baseline:
            reasons.append(f"insufficient_matched_pairs:{baseline_id}")
            comparisons.append(
                BaselineComparison(baseline_id, pair_count, math.nan, math.nan, -math.inf, False)
            )
            continue
        mean_difference = statistics.fmean(differences)
        standard_error = statistics.stdev(differences) / math.sqrt(pair_count)
        lower_bound = mean_difference - one_sided_z_score * standard_error
        passed = lower_bound > 0.0
        if not passed:
            reasons.append(f"baseline_lower_bound_not_positive:{baseline_id}")
        comparisons.append(
            BaselineComparison(
                baseline_id,
                pair_count,
                mean_difference,
                standard_error,
                lower_bound,
                passed,
            )
        )
    return SuperiorityDecision(
        next(iter(candidate_ids)),
        tuple(comparisons),
        not reasons,
        tuple(reasons),
    )
