"""Deterministic causal diagnostics for canonical research cohorts.

The evaluator is protected infrastructure. Candidates may supply observations,
but cannot tune this implementation, its held-out flags, or its promotion law.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from dopey.protocols.identity import canonical_hash


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _bootstrap_mean_interval(values: Sequence[float], iterations: int, seed: int) -> tuple[float, float]:
    if iterations <= 0:
        raise ValueError(f"bootstrap iterations must be positive: iterations={iterations}")
    if not values:
        return 0.0, 0.0
    generator = random.Random(seed)
    means = [
        sum(values[generator.randrange(len(values))] for _ in values) / len(values)
        for _ in range(iterations)
    ]
    return _quantile(means, 0.025), _quantile(means, 0.975)


def _circular_null(
    signal_values: Sequence[float],
    outcomes: Sequence[float],
    baselines: Sequence[float],
    maximum_shifts: int,
) -> list[float]:
    count = len(outcomes)
    if count < 2:
        return []
    shifts = min(maximum_shifts, count - 1)
    return [
        sum(
            signal_values[index] * outcomes[(index + shift) % count] - baselines[index]
            for index in range(count)
        ) / count
        for shift in range(1, shifts + 1)
    ]


def _benjamini_hochberg(raw: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(raw.items(), key=lambda item: (item[1], item[0]))
    count = len(ordered)
    adjusted: dict[str, float] = {}
    running = 1.0
    for reverse_index in range(count - 1, -1, -1):
        cohort_id, probability = ordered[reverse_index]
        rank = reverse_index + 1
        running = min(running, probability * count / rank)
        adjusted[cohort_id] = min(1.0, running)
    return adjusted


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _validate_record(record: Mapping[str, Any], index: int) -> None:
    required = {"child_id", "canonical_champion_id", "symbol", "era", "signal_value", "outcome_value", "baseline_value", "held_out"}
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"causal evaluation record is incomplete: index={index}, missing={missing}")
    if not -1.0 <= float(record["signal_value"]) <= 1.0:
        raise ValueError(
            "causal signal value must be within [-1, 1]: "
            f"child_id={record['child_id']}, signal_value={record['signal_value']}"
        )


def evaluate_causal_cohorts(
    records: Sequence[Mapping[str, Any]],
    bootstrap_iterations: int,
    seed: int,
    null_shifts: int,
    familywise_alpha: float,
    minimum_sample: int,
) -> dict[str, Any]:
    if not 0.0 < familywise_alpha < 1.0:
        raise ValueError(f"familywise alpha must be within (0, 1): alpha={familywise_alpha}")
    if minimum_sample <= 0:
        raise ValueError(f"causal minimum sample must be positive: minimum_sample={minimum_sample}")
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    child_ids: set[str] = set()
    for index, record in enumerate(records):
        _validate_record(record, index)
        child_id = str(record["child_id"])
        if child_id in child_ids:
            raise ValueError(f"causal evaluation child identity must be unique: child_id={child_id}")
        child_ids.add(child_id)
        grouped[str(record["canonical_champion_id"])].append(record)
    raw_p_values: dict[str, float] = {}
    interim: dict[str, dict[str, Any]] = {}
    for cohort_index, cohort_id in enumerate(sorted(grouped)):
        members = grouped[cohort_id]
        signals = [float(record["signal_value"]) for record in members]
        outcomes = [float(record["outcome_value"]) for record in members]
        baselines = [float(record["baseline_value"]) for record in members]
        contributions = [
            signal * outcome - baseline
            for signal, outcome, baseline in zip(signals, outcomes, baselines, strict=True)
        ]
        observed_gain = _mean(contributions)
        lower, upper = _bootstrap_mean_interval(contributions, bootstrap_iterations, seed + cohort_index)
        null_distribution = _circular_null(signals, outcomes, baselines, null_shifts)
        raw_p = (
            (1 + sum(value >= observed_gain for value in null_distribution)) / (1 + len(null_distribution))
            if null_distribution else 1.0
        )
        raw_p_values[cohort_id] = raw_p
        symbol_gains: dict[str, list[float]] = defaultdict(list)
        era_gains: dict[str, list[float]] = defaultdict(list)
        contested_gains: list[float] = []
        for record, contribution in zip(members, contributions, strict=True):
            symbol_gains[str(record["symbol"])].append(contribution)
            era_gains[str(record["era"])].append(contribution)
            if bool(record.get("contested_truth", False)):
                contested_gains.append(contribution)
        symbol_means = {name: _mean(values) for name, values in symbol_gains.items()}
        era_means = {name: _mean(values) for name, values in era_gains.items()}
        interim[cohort_id] = {
            "cohort_id": cohort_id,
            "sample_count": len(members),
            "child_ids": sorted(str(record["child_id"]) for record in members),
            "observed_gain": observed_gain,
            "noise_adjusted_gain": observed_gain - _mean(null_distribution),
            "bootstrap_mean_gain_ci": [lower, upper],
            "circular_shift_null_mean": _mean(null_distribution),
            "circular_shift_null_p_value": raw_p,
            "replications": bootstrap_iterations,
            "null_replications": len(null_distribution),
            "held_out": all(bool(record["held_out"]) for record in members),
            "symbol_count": len(symbol_means),
            "era_count": len(era_means),
            "symbol_transfer_fraction_positive": (
                sum(value > 0.0 for value in symbol_means.values()) / len(symbol_means)
                if symbol_means else 0.0
            ),
            "era_transfer_fraction_positive": (
                sum(value > 0.0 for value in era_means.values()) / len(era_means)
                if era_means else 0.0
            ),
            "contested_truth_count": len(contested_gains),
            "contested_truth_gain": _mean(contested_gains) if contested_gains else None,
            "child_attribution_preserved": True,
        }
    bh_adjusted = _benjamini_hochberg(raw_p_values)
    cohort_count = max(len(interim), 1)
    evaluations: list[dict[str, Any]] = []
    for cohort_id in sorted(interim):
        record = interim[cohort_id]
        bonferroni = min(1.0, raw_p_values[cohort_id] * cohort_count)
        robust = (
            int(record["sample_count"]) >= minimum_sample
            and float(record["bootstrap_mean_gain_ci"][0]) > 0.0
            and bonferroni <= familywise_alpha
            and bool(record["held_out"])
            and int(record["symbol_count"]) >= 3
            and int(record["era_count"]) >= 2
            and float(record["symbol_transfer_fraction_positive"]) >= 2.0 / 3.0
            and float(record["era_transfer_fraction_positive"]) >= 2.0 / 3.0
            and (
                record["contested_truth_gain"] is None
                or float(record["contested_truth_gain"]) >= 0.0
            )
        )
        causal_confidence = min(
            1.0,
            (int(record["sample_count"]) / minimum_sample)
            * max(0.0, 1.0 - bonferroni)
            * max(0.0, float(record["symbol_transfer_fraction_positive"]))
            * max(0.0, float(record["era_transfer_fraction_positive"])),
        )
        evaluations.append(
            {
                **record,
                "bonferroni_adjusted_p_value": round(bonferroni, 8),
                "benjamini_hochberg_adjusted_p_value": round(bh_adjusted[cohort_id], 8),
                "causal_confidence": round(causal_confidence, 8),
                "cohort_regime_robust": robust,
                "promotion_recommendation": "HELD_OUT_VALIDATED" if robust else "SHADOW_ONLY",
                "automatic_research_state_transition_allowed": True,
                "automatic_research_activation_allowed": False,
                "automatic_promotion_allowed": False,
                "full_promotion_matrix_required": True,
                "human_review_required": False,
            }
        )
    body: dict[str, Any] = {
        "artifact_type": "vnext_causal_cohort_evaluation",
        "causal_evaluation_version": "dopey-causal-evaluation-v1",
        "protected_evaluator": True,
        "optimizer_may_tune_evaluator": False,
        "record_count": len(records),
        "cohort_count": len(evaluations),
        "bootstrap_iterations": bootstrap_iterations,
        "circular_shift_count": null_shifts,
        "multiple_testing_methods": ["bonferroni", "benjamini_hochberg"],
        "familywise_alpha": familywise_alpha,
        "minimum_sample": minimum_sample,
        "evaluations": evaluations,
        "any_cohort_regime_robust": any(record["cohort_regime_robust"] for record in evaluations),
        "statistical_truth_promotion_allowed": False,
        "promotion_authority": "protected_symbol_strategy_pair_threshold_matrix",
        "human_review_required": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}
