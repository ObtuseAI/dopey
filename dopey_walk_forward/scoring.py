"""Dopey walk-forward scoring: deterministic aggregate scoring across replay windows.

Penalize: works only in train, extreme sensitivity to one window, poor liquidity windows, bad
slippage windows, repeated invalidation failure, holdout collapse. Reward: stable performance,
controlled downside, fast invalidation, good liquidity filtering, consistent fill quality,
regime-aware survival. All offline and deterministic.
"""
from __future__ import annotations

from .replay_models import ReplayResult, WalkForwardScore


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def score_walk_forward(results: list[ReplayResult]) -> WalkForwardScore:
    """Compute the aggregate WalkForwardScore from per-window ReplayResults."""
    if not results:
        return WalkForwardScore()

    by_type: dict[str, list[ReplayResult]] = {"train": [], "validation": [], "holdout": []}
    for r in results:
        by_type.setdefault(r.window_type, []).append(r)

    train = by_type.get("train", [])
    val = by_type.get("validation", [])
    holdout = by_type.get("holdout", [])

    train_pnls = [r.paper_pnl for r in train]
    val_pnls = [r.paper_pnl for r in val]
    holdout_pnls = [r.paper_pnl for r in holdout]

    train_mean = _mean(train_pnls)
    val_mean = _mean(val_pnls)
    holdout_mean = _mean(holdout_pnls)

    # window pass rate (pass = pnl >= 0 OR invalidation_triggered with controlled loss)
    passed = [r for r in results if r.verdict == "pass"]
    pass_rate = len(passed) / len(results)

    # regime survival: fraction of distinct regimes that produced a pass
    regimes = {r.regime_tag for r in results}
    surviving_regimes = {r.regime_tag for r in passed}
    regime_survival = len(surviving_regimes) / len(regimes) if regimes else 0.0

    # slippage tolerance: lower avg slippage is better (score = 1 - normalized slippage)
    avg_slip = _mean([r.slippage_score for r in results])
    slippage_tolerance = max(0.0, 1.0 - min(avg_slip, 1.0))

    # liquidity robustness: higher avg liquidity is better
    avg_liq = _mean([r.liquidity_score for r in results])
    liquidity_robustness = min(1.0, avg_liq)

    # invalidation quality: reward fast/triggered invalidations on losing windows (controlled downside)
    losing = [r for r in results if r.paper_pnl < 0]
    invalidated_losing = [r for r in losing if r.invalidation_triggered]
    invalidation_quality = (len(invalidated_losing) / len(losing)) if losing else 1.0

    # consistency: 1 - stdev(pnls)/(|mean|+eps) — lower dispersion = higher consistency
    pnls = [r.paper_pnl for r in results]
    mean_pnl = _mean(pnls)
    if pnls and abs(mean_pnl) > 1e-9:
        var = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
        disp = var ** 0.5
        consistency = max(0.0, 1.0 - min(disp / (abs(mean_pnl) + 1e-6), 1.0))
    else:
        consistency = 0.0 if any(abs(p) > 1e-6 for p in pnls) else 1.0

    # overfit suspicion: train >> OOS, or holdout collapse
    oos_mean = _mean(val_pnls + holdout_pnls)
    if train_mean > 0:
        collapse = max(0.0, (train_mean - oos_mean) / (abs(train_mean) + 1e-6))
    else:
        collapse = 0.0
    holdout_collapse = 1.0 if (holdout_mean < 0) else 0.0
    overfit_suspicion = round(min(1.0, 0.6 * min(collapse, 1.0) + 0.4 * holdout_collapse), 6)

    # overall: blend of pass rate, consistency, survival, liquidity, slippage, invalidation
    overall = round(
        0.25 * pass_rate
        + 0.20 * consistency
        + 0.15 * regime_survival
        + 0.15 * liquidity_robustness
        + 0.10 * slippage_tolerance
        + 0.10 * invalidation_quality
        + 0.05 * (1.0 - overfit_suspicion),
        6)

    return WalkForwardScore(
        consistency_score=round(consistency, 6),
        window_pass_rate=round(pass_rate, 6),
        regime_survival_score=round(regime_survival, 6),
        slippage_tolerance_score=round(slippage_tolerance, 6),
        liquidity_robustness_score=round(liquidity_robustness, 6),
        invalidation_quality_score=round(invalidation_quality, 6),
        overfit_suspicion_score=overfit_suspicion,
        train_mean_pnl=round(train_mean, 6),
        validation_mean_pnl=round(val_mean, 6),
        holdout_mean_pnl=round(holdout_mean, 6),
        overall=overall,
    )
