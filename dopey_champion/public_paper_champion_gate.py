"""Gate durable public-data paper champions."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import (
    CHAMPION_ROOT,
    load_public_leaderboard,
    proof_record,
    record_with_hash,
    safe_float,
    write_jsonl_file,
    write_summary_with_hash,
)

from .public_champion_models import ChampionThresholdProfile, champion_threshold_profile_v1


CANDIDATES_PATH = CHAMPION_ROOT / "public_paper_champion_candidates.jsonl"
RESULTS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_results.jsonl"
REJECTIONS_PATH = CHAMPION_ROOT / "public_paper_champion_rejections.jsonl"
SUMMARY_PATH = CHAMPION_ROOT / "public_paper_champion_gate_summary.json"
PROOF_PATH = CHAMPION_ROOT / "public_paper_champion_gate_proof.jsonl"


def run_public_paper_champion_gate() -> dict[str, object]:
    leaderboard = load_public_leaderboard()
    return evaluate_public_paper_champions(leaderboard, champion_threshold_profile_v1())


def evaluate_public_paper_champions(
    leaderboard: list[dict[str, object]],
    thresholds: ChampionThresholdProfile,
) -> dict[str, object]:
    candidates = [record_with_hash(candidate_record(row, thresholds), "record_hash") for row in leaderboard]
    results: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    for row in leaderboard:
        decision = champion_decision(row, thresholds)
        result = record_with_hash({**row, **decision, "threshold_profile": thresholds}, "record_hash")
        results.append(result)
        if decision["rejection_reasons"]:
            rejections.append(record_with_hash(rejection_record(row, decision["rejection_reasons"], thresholds), "record_hash"))
    champion_names = [str(result["strategy_id"]) for result in results if bool(result.get("public_data_paper_champion", False))]
    rejection_counts = Counter(reason for rejection in rejections for reason in rejection.get("rejection_reasons", []))
    summary = {
        "artifact_type": "public_paper_champion_gate_summary",
        "public_paper_champion_gate_version": "dopey-public-paper-champion-gate-v1",
        "public_paper_champion_gate_status": "public_data_paper_champions_promoted_live_gate_locked" if champion_names else "no_public_data_paper_champion_cleared_thresholds",
        "threshold_profile": thresholds,
        "candidate_count": len(candidates),
        "public_paper_champion_count": len(champion_names),
        "live_gate_candidate_locked_count": sum(1 for result in results if bool(result.get("live_gate_candidate_locked", False))),
        "rejection_count": len(rejections),
        "top_rejection_reasons": dict(rejection_counts.most_common(8)),
        "champion_names": champion_names,
        "public_data_only": all(bool(result.get("public_data_only", False)) for result in results) if results else True,
        "fixture_champion_count": sum(1 for result in results if bool(result.get("fixture_only_champion", False))),
        "thresholds_lowered": False,
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(CANDIDATES_PATH, candidates)
    write_jsonl_file(RESULTS_PATH, results)
    write_jsonl_file(REJECTIONS_PATH, rejections)
    write_jsonl_file(PROOF_PATH, [proof_record("public-paper-champion-gate", str(summary["public_paper_champion_gate_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def candidate_record(row: dict[str, object], thresholds: ChampionThresholdProfile) -> dict[str, object]:
    return {
        "artifact_type": "public_paper_champion_candidate",
        "strategy_id": row.get("strategy_id", ""),
        "setup_family": row.get("setup_family", ""),
        "net_pnl": row.get("net_pnl", 0.0),
        "expectancy": row.get("expectancy", 0.0),
        "profit_factor": row.get("profit_factor", 0.0),
        "sample_count": row.get("sample_count", 0),
        "symbol_count": row.get("symbol_count", 0),
        "split_pass_rate": row.get("split_pass_rate", 0.0),
        "threshold_profile_id": thresholds["profile_id"],
        "market_data_source_type": row.get("market_data_source_type", ""),
        "public_data_only": row.get("public_data_only", False),
        "fixture_trade_count": row.get("fixture_trade_count", 0),
        "live_trading_enabled": False,
    }


def champion_decision(row: dict[str, object], thresholds: ChampionThresholdProfile) -> dict[str, object]:
    reasons: list[str] = []
    if not bool(row.get("public_data_only", False)):
        reasons.append("not_public_data_only")
    if int(row.get("fixture_trade_count", 0)) != 0:
        reasons.append("fixture_trades_present")
    if int(row.get("sample_count", 0)) < thresholds["minimum_trades"]:
        reasons.append("sample_count_below_minimum")
    if int(row.get("symbol_count", 0)) < thresholds["minimum_symbols"]:
        reasons.append("symbol_count_below_minimum")
    if safe_float(row.get("split_pass_rate")) < thresholds["minimum_splits_passed_rate"]:
        reasons.append("walk_forward_split_pass_rate_below_minimum")
    if safe_float(row.get("net_pnl")) <= 0.0:
        reasons.append("net_pnl_not_positive")
    if safe_float(row.get("expectancy")) <= 0.0:
        reasons.append("expectancy_not_positive")
    if safe_float(row.get("profit_factor")) <= thresholds["minimum_profit_factor"]:
        reasons.append("profit_factor_below_minimum")
    if abs(min(safe_float(row.get("max_drawdown")), 0.0)) > thresholds["maximum_drawdown_abs"]:
        reasons.append("max_drawdown_above_threshold")
    if safe_float(row.get("top_symbol_trade_share")) > thresholds["maximum_top_symbol_trade_share"]:
        reasons.append("single_symbol_dependence")
    if safe_float(row.get("top_regime_trade_share")) > thresholds["maximum_top_regime_trade_share"]:
        reasons.append("single_regime_dependence")
    if safe_float(row.get("worst_trade")) < -thresholds["maximum_drawdown_abs"] * 0.35:
        reasons.append("catastrophic_loss_tail")
    if not stress_survived(row, "high_slippage_net_pnl", thresholds):
        reasons.append("slippage_stress_not_survived")
    if not stress_survived(row, "theta_stress_net_pnl", thresholds):
        reasons.append("theta_stress_not_survived")
    if not stress_survived(row, "iv_shock_negative_net_pnl", thresholds):
        reasons.append("iv_shock_stress_not_survived")
    if bool(row.get("unsupported_structure", False)):
        reasons.append("unsupported_structure_present")
    champion = not reasons
    if champion:
        promotion_level = "public_paper_champion"
    elif not reasons or safe_float(row.get("net_pnl")) > 0.0:
        promotion_level = "public_watchlist"
    else:
        promotion_level = "public_candidate"
    return {
        "promotion_level": promotion_level,
        "public_data_paper_champion": champion,
        "live_gate_candidate_locked": champion,
        "fixture_only_champion": bool(row.get("fixture_trade_count", 0)) and champion,
        "rejection_reasons": reasons,
        "live_trading_enabled": False,
        "no_live_promotion": True,
    }


def stress_survived(row: dict[str, object], field_name: str, thresholds: ChampionThresholdProfile) -> bool:
    net = safe_float(row.get("net_pnl"))
    stress_value = safe_float(row.get(field_name))
    if net <= 0.0:
        return False
    return stress_value >= -abs(net) * thresholds["stress_loss_fraction_limit"]


def rejection_record(row: dict[str, object], reasons: list[str], thresholds: ChampionThresholdProfile) -> dict[str, object]:
    return {
        "artifact_type": "public_paper_champion_rejection",
        "strategy_id": row.get("strategy_id", ""),
        "setup_family": row.get("setup_family", ""),
        "rejection_reasons": reasons,
        "threshold_profile_id": thresholds["profile_id"],
        "net_pnl": row.get("net_pnl", 0.0),
        "profit_factor": row.get("profit_factor", 0.0),
        "split_pass_rate": row.get("split_pass_rate", 0.0),
        "live_trading_enabled": False,
    }


def artifact_paths() -> dict[str, str]:
    return {
        "public_paper_champion_candidates": str(CANDIDATES_PATH),
        "public_paper_champion_gate_results": str(RESULTS_PATH),
        "public_paper_champion_rejections": str(REJECTIONS_PATH),
        "public_paper_champion_gate_summary": str(SUMMARY_PATH),
        "public_paper_champion_gate_proof": str(PROOF_PATH),
    }

