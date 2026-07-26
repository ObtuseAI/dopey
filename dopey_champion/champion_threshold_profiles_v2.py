"""Champion threshold profiles V2.

Explicit, cohort-aware thresholds. Sample-count minimums scale by cohort level so
tiny-sample flukes cannot pass the gate. Thresholds are never lowered silently.
"""
from __future__ import annotations

from typing import TypedDict


class ChampionThresholdProfileV2(TypedDict):
    profile_id: str
    variant_minimum_trades: int
    micro_cohort_minimum_trades: int
    setup_cohort_minimum_trades: int
    family_cohort_minimum_trades: int
    regime_cohort_minimum_trades: int
    symbol_cluster_cohort_minimum_trades: int
    canonical_champion_minimum_trades: int
    minimum_symbols: int
    minimum_sector_count: int
    minimum_splits_passed_rate: float
    minimum_profit_factor: float
    maximum_drawdown_abs: float
    maximum_top_symbol_trade_share: float
    maximum_top_regime_trade_share: float
    stress_loss_fraction_limit: float


COHORT_SAMPLE_THRESHOLDS = {
    "variant_id": 30,
    "micro_cohort_id": 30,
    "setup_cohort_id": 60,
    "family_cohort_id": 100,
    "regime_cohort_id": 30,
    "symbol_cluster_cohort_id": 30,
    "canonical_champion_id": 30,
}


def champion_threshold_profile_v2() -> ChampionThresholdProfileV2:
    return {
        "profile_id": "public-paper-champion-thresholds-v2-explicit",
        "variant_minimum_trades": 30,
        "micro_cohort_minimum_trades": 30,
        "setup_cohort_minimum_trades": 60,
        "family_cohort_minimum_trades": 100,
        "regime_cohort_minimum_trades": 30,
        "symbol_cluster_cohort_minimum_trades": 30,
        "canonical_champion_minimum_trades": 30,
        "minimum_symbols": 5,
        "minimum_sector_count": 2,
        "minimum_splits_passed_rate": 0.60,
        "minimum_profit_factor": 1.15,
        "maximum_drawdown_abs": 2500.0,
        "maximum_top_symbol_trade_share": 0.45,
        "maximum_top_regime_trade_share": 0.70,
        "stress_loss_fraction_limit": 0.75,
    }


def minimum_trades_for_level(level: str, thresholds: ChampionThresholdProfileV2) -> int:
    return int(thresholds.get(f"{_level_key(level)}_minimum_trades", 30))


def _level_key(level: str) -> str:
    mapping = {
        "variant_id": "variant",
        "micro_cohort_id": "micro_cohort",
        "setup_cohort_id": "setup_cohort",
        "family_cohort_id": "family_cohort",
        "regime_cohort_id": "regime_cohort",
        "symbol_cluster_cohort_id": "symbol_cluster_cohort",
        "canonical_champion_id": "canonical_champion",
    }
    return mapping.get(level, "variant")
