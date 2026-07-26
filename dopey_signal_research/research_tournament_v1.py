"""Research tournament V1."""
from __future__ import annotations

from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, stress_metrics
from dopey_autonomy.signal_research_common import LEADERBOARD_PATH, RESEARCH_ROOT, TRADES_PATH, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_signal_research.research_holdout_v1 import holdout_split_pass_rate, holdout_survival
from dopey_signal_research.research_regime_score_v1 import regime_scores


SCORES_PATH = RESEARCH_ROOT / "research_tournament_scores_v1.jsonl"
HOLDOUT_PATH = RESEARCH_ROOT / "research_tournament_holdout_scores_v1.jsonl"
REGIME_PATH = RESEARCH_ROOT / "research_tournament_regime_scores_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "research_tournament_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "research_tournament_v1_proof.jsonl"


def run_research_tournament_v1() -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    trades = read_jsonl_file(TRADES_PATH)
    by_family: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_cohort: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        by_family[str(trade.get("family_cohort_id", trade.get("setup_family", "unknown")))].append(trade)
        by_cohort[str(trade.get("setup_cohort_id", "unknown"))].append(trade)

    score_rows: list[dict[str, object]] = []
    leaderboard: list[dict[str, object]] = []
    holdout_rows: list[dict[str, object]] = []
    positive_families = 0
    breakthrough_count = 0

    for family_id, cohort_trades in by_family.items():
        metrics = stress_metrics(cohort_trades)
        split_pass = holdout_split_pass_rate(cohort_trades)
        holdout_flag = holdout_survival(cohort_trades)
        if safe_float(metrics.get("net_pnl", 0.0)) > 0.0:
            positive_families += 1
        if (
            safe_float(metrics.get("net_pnl", 0.0)) > 0.0
            and safe_float(metrics.get("profit_factor", 0.0)) > 1.10
            and int(metrics.get("sample_count", 0)) >= 30
            and holdout_flag
        ):
            breakthrough_count += 1
        row = record_with_hash({
            "artifact_type": "research_tournament_score_v1",
            "family_id": family_id,
            "sample_count": metrics.get("sample_count", 0),
            "symbol_count": metrics.get("symbol_count", 0),
            "sector_count": metrics.get("sector_count", 0),
            "net_pnl": metrics.get("net_pnl", 0.0),
            "expectancy": metrics.get("expectancy", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "split_pass_rate": split_pass,
            "holdout_survival": holdout_flag,
            **live_safety_fields(),
        }, "record_hash")
        score_rows.append(row)
        leaderboard.append(row)
        holdout_rows.append(record_with_hash({
            "artifact_type": "research_tournament_holdout_score_v1",
            "family_id": family_id,
            "holdout_survival": holdout_flag,
            "split_pass_rate": split_pass,
            **live_safety_fields(),
        }, "record_hash"))

    leaderboard.sort(key=lambda row: safe_float(row.get("net_pnl", 0.0)), reverse=True)
    top = leaderboard[0] if leaderboard else {}
    regime_rows = regime_scores(trades)

    summary = {
        "artifact_type": "research_tournament_v1_summary",
        "research_tournament_version": "dopey-public-research-tournament-v1",
        "research_tournament_status": "research_tournament_complete",
        "trade_count": len(trades),
        "family_count": len(by_family),
        "cohort_count": len(by_cohort),
        "positive_family_count": positive_families,
        "candidate_breakthrough_count": breakthrough_count,
        "top_family": top.get("family_id", ""),
        "top_cohort": top.get("family_id", ""),
        "top_net_pnl": top.get("net_pnl", 0.0),
        "top_profit_factor": top.get("profit_factor", 0.0),
        "top_max_drawdown": top.get("max_drawdown", 0.0),
        "top_sample_count": top.get("sample_count", 0),
        "top_split_pass_rate": top.get("split_pass_rate", 0.0),
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(SCORES_PATH, score_rows)
    write_jsonl_file(LEADERBOARD_PATH, leaderboard)
    write_jsonl_file(HOLDOUT_PATH, holdout_rows)
    write_jsonl_file(REGIME_PATH, [record_with_hash({**row, **live_safety_fields()}, "record_hash") for row in regime_rows])
    write_stage_proof(PROOF_PATH, "research-tournament-v1", str(summary["research_tournament_status"]), summary)
    return {**summary, "artifact_paths": {"research_tournament_v1_summary": str(SUMMARY_PATH)}}
