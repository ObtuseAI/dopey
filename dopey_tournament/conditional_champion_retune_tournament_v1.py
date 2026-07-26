"""Retune tournament and before/after comparison for conditional champions."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields, load_public_trades
from dopey_autonomy.public_champion_common import pnl_metrics
from dopey_autonomy.champion_repair_common import (
    REPAIR_ROOT,
    RETUNE_LEADERBOARD_PATH,
    RETUNE_TRADES_PATH,
    conditional_champion_names,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import group_records, read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_strategy_cohorts.strategy_cohort_models import COHORT_LEVELS

from .conditional_champion_before_after_comparison_v1 import build_before_after_rows


SCORES_PATH = REPAIR_ROOT / "conditional_champion_retune_scores_v1.jsonl"
COMPARISON_PATH = REPAIR_ROOT / "conditional_champion_before_after_comparison_v1.jsonl"
SUMMARY_PATH = REPAIR_ROOT / "conditional_champion_retune_tournament_v1_summary.json"
PROOF_PATH = REPAIR_ROOT / "conditional_champion_retune_tournament_v1_proof.jsonl"


def run_conditional_champion_retune_tournament_v1() -> dict[str, object]:
    retune_trades = [t for t in read_jsonl_file(RETUNE_TRADES_PATH) if str(t.get("trade_intent", "")) in {"long_call", "long_put"}]
    original_trades = load_public_trades()
    scores: list[dict[str, object]] = []
    leaderboard: list[dict[str, object]] = []

    for level in COHORT_LEVELS:
        for cohort_id, records in group_records(retune_trades, level).items():
            metrics = pnl_metrics(records)
            score = record_with_hash({
                "artifact_type": "conditional_champion_retune_score_v1",
                "cohort_level": level,
                "cohort_id": cohort_id,
                **metrics,
                "parent_champion_ids": sorted({str(r.get("parent_champion_id", "")) for r in records}),
                **live_safety_fields(),
            }, "record_hash")
            scores.append(score)
            leaderboard.append(score)

    leaderboard = sorted(leaderboard, key=lambda item: safe_float(item.get("net_pnl")), reverse=True)
    comparisons = build_before_after_rows(retune_trades, original_trades)
    improved = sum(1 for row in comparisons if safe_float(row.get("improvement_score")) > 0.0)
    worse = sum(1 for row in comparisons if safe_float(row.get("improvement_score")) < 0.0)
    top = leaderboard[0] if leaderboard else {}

    summary = {
        "artifact_type": "conditional_champion_retune_tournament_v1_summary",
        "conditional_champion_retune_tournament_version": "dopey-public-champion-retune-tournament-v1",
        "conditional_champion_retune_tournament_status": "conditional_retune_tournament_complete",
        "retuned_strategy_count": len({str(t.get("strategy_id", "")) for t in retune_trades}),
        "retuned_trade_count": len(retune_trades),
        "improved_candidate_count": improved,
        "worse_candidate_count": worse,
        "top_retuned_strategy": top.get("cohort_id", ""),
        "top_improvement_score": max((safe_float(row.get("improvement_score")) for row in comparisons), default=0.0),
        "public_data_only": True,
        "fixture_trade_count": 0,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(SCORES_PATH, scores)
    write_jsonl_file(RETUNE_LEADERBOARD_PATH, leaderboard)
    write_jsonl_file(COMPARISON_PATH, [record_with_hash({**row, "artifact_type": "conditional_champion_before_after_comparison_v1", **live_safety_fields()}, "record_hash") for row in comparisons])
    write_stage_proof(PROOF_PATH, "conditional-champion-retune-tournament-v1", str(summary["conditional_champion_retune_tournament_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "conditional_champion_retune_leaderboard_v1": str(RETUNE_LEADERBOARD_PATH),
        "conditional_champion_retune_tournament_v1_summary": str(SUMMARY_PATH),
    }
