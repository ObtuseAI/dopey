"""Typed inputs and lifecycle states for protected research activation."""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


class ResearchActivationState(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    QUARANTINED = "QUARANTINED"
    SHADOW_ONLY = "SHADOW_ONLY"
    REPLAY_VALIDATED = "REPLAY_VALIDATED"
    PRIVATE_VALIDATED = "PRIVATE_VALIDATED"
    EXTERNAL_VALIDATED = "EXTERNAL_VALIDATED"
    FORWARD_PAPER = "FORWARD_PAPER"
    CONTESTED_VALIDATED = "CONTESTED_VALIDATED"
    RESEARCH_APPROVED = "RESEARCH_APPROVED"
    DEGRADED = "DEGRADED"
    RETIRED = "RETIRED"


class PromotionThresholds(TypedDict):
    threshold_version: str
    symbol_min_history_rows: int
    symbol_min_replay_samples: int
    symbol_min_private_samples: int
    symbol_min_external_samples: int
    symbol_min_forward_samples: int
    symbol_min_independent_strategies: int
    strategy_min_backtest_samples: int
    strategy_min_private_samples: int
    strategy_min_external_samples: int
    strategy_min_forward_samples: int
    strategy_min_symbols: int
    strategy_min_eras: int
    strategy_min_regimes: int
    pair_min_forward_samples: int
    pair_min_regimes: int
    min_causal_confidence: float
    max_calibration_error: float
    min_transfer_score: float
    min_independence_score: float
    max_missing_fraction: float
    max_complexity_score: float
    max_abstention_rate: float


class CommonPromotionEvidence(TypedDict):
    deterministic_replay: bool
    leakage_detected: bool
    revised_data_contamination: bool
    reward_hacking_detected: bool
    causal_confidence: float
    calibration_error: float
    independence_score: float
    missing_fraction: float
    after_cost_gain: float
    contested_gain: float
    confidence_interval_lower: float


class SymbolPromotionEvidence(CommonPromotionEvidence):
    symbol_id: str
    history_rows: int
    replay_samples: int
    private_samples: int
    external_samples: int
    forward_samples: int
    independent_strategies: int


class StrategyPromotionEvidence(CommonPromotionEvidence):
    strategy_id: str
    lineage_id: str
    backtest_samples: int
    private_samples: int
    external_samples: int
    forward_samples: int
    symbol_count: int
    era_count: int
    regime_count: int
    transfer_score: float
    complexity_score: float
    abstention_rate: float
    evaluator_independent: bool


class SymbolStrategyPromotionEvidence(CommonPromotionEvidence):
    symbol_id: str
    strategy_id: str
    forward_samples: int
    regime_count: int
