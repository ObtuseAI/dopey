"""Research tournament V3 with V2 comparison."""
from __future__ import annotations

from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, stress_metrics
from dopey_autonomy.signal_research_v3_common import (
    LEADERBOARD_V3_PATH,
    RESEARCH_V3_ROOT,
    TRADES_V3_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_signal_research.research_coverage_penalty_v2 import coverage_penalty
from dopey_signal_research.research_holdout_v3 import holdout_split_pass_rate, holdout_survival
from dopey_signal_research.research_regime_score_v3 import regime_scores
from dopey_signal_research.research_v2_v3_comparison_v3 import compare_v2_v3


SCORES_PATH = RESEARCH_V3_ROOT / "research_tournament_scores_v3.jsonl"
HOLDOUT_PATH = RESEARCH_V3_ROOT / "research_tournament_holdout_scores_v3.jsonl"
REGIME_PATH = RESEARCH_V3_ROOT / "research_tournament_regime_scores_v3.jsonl"
COMPARISON_PATH = RESEARCH_V3_ROOT / "research_v2_v3_comparison_v3.jsonl"
SUMMARY_PATH = RESEARCH_V3_ROOT / "research_tournament_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "research_tournament_v3_proof.jsonl"


def run_research_tournament_v3() -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    trades = read_jsonl_file(TRADES_V3_PATH)
    by_family: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        family_id = str(trade.get("stable_family_template_id") or trade.get("discovery_family_id") or "unknown")
        by_family[family_id].append(trade)

    score_rows: list[dict[str, object]] = []
    leaderboard: list[dict[str, object]] = []
    holdout_rows: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    positive_families = 0
    breakthrough_count = 0
    improved_vs_v2 = 0

    for family_id, cohort_trades in by_family.items():
        metrics = stress_metrics(cohort_trades)
        split_pass = holdout_split_pass_rate(cohort_trades)
        holdout_flag = holdout_survival(cohort_trades)
        coverage_score, penalties = coverage_penalty({**metrics, "family_id": family_id})
        adjusted_pnl = safe_float(metrics.get("net_pnl", 0.0)) * coverage_score
        if safe_float(metrics.get("net_pnl", 0.0)) > 0.0:
            positive_families += 1
        if adjusted_pnl > 0.0 and safe_float(metrics.get("profit_factor", 0.0)) > 1.10 and holdout_flag and not penalties:
            breakthrough_count += 1
        row = record_with_hash(
            {
                "artifact_type": "research_tournament_score_v3",
                "family_id": family_id,
                "discovery_family_id": family_id,
                "sample_count": metrics.get("sample_count", 0),
                "symbol_count": metrics.get("symbol_count", 0),
                "sector_count": metrics.get("sector_count", 0),
                "net_pnl": metrics.get("net_pnl", 0.0),
                "adjusted_net_pnl": round(adjusted_pnl, 6),
                "expectancy": metrics.get("expectancy", 0.0),
                "profit_factor": metrics.get("profit_factor", 0.0),
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
                    "artifact_type": "research_tournament_holdout_score_v3",
                    "family_id": family_id,
                    "holdout_survival": holdout_flag,
                    "split_pass_rate": split_pass,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )
        comparison = compare_v2_v3(row)
        comparison_rows.append(comparison)
        if comparison.get("improved_vs_v2"):
            improved_vs_v2 += 1

    leaderboard.sort(key=lambda row: safe_float(row.get("adjusted_net_pnl", 0.0)), reverse=True)
    top = leaderboard[0] if leaderboard else {}
    regime_rows = regime_scores(trades)

    summary = {
        "artifact_type": "research_tournament_v3_summary",
        "research_tournament_v3_version": "dopey-public-research-tournament-v3",
        "research_tournament_v3_status": "research_tournament_complete_v3",
        "trade_count": len(trades),
        "family_count": len(by_family),
        "cohort_count": len({trade.get("cohort_id") for trade in trades}),
        "positive_family_count": positive_families,
        "candidate_breakthrough_count": breakthrough_count,
        "improved_vs_v2_count": improved_vs_v2,
        "top_family": top.get("family_id", ""),
        "top_cohort": top.get("family_id", ""),
        "top_net_pnl": top.get("net_pnl", 0.0),
        "top_profit_factor": top.get("profit_factor", 0.0),
        "top_max_drawdown": top.get("max_drawdown", 0.0),
        "top_sample_count": top.get("sample_count", 0),
        "top_symbol_count": top.get("symbol_count", 0),
        "top_sector_count": top.get("sector_count", 0),
        "top_split_pass_rate": top.get("split_pass_rate", 0.0),
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(SCORES_PATH, score_rows)
    write_jsonl_file(LEADERBOARD_V3_PATH, leaderboard)
    write_jsonl_file(HOLDOUT_PATH, holdout_rows)
    write_jsonl_file(REGIME_PATH, [record_with_hash({**row, **live_safety_fields()}, "record_hash") for row in regime_rows])
    write_jsonl_file(COMPARISON_PATH, comparison_rows)
    write_stage_proof(PROOF_PATH, "research-tournament-v3", str(summary["research_tournament_v3_status"]), summary)
    return {**summary, "artifact_paths": {"research_tournament_v3_summary": str(SUMMARY_PATH)}}
