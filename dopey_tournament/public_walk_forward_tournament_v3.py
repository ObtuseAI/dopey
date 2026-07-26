"""Walk-forward public tournament V3."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import (
    TOURNAMENT_ROOT,
    date_from_text,
    group_records,
    load_public_champion_trades,
    pnl_metrics,
    proof_record,
    record_with_hash,
    safe_float,
    write_jsonl_file,
    write_summary_with_hash,
)

from .public_holdout_tournament_v3 import build_public_holdout_scores_v3, score_split
from .public_regime_tournament_v3 import build_public_regime_scores_v3


TRADES_PATH = TOURNAMENT_ROOT / "public_walk_forward_trades_v3.jsonl"
STRATEGY_SCORES_PATH = TOURNAMENT_ROOT / "public_walk_forward_strategy_scores_v3.jsonl"
HOLDOUT_SCORES_PATH = TOURNAMENT_ROOT / "public_holdout_scores_v3.jsonl"
REGIME_SCORES_PATH = TOURNAMENT_ROOT / "public_regime_scores_v3.jsonl"
SYMBOL_HOLDOUT_SCORES_PATH = TOURNAMENT_ROOT / "public_symbol_holdout_scores_v3.jsonl"
LEADERBOARD_PATH = TOURNAMENT_ROOT / "public_tournament_leaderboard_v3.jsonl"
SUMMARY_PATH = TOURNAMENT_ROOT / "public_walk_forward_tournament_v3_summary.json"
PROOF_PATH = TOURNAMENT_ROOT / "public_walk_forward_tournament_v3_proof.jsonl"


def run_public_walk_forward_tournament_v3() -> dict[str, object]:
    trades = load_public_champion_trades()
    return score_public_walk_forward_tournament_v3(trades)


def score_public_walk_forward_tournament_v3(trades: list[dict[str, object]]) -> dict[str, object]:
    public_trades = [
        trade for trade in trades
        if str(trade.get("market_data_source_type", "")).startswith("public")
    ]
    executable = [trade for trade in public_trades if str(trade.get("trade_intent", "")) in {"long_call", "long_put"}]
    walk_forward_scores = build_walk_forward_scores(executable)
    holdout_scores, symbol_holdout_scores = build_public_holdout_scores_v3(public_trades)
    regime_scores = build_public_regime_scores_v3(public_trades)
    leaderboard = build_leaderboard(executable, walk_forward_scores, holdout_scores, regime_scores)
    strategy_scores = [record for record in leaderboard]
    top = leaderboard[0] if leaderboard else {}
    summary = {
        "artifact_type": "public_walk_forward_tournament_v3_summary",
        "public_walk_forward_version": "dopey-public-walk-forward-tournament-v3",
        "public_walk_forward_status": "public_walk_forward_complete" if leaderboard else "blocked_no_public_path_trades",
        "candidate_count": len(public_trades),
        "trade_count": len(executable),
        "strategy_count": len(leaderboard),
        "split_count": len(walk_forward_scores) + len(holdout_scores) + len(regime_scores),
        "positive_strategy_count": sum(1 for record in leaderboard if safe_float(record.get("net_pnl")) > 0.0),
        "candidate_champion_count": sum(1 for record in leaderboard if is_candidate_champion(record)),
        "top_strategy": top.get("strategy_id", ""),
        "top_strategy_net_pnl": top.get("net_pnl", 0.0),
        "top_strategy_profit_factor": top.get("profit_factor", 0.0),
        "top_strategy_max_drawdown": top.get("max_drawdown", 0.0),
        "top_strategy_sample_count": top.get("sample_count", 0),
        "fixture_trade_count": sum(1 for trade in public_trades if str(trade.get("market_data_source_type", "")) == "fixture_fallback"),
        "public_data_only": all(str(trade.get("market_data_source_type", "")).startswith("public") for trade in public_trades),
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(TRADES_PATH, public_trades)
    write_jsonl_file(STRATEGY_SCORES_PATH, strategy_scores)
    write_jsonl_file(HOLDOUT_SCORES_PATH, holdout_scores)
    write_jsonl_file(REGIME_SCORES_PATH, regime_scores)
    write_jsonl_file(SYMBOL_HOLDOUT_SCORES_PATH, symbol_holdout_scores)
    write_jsonl_file(LEADERBOARD_PATH, leaderboard)
    write_jsonl_file(PROOF_PATH, [proof_record("public-walk-forward-tournament-v3", str(summary["public_walk_forward_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def build_walk_forward_scores(trades: list[dict[str, object]]) -> list[dict[str, object]]:
    strategy_groups = group_records(trades, "strategy_id")
    date_values = sorted({date_from_text(trade.get("entry_date")) for trade in trades})
    if not date_values:
        return []
    bucket_dates = quantile_bucket_dates(date_values, 5)
    scores: list[dict[str, object]] = []
    for strategy_id, records in strategy_groups.items():
        for bucket_index, bucket in enumerate(bucket_dates):
            bucket_records = [record for record in records if bucket[0] <= date_from_text(record.get("entry_date")) <= bucket[1]]
            score = score_split(strategy_id, bucket_records, f"rolling_walk_forward_{bucket_index + 1}", "rolling_walk_forward")
            score["artifact_type"] = "public_walk_forward_strategy_score_v3"
            scores.append(record_with_hash(score, "record_hash"))
        for bucket_index, bucket in enumerate(bucket_dates):
            expanding_records = [record for record in records if date_from_text(record.get("entry_date")) <= bucket[1]]
            score = score_split(strategy_id, expanding_records, f"expanding_window_{bucket_index + 1}", "expanding_window_walk_forward")
            score["artifact_type"] = "public_walk_forward_strategy_score_v3"
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


def build_leaderboard(
    trades: list[dict[str, object]],
    walk_forward_scores: list[dict[str, object]],
    holdout_scores: list[dict[str, object]],
    regime_scores: list[dict[str, object]],
) -> list[dict[str, object]]:
    scores_by_strategy = group_records([*walk_forward_scores, *holdout_scores, *regime_scores], "strategy_id")
    leaderboard: list[dict[str, object]] = []
    for strategy_id, records in group_records(trades, "strategy_id").items():
        metrics = pnl_metrics(records)
        split_records = scores_by_strategy.get(strategy_id, [])
        passed_count = sum(1 for score in split_records if bool(score.get("split_passed", False)))
        split_count = len(split_records)
        stress = stress_metrics(records)
        durability_score = durability_score_for(metrics, split_count, passed_count, stress)
        setup_family = most_common_value(records, "setup_family")
        row = {
            "artifact_type": "public_tournament_leaderboard_v3",
            "strategy_id": strategy_id,
            "setup_family": setup_family,
            **metrics,
            "split_count": split_count,
            "splits_passed": passed_count,
            "split_pass_rate": round(passed_count / split_count, 6) if split_count else 0.0,
            "durability_score": durability_score,
            **stress,
            "market_data_source_type": "public_live_fetch",
            "public_data_only": all(str(record.get("market_data_source_type", "")).startswith("public") for record in records),
            "fixture_trade_count": sum(1 for record in records if str(record.get("market_data_source_type", "")) == "fixture_fallback"),
            "live_trading_enabled": False,
        }
        leaderboard.append(record_with_hash(row, "record_hash"))
    return sorted(leaderboard, key=lambda item: (safe_float(item["durability_score"]), safe_float(item["net_pnl"])), reverse=True)


def stress_metrics(records: list[dict[str, object]]) -> dict[str, object]:
    slippage_groups = group_records(records, "slippage_stress")
    iv_groups = group_records(records, "iv_proxy_regime")
    low_dte_records = [record for record in records if int(record.get("dte_bucket", 999)) <= 7]
    return {
        "low_slippage_net_pnl": round(sum(safe_float(record.get("paper_pnl")) for record in slippage_groups.get("low", [])), 6),
        "normal_slippage_net_pnl": round(sum(safe_float(record.get("paper_pnl")) for record in slippage_groups.get("normal", [])), 6),
        "high_slippage_net_pnl": round(sum(safe_float(record.get("paper_pnl")) for record in slippage_groups.get("high", [])), 6),
        "theta_stress_net_pnl": round(sum(safe_float(record.get("paper_pnl")) for record in low_dte_records), 6),
        "iv_shock_negative_net_pnl": round(sum(safe_float(record.get("paper_pnl")) for record in iv_groups.get("realized_vol_minus_10pct", [])), 6),
        "iv_shock_positive_net_pnl": round(sum(safe_float(record.get("paper_pnl")) for record in iv_groups.get("realized_vol_plus_25pct", [])), 6),
    }


def durability_score_for(metrics: dict[str, object], split_count: int, passed_count: int, stress: dict[str, object]) -> float:
    pass_rate = passed_count / split_count if split_count else 0.0
    concentration_penalty = safe_float(metrics["top_symbol_trade_share"]) * 4.0 + safe_float(metrics["top_regime_trade_share"]) * 2.0
    drawdown_penalty = abs(min(safe_float(metrics["max_drawdown"]), 0.0)) * 0.03
    stress_penalty = 0.0
    if safe_float(stress["high_slippage_net_pnl"]) < 0.0:
        stress_penalty += abs(safe_float(stress["high_slippage_net_pnl"])) * 0.02
    return round(safe_float(metrics["net_pnl"]) * 0.05 + safe_float(metrics["expectancy"]) * 8.0 + pass_rate * 40.0 - concentration_penalty - drawdown_penalty - stress_penalty, 6)


def is_candidate_champion(record: dict[str, object]) -> bool:
    return bool(
        safe_float(record.get("net_pnl")) > 0.0
        and safe_float(record.get("expectancy")) > 0.0
        and safe_float(record.get("profit_factor")) > 1.05
        and int(record.get("sample_count", 0)) >= 20
        and safe_float(record.get("split_pass_rate")) >= 0.50
    )


def most_common_value(records: list[dict[str, object]], field_name: str) -> str:
    counts = Counter(str(record.get(field_name, "")) for record in records)
    return counts.most_common(1)[0][0] if counts else ""


def artifact_paths() -> dict[str, str]:
    return {
        "public_walk_forward_trades_v3": str(TRADES_PATH),
        "public_walk_forward_strategy_scores_v3": str(STRATEGY_SCORES_PATH),
        "public_holdout_scores_v3": str(HOLDOUT_SCORES_PATH),
        "public_regime_scores_v3": str(REGIME_SCORES_PATH),
        "public_symbol_holdout_scores_v3": str(SYMBOL_HOLDOUT_SCORES_PATH),
        "public_tournament_leaderboard_v3": str(LEADERBOARD_PATH),
        "public_walk_forward_tournament_v3_summary": str(SUMMARY_PATH),
        "public_walk_forward_tournament_v3_proof": str(PROOF_PATH),
    }

