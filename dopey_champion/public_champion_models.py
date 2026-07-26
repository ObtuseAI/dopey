"""Typed public champion gate models."""
from __future__ import annotations

from typing import TypedDict


class ChampionThresholdProfile(TypedDict):
    profile_id: str
    minimum_trades: int
    minimum_symbols: int
    minimum_splits_passed_rate: float
    minimum_profit_factor: float
    maximum_drawdown_abs: float
    maximum_top_symbol_trade_share: float
    maximum_top_regime_trade_share: float
    stress_loss_fraction_limit: float


class ChampionGateDecision(TypedDict):
    strategy_id: str
    promotion_level: str
    public_data_paper_champion: bool
    live_gate_candidate_locked: bool
    rejection_reasons: list[str]


def champion_threshold_profile_v1() -> ChampionThresholdProfile:
    return {
        "profile_id": "public-paper-champion-thresholds-v1-explicit",
        "minimum_trades": 30,
        "minimum_symbols": 5,
        "minimum_splits_passed_rate": 0.60,
        "minimum_profit_factor": 1.15,
        "maximum_drawdown_abs": 2500.0,
        "maximum_top_symbol_trade_share": 0.45,
        "maximum_top_regime_trade_share": 0.70,
        "stress_loss_fraction_limit": 0.75,
    }

