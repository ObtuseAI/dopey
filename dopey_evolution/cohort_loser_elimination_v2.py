"""Cohort loser elimination V2.

Identifies fragile / losing cohorts from the champion gate V2 results and the
tournament leaderboard and writes a kill queue. Killed cohorts are excluded from
future mutation seeding.
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import record_with_hash, safe_float

from dopey_strategy_cohorts.strategy_cohort_models import COHORT_LEVELS


def build_cohort_loser_elimination_v2(
    gate_results: list[dict[str, object]],
    leaderboard: list[dict[str, object]],
) -> list[dict[str, object]]:
    kills: list[dict[str, object]] = []
    seen: set[str] = set()
    for result in gate_results:
        cohort_level = str(result.get("cohort_level", ""))
        cohort_id = str(result.get("cohort_id", ""))
        key = f"{cohort_level}::{cohort_id}"
        if key in seen:
            continue
        reasons = list(result.get("rejection_reasons", []))
        net_pnl = safe_float(result.get("net_pnl"))
        sample_count = int(result.get("sample_count", 0))
        should_kill = _should_kill_cohort(reasons, net_pnl, sample_count)
        if should_kill:
            seen.add(key)
            kills.append(record_with_hash({
                "artifact_type": "cohort_loser_elimination_v2",
                "cohort_level": cohort_level,
                "cohort_id": cohort_id,
                "kill_reason": _kill_reason(reasons, net_pnl),
                "net_pnl": net_pnl,
                "sample_count": sample_count,
                "rejection_reasons": reasons,
                "exclude_from_future_mutation_seeding": True,
                "live_trading_enabled": False,
            }, "record_hash"))
    return kills


def _should_kill_cohort(reasons: list[str], net_pnl: float, sample_count: int) -> bool:
    if sample_count >= 30 and net_pnl < 0.0 and "profit_factor_below_minimum" in reasons:
        return True
    if sample_count >= 30 and "expectancy_not_positive" in reasons and "net_pnl_not_positive" in reasons:
        return True
    return False


def _kill_reason(reasons: list[str], net_pnl: float) -> str:
    if net_pnl < 0.0 and "expectancy_not_positive" in reasons:
        return "negative_expectancy_durable_cohort"
    if "profit_factor_below_minimum" in reasons:
        return "profit_factor_below_minimum_durable_cohort"
    return "fragile_cohort"


def killed_cohort_summary(kills: list[dict[str, object]]) -> dict[str, object]:
    by_level: Counter = Counter(str(k.get("cohort_level", "")) for k in kills)
    by_reason: Counter = Counter(str(k.get("kill_reason", "")) for k in kills)
    return {"killed_cohort_count": len(kills), "by_level": dict(by_level), "by_reason": dict(by_reason)}
