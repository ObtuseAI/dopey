"""Cohort walk-forward tournament V4.

Scores trades at every cohort level (variant, micro, setup, family, regime,
symbol-cluster, canonical-champion) with walk-forward splits, holdouts, regime
survival, child-variant dispersion, stress survival, and a durability score.
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import (
    OPTIONS_ENGINE_ROOT,
    TOURNAMENT_ROOT,
    date_from_text,
    group_records,
    pnl_metrics,
    proof_record,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    write_jsonl_file,
    write_summary_with_hash,
)

from dopey_strategy_cohorts.strategy_cohort_models import COHORT_LEVELS

from .public_cohort_holdout_tournament_v4 import build_public_cohort_holdout_scores_v4, score_cohort_split
from .public_cohort_regime_tournament_v4 import build_public_cohort_regime_scores_v4, regime_survival_for


TRADES_PATH = TOURNAMENT_ROOT / "public_cohort_walk_forward_trades_v4.jsonl"
STRATEGY_SCORES_PATH = TOURNAMENT_ROOT / "public_cohort_strategy_scores_v4.jsonl"
HOLDOUT_SCORES_PATH = TOURNAMENT_ROOT / "public_cohort_holdout_scores_v4.jsonl"
REGIME_SCORES_PATH = TOURNAMENT_ROOT / "public_cohort_regime_scores_v4.jsonl"
SYMBOL_HOLDOUT_SCORES_PATH = TOURNAMENT_ROOT / "public_cohort_symbol_holdout_scores_v4.jsonl"
LEADERBOARD_PATH = TOURNAMENT_ROOT / "public_cohort_tournament_leaderboard_v4.jsonl"
SUMMARY_PATH = TOURNAMENT_ROOT / "public_cohort_walk_forward_tournament_v4_summary.json"
PROOF_PATH = TOURNAMENT_ROOT / "public_cohort_walk_forward_tournament_v4_proof.jsonl"

TRADES_INPUT_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_trades.jsonl"


def run_public_cohort_walk_forward_tournament_v4() -> dict[str, object]:
    trades = read_jsonl_file(TRADES_INPUT_PATH)
    return score_public_cohort_walk_forward_tournament_v4(trades, artifact_mode="canonical", persist=True)


def score_public_cohort_walk_forward_tournament_v4(
    trades: list[dict[str, object]],
    *,
    artifact_mode: str = "test",
    persist: bool = True,
) -> dict[str, object]:
    public_trades = [t for t in trades if str(t.get("market_data_source_type", "")).startswith("public")]
    executable = [t for t in public_trades if str(t.get("trade_intent", "")) in {"long_call", "long_put"}]

    walk_forward_scores = build_cohort_walk_forward_scores(executable)
    holdout_scores, symbol_holdout_scores = build_public_cohort_holdout_scores_v4(public_trades)
    regime_scores = build_public_cohort_regime_scores_v4(public_trades)
    leaderboard = build_cohort_leaderboard(executable, walk_forward_scores, holdout_scores, regime_scores)

    top = leaderboard[0] if leaderboard else {}
    cohort_counts = {level: len(group_records(executable, level)) for level in COHORT_LEVELS}
    summary = {
        "artifact_type": "public_cohort_walk_forward_tournament_v4_summary",
        "public_cohort_walk_forward_version": "dopey-public-cohort-walk-forward-tournament-v4",
        "public_cohort_walk_forward_status": "public_cohort_walk_forward_complete" if leaderboard else "blocked_no_public_path_trades",
        "candidate_count": len(public_trades),
        "trade_count": len(executable),
        "cohort_counts": cohort_counts,
        "strategy_count": len(group_records(executable, "variant_id")),
        "split_count": len(walk_forward_scores) + len(holdout_scores) + len(regime_scores),
        "leaderboard_count": len(leaderboard),
        "positive_cohort_count": sum(1 for r in leaderboard if safe_float(r.get("net_pnl")) > 0.0),
        "candidate_champion_count": sum(1 for r in leaderboard if is_candidate_champion(r)),
        "top_strategy": top.get("cohort_id", ""),
        "top_cohort_level": top.get("cohort_level", ""),
        "top_net_pnl": top.get("net_pnl", 0.0),
        "top_profit_factor": top.get("profit_factor", 0.0),
        "top_max_drawdown": top.get("max_drawdown", 0.0),
        "top_sample_count": top.get("sample_count", 0),
        "top_split_pass_rate": top.get("split_pass_rate", 0.0),
        "fixture_trade_count": sum(1 for t in public_trades if str(t.get("market_data_source_type", "")) == "fixture_fallback"),
        "public_data_only": all(str(t.get("market_data_source_type", "")).startswith("public") for t in public_trades),
        "live_trading_enabled": False,
        "artifact_mode": artifact_mode,
    }
    if persist and artifact_mode == "canonical":
        summary = write_summary_with_hash(SUMMARY_PATH, summary)
        write_jsonl_file(TRADES_PATH, public_trades)
        write_jsonl_file(STRATEGY_SCORES_PATH, walk_forward_scores)
        write_jsonl_file(HOLDOUT_SCORES_PATH, holdout_scores)
        write_jsonl_file(REGIME_SCORES_PATH, regime_scores)
        write_jsonl_file(SYMBOL_HOLDOUT_SCORES_PATH, symbol_holdout_scores)
        write_jsonl_file(LEADERBOARD_PATH, leaderboard)
        write_jsonl_file(PROOF_PATH, [proof_record("public-cohort-walk-forward-tournament-v4", str(summary["public_cohort_walk_forward_status"]), summary)])
    elif persist:
        from dopey_autonomy.champion_repair_common import scratch_artifact_path

        scratch_summary = scratch_artifact_path(SUMMARY_PATH, artifact_mode)
        scratch_summary.parent.mkdir(parents=True, exist_ok=True)
        write_summary_with_hash(scratch_summary, summary)
    return {**summary, "artifact_paths": artifact_paths()}


def build_cohort_walk_forward_scores(trades: list[dict[str, object]]) -> list[dict[str, object]]:
    date_values = sorted({date_from_text(t.get("entry_date")) for t in trades})
    bucket_dates = quantile_bucket_dates(date_values, 5)
    scores: list[dict[str, object]] = []
    for level in COHORT_LEVELS:
        groups = group_records(trades, level)
        for cohort_id, records in groups.items():
            for bucket_index, bucket in enumerate(bucket_dates):
                bucket_records = [r for r in records if bucket[0] <= date_from_text(r.get("entry_date")) <= bucket[1]]
                score = score_cohort_split(cohort_id, level, bucket_records, f"{level}_rolling_walk_forward_{bucket_index + 1}", "rolling_walk_forward")
                score["artifact_type"] = "public_cohort_strategy_score_v4"
                scores.append(record_with_hash(score, "record_hash"))
            for bucket_index, bucket in enumerate(bucket_dates):
                expanding_records = [r for r in records if date_from_text(r.get("entry_date")) <= bucket[1]]
                score = score_cohort_split(cohort_id, level, expanding_records, f"{level}_expanding_window_{bucket_index + 1}", "expanding_window_walk_forward")
                score["artifact_type"] = "public_cohort_strategy_score_v4"
                scores.append(record_with_hash(score, "record_hash"))
    return scores


def quantile_bucket_dates(date_values: list, bucket_count: int) -> list[tuple[object, object]]:
    if not date_values:
        return []
    buckets: list[tuple[object, object]] = []
    for index in range(bucket_count):
        start_index = int(index * len(date_values) / bucket_count)
        end_index = int(((index + 1) * len(date_values) / bucket_count) - 1)
        buckets.append((date_values[start_index], date_values[max(start_index, min(end_index, len(date_values) - 1))]))
    return buckets


def build_cohort_leaderboard(
    trades: list[dict[str, object]],
    walk_forward_scores: list[dict[str, object]],
    holdout_scores: list[dict[str, object]],
    regime_scores: list[dict[str, object]],
) -> list[dict[str, object]]:
    all_splits = [*walk_forward_scores, *holdout_scores, *regime_scores]
    splits_by_cohort: dict[str, list[dict[str, object]]] = {}
    for score in all_splits:
        key = f"{score.get('cohort_level', '')}::{score.get('cohort_id', '')}"
        splits_by_cohort.setdefault(key, []).append(score)

    leaderboard: list[dict[str, object]] = []
    for level in COHORT_LEVELS:
        for cohort_id, records in group_records(trades, level).items():
            metrics = pnl_metrics(records)
            key = f"{level}::{cohort_id}"
            split_records = splits_by_cohort.get(key, [])
            passed_count = sum(1 for s in split_records if bool(s.get("split_passed", False)))
            split_count = len(split_records)
            split_pass_rate = round(passed_count / split_count, 6) if split_count else 0.0
            stress = stress_metrics(records)
            dispersion = child_variant_dispersion(records, level)
            regime_survival = regime_survival_for(records)
            max_dd = safe_float(metrics["max_drawdown"])
            drawdown_adjusted_pnl = round(safe_float(metrics["net_pnl"]) + max_dd, 6)
            stress_survival = stress_survival_flag(stress)
            durability = durability_score_for(metrics, split_pass_rate, split_count, stress, dispersion)
            row = {
                "artifact_type": "public_cohort_tournament_leaderboard_v4",
                "cohort_level": level,
                "cohort_id": cohort_id,
                **metrics,
                "drawdown_adjusted_pnl": drawdown_adjusted_pnl,
                "split_count": split_count,
                "splits_passed": passed_count,
                "split_pass_rate": split_pass_rate,
                "child_variant_dispersion": dispersion,
                "stress_survival": stress_survival,
                "regime_survival": regime_survival,
                "durability_score": durability,
                **stress,
                "market_data_source_type": "public_live_fetch",
                "public_data_only": all(str(r.get("market_data_source_type", "")).startswith("public") for r in records),
                "fixture_trade_count": sum(1 for r in records if str(r.get("market_data_source_type", "")) == "fixture_fallback"),
                "live_trading_enabled": False,
            }
            leaderboard.append(record_with_hash(row, "record_hash"))
    return sorted(leaderboard, key=lambda item: (safe_float(item["durability_score"]), safe_float(item["net_pnl"])), reverse=True)


def stress_metrics(records: list[dict[str, object]]) -> dict[str, object]:
    slippage_groups = group_records(records, "slippage_stress")
    iv_groups = group_records(records, "iv_proxy_regime")
    low_dte_records = [r for r in records if int(r.get("dte_bucket", 999)) <= 7]
    return {
        "low_slippage_net_pnl": round(sum(safe_float(r.get("paper_pnl")) for r in slippage_groups.get("low", [])), 6),
        "normal_slippage_net_pnl": round(sum(safe_float(r.get("paper_pnl")) for r in slippage_groups.get("normal", [])), 6),
        "high_slippage_net_pnl": round(sum(safe_float(r.get("paper_pnl")) for r in slippage_groups.get("high", [])), 6),
        "theta_stress_net_pnl": round(sum(safe_float(r.get("paper_pnl")) for r in low_dte_records), 6),
        "iv_shock_negative_net_pnl": round(sum(safe_float(r.get("paper_pnl")) for r in iv_groups.get("realized_vol_minus_10pct", [])), 6),
        "iv_shock_positive_net_pnl": round(sum(safe_float(r.get("paper_pnl")) for r in iv_groups.get("realized_vol_plus_25pct", [])), 6),
    }


def stress_survival_flag(stress: dict[str, object]) -> bool:
    return bool(
        safe_float(stress["high_slippage_net_pnl"]) >= 0.0
        or safe_float(stress["iv_shock_positive_net_pnl"]) >= 0.0
    )


def child_variant_dispersion(records: list[dict[str, object]], level: str) -> dict[str, object]:
    if level == "variant_id":
        return {"sample_count": len(records), "unique_variants": 1, "unique_symbols": len({str(r.get("symbol", "")) for r in records})}
    variants = {str(r.get("variant_id", r.get("strategy_id", ""))) for r in records}
    symbols = {str(r.get("symbol", "")) for r in records}
    return {
        "sample_count": len(records),
        "unique_variants": len(variants),
        "unique_symbols": len(symbols),
    }


def durability_score_for(metrics: dict[str, object], split_pass_rate: float, split_count: int, stress: dict[str, object], dispersion: dict[str, object]) -> float:
    concentration_penalty = safe_float(metrics["top_symbol_trade_share"]) * 4.0 + safe_float(metrics["top_regime_trade_share"]) * 2.0
    drawdown_penalty = abs(min(safe_float(metrics["max_drawdown"]), 0.0)) * 0.03
    stress_penalty = 0.0
    if safe_float(stress["high_slippage_net_pnl"]) < 0.0:
        stress_penalty += abs(safe_float(stress["high_slippage_net_pnl"])) * 0.02
    dispersion_bonus = min(safe_float(dispersion.get("unique_variants", 0)) * 0.5, 8.0)
    split_bonus = min(split_count * 0.4, 12.0)
    return round(
        safe_float(metrics["net_pnl"]) * 0.05
        + safe_float(metrics["expectancy"]) * 8.0
        + split_pass_rate * 40.0
        + split_bonus
        + dispersion_bonus
        - concentration_penalty
        - drawdown_penalty
        - stress_penalty,
        6,
    )


def is_candidate_champion(record: dict[str, object]) -> bool:
    return bool(
        safe_float(record.get("net_pnl")) > 0.0
        and safe_float(record.get("expectancy")) > 0.0
        and safe_float(record.get("profit_factor")) > 1.05
        and int(record.get("sample_count", 0)) >= 20
        and safe_float(record.get("split_pass_rate")) >= 0.50
    )


def artifact_paths() -> dict[str, str]:
    return {
        "public_cohort_walk_forward_trades_v4": str(TRADES_PATH),
        "public_cohort_strategy_scores_v4": str(STRATEGY_SCORES_PATH),
        "public_cohort_holdout_scores_v4": str(HOLDOUT_SCORES_PATH),
        "public_cohort_regime_scores_v4": str(REGIME_SCORES_PATH),
        "public_cohort_symbol_holdout_scores_v4": str(SYMBOL_HOLDOUT_SCORES_PATH),
        "public_cohort_tournament_leaderboard_v4": str(LEADERBOARD_PATH),
        "public_cohort_walk_forward_tournament_v4_summary": str(SUMMARY_PATH),
        "public_cohort_walk_forward_tournament_v4_proof": str(PROOF_PATH),
    }
