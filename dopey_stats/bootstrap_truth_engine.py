"""Deterministic bootstrap diagnostics for model-unit P&L."""
from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import median

from .statistical_metric_calculator import (
    FIXTURE_DIAGNOSTIC_MIN_TRADES,
    REAL_EVIDENCE_MIN_TRADES,
)
from .statistical_truth_models import BootstrapConfidenceInterval


@dataclass(frozen=True)
class BootstrapTruthConfig:
    seed: int
    iterations: int
    confidence_level: float


def default_bootstrap_truth_config() -> BootstrapTruthConfig:
    return BootstrapTruthConfig(seed=8675309, iterations=1000, confidence_level=0.95)


def bootstrap_confidence_intervals(
    pnl_values: list[float],
    real_sample_size: int,
    config: BootstrapTruthConfig,
) -> dict:
    sample_count = len(pnl_values)
    insufficient_sample = sample_count < FIXTURE_DIAGNOSTIC_MIN_TRADES
    insufficient_real_sample = real_sample_size < REAL_EVIDENCE_MIN_TRADES
    if sample_count == 0:
        mean_ci = [0.0, 0.0]
        win_rate_ci = [0.0, 0.0]
        drawdown_ci = [0.0, 0.0]
        median_ci = [0.0, 0.0]
    else:
        rng = random.Random(config.seed)
        mean_samples: list[float] = []
        win_rate_samples: list[float] = []
        drawdown_samples: list[float] = []
        median_samples: list[float] = []
        for _ in range(config.iterations):
            sampled = [pnl_values[rng.randrange(sample_count)] for _ in range(sample_count)]
            mean_samples.append(round(sum(sampled) / sample_count, 6))
            win_rate_samples.append(round(sum(1 for value in sampled if value > 0.0) / sample_count, 6))
            drawdown_samples.append(_max_drawdown(sampled))
            median_samples.append(round(float(median(sampled)), 6))
        mean_ci = _percentile_interval(mean_samples, config.confidence_level)
        win_rate_ci = _percentile_interval(win_rate_samples, config.confidence_level)
        drawdown_ci = _percentile_interval(drawdown_samples, config.confidence_level)
        median_ci = _percentile_interval(median_samples, config.confidence_level)
    interval = BootstrapConfidenceInterval(
        artifact_type="bootstrap_confidence_intervals",
        statistical_truth_version="",
        seed=config.seed,
        iterations=config.iterations,
        sample_count=sample_count,
        insufficient_sample=insufficient_sample,
        insufficient_real_sample=insufficient_real_sample,
        mean_pnl_ci=mean_ci,
        win_rate_ci=win_rate_ci,
        drawdown_ci=drawdown_ci,
        median_pnl_ci=median_ci,
        significance_claim_allowed=False,
        real_alpha_claim_allowed=False,
        promotion_allowed=False,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        ci_hash="",
    )
    return interval.to_dict()


def _percentile_interval(values: list[float], confidence_level: float) -> list[float]:
    ordered = sorted(values)
    if not ordered:
        return [0.0, 0.0]
    lower_q = (1.0 - confidence_level) / 2.0
    upper_q = 1.0 - lower_q
    return [round(_quantile(ordered, lower_q), 6), round(_quantile(ordered, upper_q), 6)]


def _quantile(ordered: list[float], q: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    index = q * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_drawdown = 0.0
    for value in values:
        cumulative = round(cumulative + float(value), 6)
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, round(cumulative - peak, 6))
    return round(max_drawdown, 6)
