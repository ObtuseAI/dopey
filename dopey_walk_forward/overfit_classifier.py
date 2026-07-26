"""Dopey walk-forward overfit classifier (extends dopey_strategy_lab.overfit_detector).

Deterministic classification: none | low | moderate | high.

- high: train passes strongly but validation/holdout fail (classic curve-fit).
- moderate: train passes, one validation passes but holdout fails; OR validation collapse.
- low: train, validation, AND holdout all survive within thresholds.
- none: train passes and holdout passes with validation non-negative (robust).
"""
from __future__ import annotations

from .replay_models import OverfitSignal


def classify_overfit(*, train_passed: bool, validation_passed: bool, holdout_passed: bool,
                     train_pnl: float = 0.0, validation_pnl: float = 0.0, holdout_pnl: float = 0.0,
                     overfit_suspicion: float = 0.0) -> OverfitSignal:
    reasons: list[str] = []
    if train_passed and not validation_passed and not holdout_passed:
        level = "high"
        reasons.append("train passes but validation and holdout both fail (curve-fit)")
    elif train_passed and validation_passed and not holdout_passed:
        level = "moderate"
        reasons.append("train+validation pass but holdout fails (tail fragility)")
    elif train_passed and not validation_passed and holdout_passed:
        level = "moderate"
        reasons.append("train+holdout pass but validation fails (regime-specific)")
    elif train_passed and validation_passed and holdout_passed:
        if holdout_pnl < 0 or overfit_suspicion >= 0.6:
            level = "low"
            reasons.append("all windows pass but holdout pnl negative or elevated suspicion")
        else:
            level = "none"
            reasons.append("all windows pass with non-negative holdout pnl")
    elif not train_passed:
        level = "high"
        reasons.append("train itself fails (no edge to evaluate)")
    else:
        level = "moderate"
        reasons.append("mixed window survival; manual review")
    return OverfitSignal(
        level=level, reasons=reasons,
        train_passed=train_passed, validation_passed=validation_passed, holdout_passed=holdout_passed,
    )
