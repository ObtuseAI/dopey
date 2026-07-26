"""Deflated Sharpe ratio - the real Bailey & Lopez de Prado statistic.

Replaces the former linear-penalty placeholder. Two components:

1. PSR (probabilistic Sharpe ratio): P[true SR > benchmark] given the observed
   SR, sample size, and the return distribution's skew/kurtosis:
       PSR(SR*) = Phi( (SR - SR*) * sqrt(n - 1) / sqrt(1 - g3*SR + (g4-1)/4 * SR^2) )
2. DSR: PSR evaluated at SR* = E[max SR under N independent trials] - the
   expected best Sharpe pure selection luck would produce across everything
   that was tested:
       SR* = sqrt(V[SR]) * ( (1-gamma)*z(1 - 1/N) + gamma*z(1 - 1/(N*e)) )
   with gamma = Euler-Mascheroni and z the standard normal quantile.

Per-trade model units, no annualization claimed. All outputs stay
diagnostic_only: this layer can veto significance, never grant promotion.
"""
from __future__ import annotations

import math
from typing import Any

from .statistical_truth_models import DeflatedSharpeResult

EULER_MASCHERONI = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Standard normal quantile via bisection on the CDF (dependency-free)."""
    if not 0.0 < p < 1.0:
        return 0.0
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _moments(pnls: list[float]) -> tuple[int, float, float]:
    """(n, skewness g3, kurtosis g4 - non-excess); normal defaults when thin."""
    n = len(pnls)
    if n < 4:
        return n, 0.0, 3.0
    mean = sum(pnls) / n
    m2 = sum((value - mean) ** 2 for value in pnls) / n
    if m2 <= 0:
        return n, 0.0, 3.0
    m3 = sum((value - mean) ** 3 for value in pnls) / n
    m4 = sum((value - mean) ** 4 for value in pnls) / n
    return n, m3 / m2**1.5, m4 / m2**2


def expected_max_sharpe(trials: int, sharpe_variance: float) -> float:
    """E[max SR] across `trials` independent zero-skill strategies."""
    if trials <= 1 or sharpe_variance <= 0:
        return 0.0
    scale = math.sqrt(sharpe_variance)
    return scale * (
        (1.0 - EULER_MASCHERONI) * _norm_ppf(1.0 - 1.0 / trials)
        + EULER_MASCHERONI * _norm_ppf(1.0 - 1.0 / (trials * math.e))
    )


def probabilistic_sharpe(observed: float, benchmark: float, n: int, skew: float, kurtosis: float) -> float:
    """PSR = P[true SR > benchmark]; 0.5 when the sample is too thin to say."""
    if n < 2:
        return 0.5
    denominator = 1.0 - skew * observed + (kurtosis - 1.0) / 4.0 * observed * observed
    if denominator <= 0:
        return 0.5
    return _norm_cdf((observed - benchmark) * math.sqrt(n - 1.0) / math.sqrt(denominator))


def build_deflated_sharpe_result(
    metric_set: dict[str, Any],
    multiple_testing: dict[str, Any],
    pnls: list[float] | None = None,
) -> dict[str, Any]:
    observed = round(float(metric_set.get("sharpe_like_model_units", 0.0)), 6)
    family_count = int(multiple_testing.get("strategy_family_count", 0))
    signal_count = int(multiple_testing.get("tested_signal_family_count", 0))
    trials = max(family_count * max(signal_count, 1), family_count + signal_count, 1)
    n, skew, kurtosis = _moments(list(pnls or []))
    if n < 4:
        n = max(int(metric_set.get("sample_count", metric_set.get("trade_count", 0)) or 0), 2)
    # variance of the SR estimator across trials under H0 (SR=0): ~1/(n-1)
    sr_star = expected_max_sharpe(trials, 1.0 / max(n - 1, 1))
    dsr_probability = probabilistic_sharpe(observed, sr_star, n, skew, kurtosis)
    result = DeflatedSharpeResult(
        artifact_type="deflated_sharpe_result",
        statistical_truth_version="",
        observed_sharpe_like_model_units=observed,
        strategy_family_count=family_count,
        tested_signal_family_count=signal_count,
        diagnostic_only=True,
        deflated_sharpe_model_units=round(observed - sr_star, 6),
        p_value=round(1.0 - dsr_probability, 6),
        significance_claim_allowed=False,
        real_alpha_claim_allowed=False,
        promotion_allowed=False,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        result_hash="",
    )
    record = result.to_dict()
    record.update(
        {
            "dsr_probability_true_sr_positive": round(dsr_probability, 6),
            "expected_max_sharpe_under_trials": round(sr_star, 6),
            "effective_trials": trials,
            "sample_size_used": n,
            "return_skewness": round(skew, 6),
            "return_kurtosis": round(kurtosis, 6),
            "method": "bailey_lopez_de_prado_dsr_psr_per_trade_units",
        }
    )
    return record
