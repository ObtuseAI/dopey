"""V5 gate rejection analyzer for V6.

Diagnoses each V5 watchlist candidate using the V5 gate rejections, tournament
leaderboard, holdout scores, regime scores, path trades, scoreboard, and mutation
queue. Produces deterministic diagnosis records, a blocker matrix, and a summary.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Sequence

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v6_common import (
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V5_ROOT,
    RESEARCH_V6_VERSION,
    V5_BREAKTHROUGH_BLOCKER_MATRIX_V6_PATH,
    V5_GATE_REJECTION_ANALYSIS_V6_PATH,
    V5_GATE_REJECTION_ANALYZER_V6_PROOF_PATH,
    V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH,
    V5_WATCHLIST_DIAGNOSIS_V6_PATH,
    load_v5_mutation_queue_records,
    load_v5_rejection_records,
    load_v5_watchlist_records,
    research_v6_proof_record,
    utc_now_iso,
)
from dopey_signal_research.v5_watchlist_diagnosis_v6 import (
    compute_concentration,
    compute_holdout_survival,
    compute_outlier_dependence,
    compute_split_pass_rate,
    compute_stress_survival,
    failed_gate_criteria,
    mutation_plan_linkage,
    repairability_score,
    safe_float,
    safe_int,
)


__all__ = ["run_v5_gate_rejection_analyzer_v6"]


V5_TOURNAMENT_LEADERBOARD_PATH = RESEARCH_V5_ROOT / "research_tournament_leaderboard_v5.jsonl"
V5_HOLDOUT_SCORES_PATH = RESEARCH_V5_ROOT / "research_tournament_holdout_scores_v5.jsonl"
V5_REGIME_SCORES_PATH = RESEARCH_V5_ROOT / "research_tournament_regime_scores_v5.jsonl"
V5_PATH_TRADES_PATH = RESEARCH_V5_ROOT / "research_path_trades_v5.jsonl"
V5_SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v5.json"


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return read_jsonl_file(path) if path.exists() else []


def _load_json(path: Path) -> dict[str, object]:
    return read_json_file(path) if path.exists() else {}


def _index_by(records: Sequence[dict[str, object]], key: str) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        k = str(rec.get(key, ""))
        if k:
            out[k] = rec
    return out


def _diagnosis_id(idx: int, subfamily_id: str) -> str:
    clean = subfamily_id.replace("|", "-").replace(" ", "_") if subfamily_id else "unknown"
    return f"diag-v6-{idx:04d}-{clean}"


def _diagnosis_record(
    idx: int,
    candidate: dict[str, object],
    holdout_map: dict[str, dict[str, object]],
    regime_map: dict[str, dict[str, object]],
    trades: Sequence[dict[str, object]],
) -> dict[str, object]:
    subfamily_id = str(candidate.get("stable_subfamily_id", ""))
    blockers = failed_gate_criteria(candidate)
    concentration = compute_concentration(subfamily_id, trades)
    outlier = compute_outlier_dependence(candidate, trades)
    rec = {
        "artifact_type": "v5_watchlist_diagnosis_v6",
        "diagnosis_id": _diagnosis_id(idx, subfamily_id),
        "stable_family_id": str(candidate.get("stable_family_id", "")),
        "stable_subfamily_id": subfamily_id,
        "cohort_id": str(candidate.get("cohort_id", "")),
        "profit_factor": safe_float(candidate.get("profit_factor", 0.0)),
        "net_pnl": safe_float(candidate.get("net_pnl", 0.0)),
        "sample_count": safe_int(candidate.get("sample_count", 0)),
        "symbol_count": safe_int(candidate.get("symbol_count", 0)),
        "sector_count": safe_int(candidate.get("sector_count", 0)),
        "split_pass_rate": compute_split_pass_rate(candidate),
        "holdout_survival": compute_holdout_survival(candidate, holdout_map),
        "max_drawdown": safe_float(candidate.get("max_drawdown", 0.0)),
        "expectancy": safe_float(candidate.get("expectancy", 0.0)),
        "stress_survival": compute_stress_survival(candidate, regime_map),
        "top_symbol_trade_share": concentration["top_symbol_trade_share"],
        "top_sector_trade_share": concentration["top_sector_trade_share"],
        "max_trade_pnl_magnitude": outlier["max_trade_pnl_magnitude"],
        "max_trade_to_drawdown_ratio": outlier["max_trade_to_drawdown_ratio"],
        "failed_gate_criteria": blockers,
        "repairability_score": repairability_score(candidate, blockers),
        "mutation_plan_linkage": mutation_plan_linkage(blockers),
        "pf_above_threshold": safe_float(candidate.get("profit_factor", 0.0)) > MIN_BREAKTHROUGH_PF,
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def _rejection_analysis_record(diagnosis: dict[str, object]) -> dict[str, object]:
    rec = {
        "artifact_type": "v5_gate_rejection_analysis_v6",
        "diagnosis_id": diagnosis["diagnosis_id"],
        "stable_subfamily_id": diagnosis["stable_subfamily_id"],
        "profit_factor": diagnosis["profit_factor"],
        "net_pnl": diagnosis["net_pnl"],
        "sample_count": diagnosis["sample_count"],
        "symbol_count": diagnosis["symbol_count"],
        "sector_count": diagnosis["sector_count"],
        "split_pass_rate": diagnosis["split_pass_rate"],
        "holdout_survival": diagnosis["holdout_survival"],
        "max_drawdown": diagnosis["max_drawdown"],
        "expectancy": diagnosis["expectancy"],
        "stress_survival": diagnosis["stress_survival"],
        "concentration": {
            "top_symbol_trade_share": diagnosis["top_symbol_trade_share"],
            "top_sector_trade_share": diagnosis["top_sector_trade_share"],
        },
        "outlier_dependence": {
            "max_trade_pnl_magnitude": diagnosis["max_trade_pnl_magnitude"],
            "max_trade_to_drawdown_ratio": diagnosis["max_trade_to_drawdown_ratio"],
        },
        "failed_gate_criteria": diagnosis["failed_gate_criteria"],
        "repairability_score": diagnosis["repairability_score"],
        "mutation_plan_linkage": diagnosis["mutation_plan_linkage"],
        "pf_above_threshold": diagnosis["pf_above_threshold"],
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def _blocker_matrix_record(
    diag_id: str,
    subfamily_id: str,
    blocker_type: str,
    candidate_idx: int,
) -> dict[str, object]:
    blocker_id = f"blocker-v6-{candidate_idx:04d}-{blocker_type}"
    rec = {
        "artifact_type": "v5_breakthrough_blocker_matrix_v6",
        "blocker_id": blocker_id,
        "diagnosis_id": diag_id,
        "stable_subfamily_id": subfamily_id,
        "blocker_type": blocker_type,
        "repairable": blocker_type in {
            "drawdown_exceeds_max",
            "holdout_survival_failed",
            "split_pass_rate_below_threshold",
            "expectancy_below_threshold",
            "stress_survival_failed",
            "outlier_dependence_high",
            "concentration_exceeds_max",
            "symbol_coverage_below_min",
            "sector_coverage_below_min",
        },
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def run_v5_gate_rejection_analyzer_v6() -> dict[str, object]:
    watchlist = load_v5_watchlist_records()
    rejections = load_v5_rejection_records()
    leaderboard = _load_jsonl(V5_TOURNAMENT_LEADERBOARD_PATH)
    holdout_scores = _load_jsonl(V5_HOLDOUT_SCORES_PATH)
    regime_scores = _load_jsonl(V5_REGIME_SCORES_PATH)
    trades = _load_jsonl(V5_PATH_TRADES_PATH)
    scoreboard = _load_json(V5_SCOREBOARD_PATH)
    mutation_queue = load_v5_mutation_queue_records()

    holdout_map = _index_by(holdout_scores, "stable_subfamily_id")
    regime_map = _index_by(regime_scores, "regime_cohort_id")

    diagnosis_records: list[dict[str, object]] = []
    analysis_records: list[dict[str, object]] = []
    blocker_records: list[dict[str, object]] = []
    all_blockers: list[str] = []
    pf_above_count = 0
    repairable_count = 0

    for idx, candidate in enumerate(watchlist):
        if not isinstance(candidate, dict):
            continue
        diag = _diagnosis_record(idx, candidate, holdout_map, regime_map, trades)
        diagnosis_records.append(diag)
        analysis_records.append(_rejection_analysis_record(diag))
        if diag["pf_above_threshold"]:
            pf_above_count += 1
        if diag["repairability_score"] >= 0.5:
            repairable_count += 1
        for blocker in diag["failed_gate_criteria"]:
            all_blockers.append(blocker)
            blocker_records.append(_blocker_matrix_record(
                str(diag["diagnosis_id"]),
                str(diag["stable_subfamily_id"]),
                blocker,
                idx,
            ))

    blocker_counts = Counter(all_blockers)
    top_blockers = [
        {"blocker_type": k, "count": v}
        for k, v in blocker_counts.most_common()
    ]

    write_jsonl_file(V5_WATCHLIST_DIAGNOSIS_V6_PATH, diagnosis_records)
    write_jsonl_file(V5_GATE_REJECTION_ANALYSIS_V6_PATH, analysis_records)
    write_jsonl_file(V5_BREAKTHROUGH_BLOCKER_MATRIX_V6_PATH, blocker_records)

    status = "v5_gate_rejection_analysis_complete_v6"
    summary = {
        "artifact_type": "v5_gate_rejection_analyzer_v6_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "v5_gate_rejection_analyzer_status": status,
        "watchlist_candidate_count": len(watchlist),
        "pf_above_threshold_watchlist_count": pf_above_count,
        "breakthrough_blocker_count": len(all_blockers),
        "top_breakthrough_blockers": top_blockers,
        "repairable_candidate_count": repairable_count,
        "rejection_record_count": len(rejections),
        "leaderboard_record_count": len(leaderboard),
        "holdout_score_count": len(holdout_scores),
        "regime_score_count": len(regime_scores),
        "trade_count": len(trades),
        "scoreboard_row_count": len(scoreboard.get("rows", [])),
        "mutation_queue_count": len(mutation_queue),
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH, summary)
    write_jsonl_file(
        V5_GATE_REJECTION_ANALYZER_V6_PROOF_PATH,
        [research_v6_proof_record("v5-gate-rejection-analyzer-v6", status, summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v5_gate_rejection_analyzer_v6(), indent=2, sort_keys=True, default=str))
