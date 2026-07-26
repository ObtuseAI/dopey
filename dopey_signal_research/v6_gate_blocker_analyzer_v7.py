"""V6 gate blocker analyzer for V7.

Diagnoses each V6 watchlist candidate and each V6 PF-above-threshold gate
rejection using the immutable V6 tournament leaderboard, holdout scores, regime
scores, path trades, scoreboard, and mutation queue.  Produces deterministic
diagnosis records, a trade-active blocker matrix, and a summary.
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
    RESEARCH_V6_ROOT,
    TOURNAMENT_REGIME_V6_PATH,
    TRADES_V6_PATH,
)
from dopey_autonomy.signal_research_v7_common import (
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V7_VERSION,
    V6_GATE_BLOCKER_ANALYSIS_V7_PATH,
    V6_TRADE_ACTIVE_BLOCKER_MATRIX_V7_PATH,
    V6_WATCHLIST_DIAGNOSIS_V7_PATH,
    V6_WATCHLIST_DIAGNOSIS_V7_PROOF_PATH,
    V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH,
    load_v6_live_gate_status,
    load_v6_mutation_queue_records,
    load_v6_mutation_queue_summary,
    load_v6_rejection_records,
    load_v6_summary,
    load_v6_tournament_leaderboard,
    load_v6_watchlist_records,
    research_v7_proof_record,
    utc_now_iso,
)
from dopey_signal_research.v6_watchlist_diagnosis_v7 import (
    compute_concentration,
    compute_holdout_survival,
    compute_outlier_dependence,
    compute_split_pass_rate,
    compute_stress_survival,
    compute_trade_active_ratio,
    failed_gate_criteria,
    is_no_trade_dominant,
    mutation_plan_linkage,
    repairability_score,
    safe_float,
    safe_int,
)


__all__ = ["run_v6_gate_blocker_analyzer_v7"]


V6_SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6.json"
V6_HOLDOUT_SCORES_PATH = RESEARCH_V6_ROOT / "research_tournament_holdout_scores_v6.jsonl"


REPAIRABLE_BLOCKERS = {
    "drawdown_exceeds_max",
    "holdout_survival_failed",
    "split_pass_rate_below_threshold",
    "expectancy_below_threshold",
    "expectancy_not_positive",
    "stress_survival_failed",
    "outlier_dependence_high",
    "concentration_exceeds_max",
    "symbol_coverage_below_min",
    "sector_coverage_below_min",
    "no_improvement_vs_v5",
    "profit_factor_below_threshold",
    "net_pnl_not_positive",
    "no_trade_dominant",
}


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
    return f"diag-v7-{idx:04d}-{clean}"


def _diagnosis_record(
    idx: int,
    candidate: dict[str, object],
    diagnosis_scope: str,
    holdout_map: dict[str, dict[str, object]],
    regime_map: dict[str, dict[str, object]],
    trades: Sequence[dict[str, object]],
) -> dict[str, object]:
    subfamily_id = str(candidate.get("stable_subfamily_id", ""))
    original_blockers = failed_gate_criteria(candidate)
    concentration = compute_concentration(subfamily_id, trades)
    outlier = compute_outlier_dependence(candidate, trades)
    trade_ratio = compute_trade_active_ratio(subfamily_id, trades)
    no_trade_dominant = is_no_trade_dominant(trade_ratio)
    all_blockers = list(original_blockers)
    if no_trade_dominant:
        all_blockers.append("no_trade_dominant")

    rec = {
        "artifact_type": "v6_watchlist_diagnosis_v7",
        "diagnosis_id": _diagnosis_id(idx, subfamily_id),
        "diagnosis_scope": diagnosis_scope,
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
        "trade_active_count": trade_ratio["trade_active_count"],
        "no_trade_count": trade_ratio["no_trade_count"],
        "trade_active_ratio": trade_ratio["trade_active_ratio"],
        "no_trade_ratio": trade_ratio["no_trade_ratio"],
        "no_trade_dominant": no_trade_dominant,
        "failed_gate_criteria": original_blockers,
        "all_blockers": all_blockers,
        "repairability_score": repairability_score(candidate, all_blockers, no_trade_dominant),
        "mutation_plan_linkage": mutation_plan_linkage(all_blockers),
        "pf_above_threshold": safe_float(candidate.get("profit_factor", 0.0)) > MIN_BREAKTHROUGH_PF,
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def _gate_blocker_analysis_record(diagnosis: dict[str, object]) -> dict[str, object]:
    rec = {
        "artifact_type": "v6_gate_blocker_analysis_v7",
        "diagnosis_id": diagnosis["diagnosis_id"],
        "diagnosis_scope": diagnosis["diagnosis_scope"],
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
        "trade_active_ratio": {
            "trade_active_count": diagnosis["trade_active_count"],
            "no_trade_count": diagnosis["no_trade_count"],
            "trade_active_ratio": diagnosis["trade_active_ratio"],
            "no_trade_ratio": diagnosis["no_trade_ratio"],
        },
        "no_trade_dominant": diagnosis["no_trade_dominant"],
        "failed_gate_criteria": diagnosis["failed_gate_criteria"],
        "all_blockers": diagnosis["all_blockers"],
        "repairability_score": diagnosis["repairability_score"],
        "mutation_plan_linkage": diagnosis["mutation_plan_linkage"],
        "pf_above_threshold": diagnosis["pf_above_threshold"],
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
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
    diagnosis_scope: str,
    blocker_type: str,
    candidate_idx: int,
) -> dict[str, object]:
    blocker_id = f"blocker-v7-{candidate_idx:04d}-{blocker_type}"
    rec = {
        "artifact_type": "v6_trade_active_blocker_matrix_v7",
        "blocker_id": blocker_id,
        "diagnosis_id": diag_id,
        "stable_subfamily_id": subfamily_id,
        "diagnosis_scope": diagnosis_scope,
        "blocker_type": blocker_type,
        "repairable": blocker_type in REPAIRABLE_BLOCKERS,
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def _select_candidates(
    watchlist: Sequence[dict[str, object]],
    rejections: Sequence[dict[str, object]],
) -> list[tuple[dict[str, object], str]]:
    """Return the 2 watchlist candidates plus any PF-above-threshold rejections.

    The V6 summary reports watchlist_count=2 and pf_above_110_count=6.  The two
    watchlist candidates are themselves PF-above-threshold, so the unique set
    of candidates to diagnose is the watchlist plus the PF-above-threshold
    rejections (4), totalling 6.
    """
    seen: set[str] = set()
    selected: list[tuple[dict[str, object], str]] = []
    for candidate in watchlist:
        if not isinstance(candidate, dict):
            continue
        sub = str(candidate.get("stable_subfamily_id", ""))
        if sub and sub not in seen:
            seen.add(sub)
            selected.append((candidate, "watchlist"))
    for candidate in rejections:
        if not isinstance(candidate, dict):
            continue
        sub = str(candidate.get("stable_subfamily_id", ""))
        if not sub or sub in seen:
            continue
        pf = safe_float(candidate.get("profit_factor", 0.0))
        if pf > MIN_BREAKTHROUGH_PF:
            seen.add(sub)
            selected.append((candidate, "pf_above_110_rejection"))
    return selected


def run_v6_gate_blocker_analyzer_v7() -> dict[str, object]:
    watchlist = load_v6_watchlist_records()
    rejections = load_v6_rejection_records()
    leaderboard = load_v6_tournament_leaderboard()
    holdout_scores = _load_jsonl(V6_HOLDOUT_SCORES_PATH)
    regime_scores = _load_jsonl(TOURNAMENT_REGIME_V6_PATH)
    trades = _load_jsonl(TRADES_V6_PATH)
    scoreboard = _load_json(V6_SCOREBOARD_PATH)
    mutation_queue = load_v6_mutation_queue_records()
    mutation_queue_summary = load_v6_mutation_queue_summary()
    v6_summary = load_v6_summary()
    live_gate = load_v6_live_gate_status()

    holdout_map = _index_by(holdout_scores, "stable_subfamily_id")
    regime_map = _index_by(regime_scores, "regime_cohort_id")

    candidates = _select_candidates(watchlist, rejections)

    diagnosis_records: list[dict[str, object]] = []
    analysis_records: list[dict[str, object]] = []
    blocker_records: list[dict[str, object]] = []
    all_blockers: list[str] = []
    pf_above_count = 0
    repairable_count = 0
    no_trade_dominant_count = 0

    for idx, (candidate, scope) in enumerate(candidates):
        diag = _diagnosis_record(idx, candidate, scope, holdout_map, regime_map, trades)
        diagnosis_records.append(diag)
        analysis_records.append(_gate_blocker_analysis_record(diag))
        if diag["pf_above_threshold"]:
            pf_above_count += 1
        if diag["repairability_score"] >= 0.5:
            repairable_count += 1
        if diag["no_trade_dominant"]:
            no_trade_dominant_count += 1
        for blocker in diag["all_blockers"]:
            all_blockers.append(blocker)
            blocker_records.append(_blocker_matrix_record(
                str(diag["diagnosis_id"]),
                str(diag["stable_subfamily_id"]),
                scope,
                blocker,
                idx,
            ))

    blocker_counts = Counter(all_blockers)
    top_blockers = [
        {"blocker_type": k, "count": v}
        for k, v in blocker_counts.most_common()
    ]

    write_jsonl_file(V6_WATCHLIST_DIAGNOSIS_V7_PATH, diagnosis_records)
    write_jsonl_file(V6_GATE_BLOCKER_ANALYSIS_V7_PATH, analysis_records)
    write_jsonl_file(V6_TRADE_ACTIVE_BLOCKER_MATRIX_V7_PATH, blocker_records)

    status = "v6_watchlist_diagnosis_complete_v7"
    summary = {
        "artifact_type": "v6_watchlist_diagnosis_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "v6_watchlist_diagnosis_v7_status": status,
        "watchlist_candidate_count": len(watchlist),
        "pf_above_110_count": pf_above_count,
        "diagnosed_candidate_count": len(candidates),
        "breakthrough_blocker_count": len(all_blockers),
        "top_breakthrough_blockers": top_blockers,
        "repairable_candidate_count": repairable_count,
        "no_trade_dominant_count": no_trade_dominant_count,
        "v6_rejection_record_count": len(rejections),
        "v6_leaderboard_record_count": len(leaderboard),
        "v6_holdout_score_count": len(holdout_scores),
        "v6_regime_score_count": len(regime_scores),
        "v6_trade_count": len(trades),
        "v6_scoreboard_row_count": len(scoreboard.get("rows", [])),
        "v6_mutation_queue_count": len(mutation_queue),
        "v6_mutation_queue_summary_status": mutation_queue_summary.get("research_mutation_queue_v6_status", ""),
        "v6_summary_status": v6_summary.get("public_signal_research_v6_status", ""),
        "v6_live_gate_status": live_gate.get("live_gate_status", ""),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        V6_WATCHLIST_DIAGNOSIS_V7_PROOF_PATH,
        [research_v7_proof_record("v6-watchlist-diagnosis-v7", status, summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v6_gate_blocker_analyzer_v7(), indent=2, sort_keys=True, default=str))
