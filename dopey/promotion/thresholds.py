"""Sealed threshold policy for autonomous research activation."""

from __future__ import annotations

from typing import Final

from .schema import PromotionThresholds


AUTONOMOUS_PROMOTION_THRESHOLDS: Final[PromotionThresholds] = {
    "threshold_version": "dopey-autonomous-research-promotion-thresholds-v1",
    "symbol_min_history_rows": 504,
    "symbol_min_replay_samples": 100,
    "symbol_min_private_samples": 60,
    "symbol_min_external_samples": 30,
    "symbol_min_forward_samples": 30,
    "symbol_min_independent_strategies": 3,
    "strategy_min_backtest_samples": 300,
    "strategy_min_private_samples": 150,
    "strategy_min_external_samples": 60,
    "strategy_min_forward_samples": 50,
    "strategy_min_symbols": 5,
    "strategy_min_eras": 3,
    "strategy_min_regimes": 3,
    "pair_min_forward_samples": 20,
    "pair_min_regimes": 2,
    "min_causal_confidence": 0.65,
    "max_calibration_error": 0.10,
    "min_transfer_score": 0.67,
    "min_independence_score": 0.60,
    "max_missing_fraction": 0.05,
    "max_complexity_score": 0.35,
    "max_abstention_rate": 0.75,
}
