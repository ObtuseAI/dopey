"""Research tournament V4 with V3 comparison and subfamily grouping.

Mirrors V3 tournament but groups by both `stable_family_id` and
`stable_subfamily_id` so that V3's collapsed single cohort is replaced
by a separated continuation / volume tournament. Adds UVXY-like
corruption check and V3/V4 comparison rows.
"""
from __future__ import annotations

from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, stress_metrics
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_autonomy.signal_research_v4_common import (
    RESEARCH_V4_ROOT,
    TOURNAMENT_COMPARISON_V4_PATH,
    TOURNAMENT_HOLDOUT_V4_PATH,
    TOURNAMENT_LEADERBOARD_V4_PATH,
    TOURNAMENT_PROOF_PATH,
    TOURNAMENT_REGIME_V4_PATH,
    TOURNAMENT_SCORES_V4_PATH,
    TOURNAMENT_SUMMARY_PATH,
    TRADES_V4_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_signal_research.research_coverage_penalty_v2 import coverage_penalty
from dopey_signal_research.research_holdout_v4 import holdout_split_pass_rate, holdout_survival
from dopey_signal_research.research_regime_score_v4 import regime_scores
from dopey_signal_research.research_v3_v4_comparison_v4 import compare_v3_v4


def run_research_tournament_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    trades = read_jsonl_file(TRADES_V4_PATH)

    by_subfamily: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        subfamily_id = str(
            trade.get("stable_subfamily_id")
            or trade.get("discovery_subfamily_id")
            or trade.get("stable_family_id")
            or trade.get("discovery_family_id")
            or "unknown"
        )
        by_subfamily[subfamily_id].append(trade)

    score_rows: list[dict[str, object]] = []
    leaderboard: list[dict[str, object]] = []
    holdout_rows: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    positive_subfamilies = 0
    pf_above_threshold = 0
    improved_vs_v3 = 0
    breakthrough_candidate_count = 0

    # UVXY-like corruption heuristic: any single symbol contributing
    # more than 50% of the total net PnL across the tournament.
    symbol_pnl: dict[str, float] = defaultdict(float)
    for trade in trades:
        sym = str(trade.get("symbol", "unknown"))
        symbol_pnl[sym] += safe_float(trade.get("paper_pnl", 0.0))
    total_pnl_all = sum(max(0.0, v) for v in symbol_pnl.values())
    corruption_detected = False
    if total_pnl_all > 0.0:
        max_sym, max_pnl = max(symbol_pnl.items(), key=lambda kv: kv[1])
        if max_pnl / total_pnl_all > 0.5:
            corruption_detected = True

    for subfamily_id, subfamily_trades in by_subfamily.items():
        family_id = str(subfamily_trades[0].get("stable_family_id", ""))
        metrics = stress_metrics(subfamily_trades)
        split_pass = holdout_split_pass_rate(subfamily_trades)
        holdout_flag = holdout_survival(subfamily_trades)
        coverage_row = {**metrics, "family_id": subfamily_id}
        coverage_score, penalties = coverage_penalty(coverage_row)
        adjusted_pnl = safe_float(metrics.get("net_pnl", 0.0)) * coverage_score
        profit_factor = safe_float(metrics.get("profit_factor", 0.0))
        if safe_float(metrics.get("net_pnl", 0.0)) > 0.0:
            positive_subfamilies += 1
        if profit_factor > 1.10:
            pf_above_threshold += 1
        if (
            adjusted_pnl > 0.0
            and profit_factor > 1.10
            and holdout_flag
            and not penalties
        ):
            breakthrough_candidate_count += 1
        row = record_with_hash(
            {
                "artifact_type": "research_tournament_score_v4",
                "stable_subfamily_id": subfamily_id,
                "stable_family_id": family_id,
                "family_id": subfamily_id,
                "discovery_subfamily_id": subfamily_id,
                "sample_count": metrics.get("sample_count", 0),
                "symbol_count": metrics.get("symbol_count", 0),
                "sector_count": metrics.get("sector_count", 0),
                "year_count": metrics.get("year_count", 0),
                "net_pnl": metrics.get("net_pnl", 0.0),
                "adjusted_net_pnl": round(adjusted_pnl, 6),
                "expectancy": metrics.get("expectancy", 0.0),
                "profit_factor": profit_factor,
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "split_pass_rate": split_pass,
                "holdout_survival": holdout_flag,
                "coverage_score": coverage_score,
                "coverage_penalties": penalties,
                **live_safety_fields(),
            },
            "record_hash",
        )
        score_rows.append(row)
        leaderboard.append(row)
        holdout_rows.append(
            record_with_hash(
                {
                    "artifact_type": "research_tournament_holdout_score_v4",
                    "stable_subfamily_id": subfamily_id,
                    "holdout_survival": holdout_flag,
                    "split_pass_rate": split_pass,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )
        comparison = compare_v3_v4(row)
        comparison_rows.append(comparison)
        if comparison.get("improved_vs_v3"):
            improved_vs_v3 += 1

    leaderboard.sort(key=lambda row: safe_float(row.get("adjusted_net_pnl", 0.0)), reverse=True)
    top = leaderboard[0] if leaderboard else {}
    regime_rows = regime_scores(trades)
    family_ids = {str(t.get("stable_family_id", "")) for t in trades}
    subfamily_ids = {str(t.get("stable_subfamily_id", "")) for t in trades}
    cohort_ids = {str(t.get("cohort_id", "")) for t in trades}

    summary = {
        "artifact_type": "research_tournament_v4_summary",
        "research_tournament_v4_version": "dopey-public-research-tournament-v4",
        "research_tournament_v4_status": "research_tournament_complete_v4",
        "trade_count": len(trades),
        "family_count": len([f for f in family_ids if f]),
        "subfamily_count": len([s for s in subfamily_ids if s]),
        "cohort_count": len([c for c in cohort_ids if c]),
        "positive_subfamily_count": positive_subfamilies,
        "candidate_breakthrough_count": breakthrough_candidate_count,
        "improved_vs_v3_count": improved_vs_v3,
        "pf_above_110_count": pf_above_threshold,
        "top_family": top.get("stable_family_id", ""),
        "top_subfamily": top.get("stable_subfamily_id", ""),
        "top_cohort": top.get("stable_subfamily_id", ""),
        "top_net_pnl": top.get("net_pnl", 0.0),
        "top_profit_factor": top.get("profit_factor", 0.0),
        "top_max_drawdown": top.get("max_drawdown", 0.0),
        "top_sample_count": top.get("sample_count", 0),
        "top_symbol_count": top.get("symbol_count", 0),
        "top_sector_count": top.get("sector_count", 0),
        "top_split_pass_rate": top.get("split_pass_rate", 0.0),
        "uvxy_like_corruption_detected": corruption_detected,
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(TOURNAMENT_SUMMARY_PATH, summary)
    write_jsonl_file(TOURNAMENT_SCORES_V4_PATH, score_rows)
    write_jsonl_file(TOURNAMENT_LEADERBOARD_V4_PATH, leaderboard)
    write_jsonl_file(TOURNAMENT_HOLDOUT_V4_PATH, holdout_rows)
    write_jsonl_file(
        TOURNAMENT_REGIME_V4_PATH,
        [record_with_hash({**row, **live_safety_fields()}, "record_hash") for row in regime_rows],
    )
    write_jsonl_file(TOURNAMENT_COMPARISON_V4_PATH, comparison_rows)
    write_stage_proof(TOURNAMENT_PROOF_PATH, "research-tournament-v4", str(summary["research_tournament_v4_status"]), summary)
    return {**summary, "artifact_paths": {"research_tournament_v4_summary": str(TOURNAMENT_SUMMARY_PATH)}}
