"""Public paper champion gate V2 with sample repair.

Evaluates the V4 cohort tournament leaderboard against explicit cohort-aware
thresholds. Promotes only public-data candidates that clear every threshold.
Near champions that fail only sample-count or only split-pass emit labeled
repair plans. Thresholds are never lowered silently. Live promotion is blocked.
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import (
    CHAMPION_ROOT,
    proof_record,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_deepening_common import TOURNAMENT_ROOT

from .champion_sample_repair_analyzer_v2 import analyze_near_champions
from .champion_threshold_profiles_v2 import champion_threshold_profile_v2, minimum_trades_for_level


CANDIDATES_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_candidates.jsonl"
RESULTS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_results.jsonl"
REJECTIONS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_rejections.jsonl"
NEAR_CHAMPIONS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_near_champions.jsonl"
SAMPLE_REPAIR_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_sample_repair_plan.jsonl"
SUMMARY_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_summary.json"
PROOF_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_proof.jsonl"

LEADERBOARD_PATH = TOURNAMENT_ROOT / "public_cohort_tournament_leaderboard_v4.jsonl"


def run_public_paper_champion_gate_v2() -> dict[str, object]:
    leaderboard = read_jsonl_file(LEADERBOARD_PATH)
    thresholds = champion_threshold_profile_v2()
    return evaluate_public_paper_champions_v2(leaderboard, thresholds, artifact_mode="canonical", persist=True)


def evaluate_public_paper_champions_v2(
    leaderboard: list[dict[str, object]],
    thresholds: dict[str, object],
    *,
    artifact_mode: str = "test",
    persist: bool = True,
) -> dict[str, object]:
    candidates = [record_with_hash(candidate_record_v2(row, thresholds), "record_hash") for row in leaderboard]
    results: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    for row in leaderboard:
        decision = champion_decision_v2(row, thresholds)
        result = record_with_hash({**row, **decision, "threshold_profile": thresholds}, "record_hash")
        results.append(result)
        if decision["rejection_reasons"]:
            rejections.append(record_with_hash(rejection_record_v2(row, decision["rejection_reasons"], thresholds), "record_hash"))

    near_champions, sample_repair_plans, split_repair_plans = analyze_near_champions(results, thresholds)
    repair_plans = [*sample_repair_plans, *split_repair_plans]

    champion_names = [
        str(result.get("cohort_id", "")) for result in results
        if bool(result.get("public_data_paper_champion", False))
    ]
    rejection_counts = Counter(reason for rejection in rejections for reason in rejection.get("rejection_reasons", []))
    sample_repair_count = sum(1 for nc in near_champions if str(nc.get("near_champion_label", "")).startswith("sample_count"))
    split_repair_count = sum(1 for nc in near_champions if str(nc.get("near_champion_label", "")).startswith("walk_forward"))
    summary = {
        "artifact_type": "public_paper_champion_gate_v2_summary",
        "public_paper_champion_gate_version": "dopey-public-paper-champion-gate-v2",
        "public_paper_champion_gate_status": "public_data_paper_champions_promoted_live_gate_locked" if champion_names else "no_public_data_paper_champion_cleared_thresholds",
        "threshold_profile": thresholds,
        "candidate_count": len(candidates),
        "public_paper_champion_count": len(champion_names),
        "champion_names": champion_names,
        "near_champion_count": len(near_champions),
        "sample_repair_candidate_count": sample_repair_count,
        "walk_forward_repair_candidate_count": split_repair_count,
        "rejection_count": len(rejections),
        "top_rejection_reasons": dict(rejection_counts.most_common(10)),
        "public_data_only": all(bool(result.get("public_data_only", False)) for result in results) if results else True,
        "fixture_champion_count": sum(1 for result in results if bool(result.get("fixture_only_champion", False))),
        "thresholds_lowered": False,
        "no_live_promotion": True,
        "live_trading_enabled": False,
        "artifact_mode": artifact_mode,
    }
    if persist and artifact_mode == "canonical":
        summary = write_summary_with_hash(SUMMARY_PATH, summary)
        write_jsonl_file(CANDIDATES_PATH, candidates)
        write_jsonl_file(RESULTS_PATH, results)
        write_jsonl_file(REJECTIONS_PATH, rejections)
        write_jsonl_file(NEAR_CHAMPIONS_PATH, near_champions)
        write_jsonl_file(SAMPLE_REPAIR_PATH, repair_plans)
        write_jsonl_file(PROOF_PATH, [proof_record("public-paper-champion-gate-v2", str(summary["public_paper_champion_gate_status"]), summary)])
    elif persist:
        from dopey_autonomy.champion_repair_common import scratch_artifact_path

        scratch_summary = scratch_artifact_path(SUMMARY_PATH, artifact_mode)
        scratch_summary.parent.mkdir(parents=True, exist_ok=True)
        write_summary_with_hash(scratch_summary, summary)
    return {**summary, "artifact_paths": artifact_paths()}


def candidate_record_v2(row: dict[str, object], thresholds: dict[str, object]) -> dict[str, object]:
    level = str(row.get("cohort_level", "variant_id"))
    return {
        "artifact_type": "public_paper_champion_gate_v2_candidate",
        "cohort_level": level,
        "cohort_id": row.get("cohort_id", ""),
        "net_pnl": row.get("net_pnl", 0.0),
        "expectancy": row.get("expectancy", 0.0),
        "profit_factor": row.get("profit_factor", 0.0),
        "sample_count": row.get("sample_count", 0),
        "symbol_count": row.get("symbol_count", 0),
        "sector_count": row.get("sector_count", 0),
        "split_pass_rate": row.get("split_pass_rate", 0.0),
        "minimum_trades_for_level": minimum_trades_for_level(level, thresholds),
        "threshold_profile_id": thresholds.get("profile_id", ""),
        "market_data_source_type": row.get("market_data_source_type", ""),
        "public_data_only": row.get("public_data_only", False),
        "fixture_trade_count": row.get("fixture_trade_count", 0),
        "live_trading_enabled": False,
    }


def champion_decision_v2(row: dict[str, object], thresholds: dict[str, object]) -> dict[str, object]:
    reasons: list[str] = []
    level = str(row.get("cohort_level", "variant_id"))
    min_trades = minimum_trades_for_level(level, thresholds)
    if not bool(row.get("public_data_only", False)):
        reasons.append("not_public_data_only")
    if int(row.get("fixture_trade_count", 0)) != 0:
        reasons.append("fixture_trades_present")
    if int(row.get("sample_count", 0)) < min_trades:
        reasons.append("sample_count_below_minimum")
    if int(row.get("symbol_count", 0)) < int(thresholds.get("minimum_symbols", 5)):
        reasons.append("symbol_count_below_minimum")
    if int(row.get("sector_count", 0)) < int(thresholds.get("minimum_sector_count", 2)):
        reasons.append("sector_count_below_minimum")
    if safe_float(row.get("split_pass_rate")) < float(thresholds.get("minimum_splits_passed_rate", 0.60)):
        reasons.append("walk_forward_split_pass_rate_below_minimum")
    if safe_float(row.get("net_pnl")) <= 0.0:
        reasons.append("net_pnl_not_positive")
    if safe_float(row.get("expectancy")) <= 0.0:
        reasons.append("expectancy_not_positive")
    if safe_float(row.get("profit_factor")) <= float(thresholds.get("minimum_profit_factor", 1.15)):
        reasons.append("profit_factor_below_minimum")
    if abs(min(safe_float(row.get("max_drawdown")), 0.0)) > float(thresholds.get("maximum_drawdown_abs", 2500.0)):
        reasons.append("max_drawdown_above_threshold")
    if safe_float(row.get("top_symbol_trade_share")) > float(thresholds.get("maximum_top_symbol_trade_share", 0.45)):
        reasons.append("single_symbol_dependence")
    if safe_float(row.get("top_regime_trade_share")) > float(thresholds.get("maximum_top_regime_trade_share", 0.70)):
        reasons.append("single_regime_dependence")
    if not stress_survived_v2(row, "high_slippage_net_pnl", thresholds):
        reasons.append("slippage_stress_not_survived")
    if not stress_survived_v2(row, "theta_stress_net_pnl", thresholds):
        reasons.append("theta_stress_not_survived")
    if not stress_survived_v2(row, "iv_shock_negative_net_pnl", thresholds):
        reasons.append("iv_shock_stress_not_survived")
    if bool(row.get("unsupported_structure", False)):
        reasons.append("unsupported_structure_present")
    champion = not reasons
    if champion:
        promotion_level = "public_paper_champion_v2"
    elif safe_float(row.get("net_pnl")) > 0.0:
        promotion_level = "public_watchlist_v2"
    else:
        promotion_level = "public_candidate_v2"
    return {
        "promotion_level": promotion_level,
        "public_data_paper_champion": champion,
        "live_gate_candidate_locked": champion,
        "fixture_only_champion": bool(row.get("fixture_trade_count", 0)) and champion,
        "rejection_reasons": reasons,
        "minimum_trades_for_level": min_trades,
        "live_trading_enabled": False,
        "no_live_promotion": True,
    }


def stress_survived_v2(row: dict[str, object], field_name: str, thresholds: dict[str, object]) -> bool:
    net = safe_float(row.get("net_pnl"))
    stress_value = safe_float(row.get(field_name))
    if net <= 0.0:
        return False
    return stress_value >= -abs(net) * float(thresholds.get("stress_loss_fraction_limit", 0.75))


def rejection_record_v2(row: dict[str, object], reasons: list[str], thresholds: dict[str, object]) -> dict[str, object]:
    return {
        "artifact_type": "public_paper_champion_gate_v2_rejection",
        "cohort_level": row.get("cohort_level", ""),
        "cohort_id": row.get("cohort_id", ""),
        "rejection_reasons": reasons,
        "threshold_profile_id": thresholds.get("profile_id", ""),
        "net_pnl": row.get("net_pnl", 0.0),
        "profit_factor": row.get("profit_factor", 0.0),
        "split_pass_rate": row.get("split_pass_rate", 0.0),
        "sample_count": row.get("sample_count", 0),
        "live_trading_enabled": False,
    }


def artifact_paths() -> dict[str, str]:
    return {
        "public_paper_champion_gate_v2_candidates": str(CANDIDATES_PATH),
        "public_paper_champion_gate_v2_results": str(RESULTS_PATH),
        "public_paper_champion_gate_v2_rejections": str(REJECTIONS_PATH),
        "public_paper_champion_gate_v2_near_champions": str(NEAR_CHAMPIONS_PATH),
        "public_paper_champion_gate_v2_sample_repair_plan": str(SAMPLE_REPAIR_PATH),
        "public_paper_champion_gate_v2_summary": str(SUMMARY_PATH),
        "public_paper_champion_gate_v2_proof": str(PROOF_PATH),
    }
