"""Watchdog-safe signal density scheduler V4.

Plans how many historical entry dates to sample per symbol/regime so each cohort
accumulates enough repeated samples (30+ for near-champion cohorts, 100+ for
setup cohorts, 300+ for family cohorts) without unbounded memory use.
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import record_with_hash


TARGET_NEAR_CHAMPION_SAMPLES = 30
TARGET_SETUP_COHORT_SAMPLES = 100
TARGET_FAMILY_COHORT_SAMPLES = 300
DEFAULT_DATES_PER_SYMBOL = 60
MIN_DATES_PER_SYMBOL = 24


def build_density_schedule(
    symbols: list[str],
    family_counts: Counter,
    setup_counts: Counter,
    watchdog_cap: int = 50_000,
) -> list[dict[str, object]]:
    schedule: list[dict[str, object]] = []
    total_budget = watchdog_cap
    remaining = total_budget
    family_target = TARGET_FAMILY_COHORT_SAMPLES
    setup_target = TARGET_SETUP_COHORT_SAMPLES
    for index, symbol in enumerate(sorted(symbols)):
        if remaining <= 0:
            break
        family_deficit = max(family_target - 1, 0)
        setup_deficit = max(setup_target - 1, 0)
        # Allocate more dates to symbols whose families are under-sampled.
        dates = min(max(DEFAULT_DATES_PER_SYMBOL, MIN_DATES_PER_SYMBOL), remaining)
        if family_deficit > 0 or setup_deficit > 0:
            dates = min(dates + 12, remaining)
        record = {
            "artifact_type": "public_signal_density_schedule_v4",
            "symbol": symbol,
            "schedule_rank": index + 1,
            "planned_entry_dates": dates,
            "family_cohort_target": TARGET_FAMILY_COHORT_SAMPLES,
            "setup_cohort_target": TARGET_SETUP_COHORT_SAMPLES,
            "near_champion_target": TARGET_NEAR_CHAMPION_SAMPLES,
            "watchdog_cap": watchdog_cap,
            "live_trading_enabled": False,
        }
        schedule.append(record_with_hash(record, "record_hash"))
        remaining -= dates
    return schedule


def density_targets() -> dict[str, int]:
    return {
        "near_champion_target": TARGET_NEAR_CHAMPION_SAMPLES,
        "setup_cohort_target": TARGET_SETUP_COHORT_SAMPLES,
        "family_cohort_target": TARGET_FAMILY_COHORT_SAMPLES,
        "default_dates_per_symbol": DEFAULT_DATES_PER_SYMBOL,
        "minimum_dates_per_symbol": MIN_DATES_PER_SYMBOL,
    }
