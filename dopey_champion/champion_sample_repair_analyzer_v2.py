"""Champion sample-repair analyzer V2.

Inspects near-champion cohort rows that failed only one gate dimension and writes
focused repair plans (sample-count densification or walk-forward split repair).
"""
from __future__ import annotations

from dopey_autonomy.public_champion_common import record_with_hash, safe_float


SAMPLE_REPAIR_LABEL = "sample_count_insufficient_near_champion"
SPLIT_REPAIR_LABEL = "walk_forward_fragile_near_champion"


def analyze_near_champions(
    results: list[dict[str, object]],
    thresholds: dict[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    near_champions: list[dict[str, object]] = []
    sample_repair_plans: list[dict[str, object]] = []
    split_repair_plans: list[dict[str, object]] = []
    for result in results:
        reasons = list(result.get("rejection_reasons", []))
        if not reasons:
            continue
        if _is_only_sample_count_failure(reasons, result, thresholds):
            near_champions.append(_near_champion_record(result, SAMPLE_REPAIR_LABEL))
            sample_repair_plans.append(_sample_repair_plan(result, thresholds))
        elif _is_only_split_failure(reasons, result, thresholds):
            near_champions.append(_near_champion_record(result, SPLIT_REPAIR_LABEL))
            split_repair_plans.append(_split_repair_plan(result, thresholds))
    return near_champions, sample_repair_plans, split_repair_plans


def _is_only_sample_count_failure(reasons: list[str], result: dict[str, object], thresholds: dict[str, object]) -> bool:
    return reasons == ["sample_count_below_minimum"]


def _is_only_split_failure(reasons: list[str], result: dict[str, object], thresholds: dict[str, object]) -> bool:
    return reasons == ["walk_forward_split_pass_rate_below_minimum"]


def _near_champion_record(result: dict[str, object], label: str) -> dict[str, object]:
    return record_with_hash({
        "artifact_type": "public_paper_champion_gate_v2_near_champion",
        "cohort_level": result.get("cohort_level", ""),
        "cohort_id": result.get("cohort_id", ""),
        "near_champion_label": label,
        "net_pnl": result.get("net_pnl", 0.0),
        "profit_factor": result.get("profit_factor", 0.0),
        "expectancy": result.get("expectancy", 0.0),
        "sample_count": result.get("sample_count", 0),
        "symbol_count": result.get("symbol_count", 0),
        "split_pass_rate": result.get("split_pass_rate", 0.0),
        "rejection_reasons": result.get("rejection_reasons", []),
        "live_trading_enabled": False,
    }, "record_hash")


def _sample_repair_plan(result: dict[str, object], thresholds: dict[str, object]) -> dict[str, object]:
    current = int(result.get("sample_count", 0))
    target = int(thresholds.get("minimum_trades_for_level", 30))
    deficit = max(target - current, 0)
    return record_with_hash({
        "artifact_type": "public_paper_champion_gate_v2_sample_repair_plan",
        "cohort_level": result.get("cohort_level", ""),
        "cohort_id": result.get("cohort_id", ""),
        "near_champion_label": SAMPLE_REPAIR_LABEL,
        "current_sample_count": current,
        "target_sample_count": target,
        "sample_deficit": deficit,
        "repair_action": "densify_dates_symbols_sector_peers",
        "repair_axes": ["dates", "symbols", "sector_peers", "adjacent_dte", "adjacent_moneyness", "alternate_exits"],
        "estimated_new_candidates_needed": max(deficit * 4, 30),
        "live_trading_enabled": False,
    }, "record_hash")


def _split_repair_plan(result: dict[str, object], thresholds: dict[str, object]) -> dict[str, object]:
    return record_with_hash({
        "artifact_type": "public_paper_champion_gate_v2_walk_forward_repair_plan",
        "cohort_level": result.get("cohort_level", ""),
        "cohort_id": result.get("cohort_id", ""),
        "near_champion_label": SPLIT_REPAIR_LABEL,
        "current_split_pass_rate": result.get("split_pass_rate", 0.0),
        "target_split_pass_rate": float(thresholds.get("minimum_splits_passed_rate", 0.60)),
        "repair_action": "widen_invalidation_alternate_exits_reduce_split_fragility",
        "repair_axes": ["invalidation_factor", "exit_policy", "dte_bucket", "moneyness_bucket"],
        "live_trading_enabled": False,
    }, "record_hash")
