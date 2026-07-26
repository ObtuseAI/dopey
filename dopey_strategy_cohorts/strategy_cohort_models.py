"""Typed models for strategy cohort canonicalization."""
from __future__ import annotations

from typing import TypedDict


COHORT_LEVELS = [
    "variant_id",
    "micro_cohort_id",
    "setup_cohort_id",
    "family_cohort_id",
    "regime_cohort_id",
    "symbol_cluster_cohort_id",
    "canonical_champion_id",
]


class CohortAssignment(TypedDict, total=False):
    variant_id: str
    micro_cohort_id: str
    setup_cohort_id: str
    family_cohort_id: str
    regime_cohort_id: str
    symbol_cluster_cohort_id: str
    canonical_champion_id: str


class CohortSummary(TypedDict, total=False):
    strategy_cohort_status: str
    variant_count: int
    micro_cohort_count: int
    setup_cohort_count: int
    family_cohort_count: int
    regime_cohort_count: int
    symbol_cluster_cohort_count: int
    canonical_cohort_count: int
    public_data_only: bool
    fixture_trade_count: int
    live_trading_enabled: bool


def dte_bucket_group(dte_bucket: int) -> str:
    dte = int(dte_bucket)
    if dte <= 7:
        return "short_dte"
    if dte <= 14:
        return "near_dte"
    if dte <= 30:
        return "mid_dte"
    return "long_dte"


def moneyness_group(moneyness_bucket: str) -> str:
    bucket = str(moneyness_bucket).upper()
    if bucket == "ATM":
        return "atm"
    if "OTM" in bucket:
        return "otm"
    if "ITM" in bucket:
        return "itm"
    return "other"


def exit_style_group(exit_policy: str) -> str:
    policy = str(exit_policy)
    if "scalp" in policy:
        return "scalp"
    if "trend" in policy:
        return "trend_follow"
    if "invalidation" in policy:
        return "invalidation"
    if "theta" in policy:
        return "theta_protective"
    if "volatility" in policy:
        return "vol_hunter"
    return "other"
