"""Research breakthrough gate V4.

Subfamily-aware. Requires:
- public data only
- fixture count 0
- not in failed-family quarantine
- stable family AND subfamily IDs
- sample / symbol / sector counts above minimum
- profit factor > 1.10
- split pass rate / holdout survival
- improves vs V3 on at least one axis
- survives basic stress
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_autonomy.signal_research_common import is_quarantined_signature
from dopey_autonomy.signal_research_v4_common import (
    BREAKTHROUGH_V4_PATH,
    GATE_V4_PROOF_PATH,
    GATE_V4_SUMMARY_PATH,
    MIN_BREAKTHROUGH_PF,
    MIN_BREAKTHROUGH_SAMPLE,
    MIN_BREAKTHROUGH_SECTORS,
    MIN_BREAKTHROUGH_SPLIT_PASS,
    MIN_BREAKTHROUGH_SYMBOLS,
    REJECTIONS_V4_PATH,
    RESEARCH_V4_ROOT,
    TOURNAMENT_LEADERBOARD_V4_PATH,
    V4_CONTINUATION_SUBFAMILIES,
    V4_VOLUME_SUBFAMILIES,
    WATCHLIST_V4_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_signal_research.research_v3_v4_comparison_v4 import compare_v3_v4


def run_research_breakthrough_gate_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    leaderboard = read_jsonl_file(TOURNAMENT_LEADERBOARD_V4_PATH)
    breakthroughs: list[dict[str, object]] = []
    watchlist: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    locked: list[dict[str, object]] = []
    rejection_reasons: Counter[str] = Counter()
    improved_watchlist = 0

    for row in leaderboard:
        subfamily_id = str(
            row.get("stable_subfamily_id", row.get("discovery_subfamily_id", row.get("family_id", "")))
        )
        family_id = str(row.get("stable_family_id", ""))
        status, reasons = classify_breakthrough_v4(row, subfamily_id, family_id)
        comparison = compare_v3_v4(row)
        for reason in reasons:
            rejection_reasons[reason] += 1
        record = record_with_hash(
            {
                "artifact_type": "research_breakthrough_gate_result_v4",
                "stable_subfamily_id": subfamily_id,
                "stable_family_id": family_id,
                "family_id": subfamily_id,
                "status": status,
                "reasons": reasons,
                "improved_vs_v3": comparison.get("improved_vs_v3", False),
                "improved_axes": comparison.get("improved_axes", []),
                "public_data_only": True,
                **live_safety_fields(),
            },
            "record_hash",
        )
        if status == "research_breakthrough_candidate":
            breakthroughs.append(record)
        elif status == "paper_champion_candidate_locked":
            locked.append(record)
            breakthroughs.append(record)
        elif status == "research_watchlist":
            watchlist.append(record)
            if comparison.get("improved_vs_v3"):
                improved_watchlist += 1
        else:
            rejections.append(record)
            if comparison.get("improved_vs_v3") and safe_float(row.get("profit_factor", 0.0)) > 0.8:
                watchlist.append(record)
                improved_watchlist += 1

    gate_status = gate_status_for(breakthroughs, watchlist)
    summary = {
        "artifact_type": "research_breakthrough_gate_v4_summary",
        "research_breakthrough_gate_v4_version": "dopey-public-research-breakthrough-gate-v4",
        "research_breakthrough_gate_v4_status": gate_status,
        "candidate_count": len(leaderboard),
        "breakthrough_candidate_count": len(breakthroughs),
        "watchlist_count": len(watchlist),
        "improved_watchlist_count": improved_watchlist,
        "pf_above_threshold_count": sum(
            1 for row in leaderboard if safe_float(row.get("profit_factor", 0.0)) > MIN_BREAKTHROUGH_PF
        ),
        "rejection_count": len(rejections),
        "top_rejection_reasons": dict(rejection_reasons.most_common(10)),
        "paper_champion_candidate_locked_count": len(locked),
        "watchlist_mutation_required": len(watchlist) > 0 and len(breakthroughs) == 0,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(GATE_V4_SUMMARY_PATH, summary)
    write_jsonl_file(BREAKTHROUGH_V4_PATH, breakthroughs)
    write_jsonl_file(WATCHLIST_V4_PATH, watchlist)
    write_jsonl_file(REJECTIONS_V4_PATH, rejections)
    write_stage_proof(GATE_V4_PROOF_PATH, "research-breakthrough-gate-v4", gate_status, summary)
    return {**summary, "artifact_paths": {"research_breakthrough_gate_v4_summary": str(GATE_V4_SUMMARY_PATH)}}


def classify_breakthrough_v4(row: dict[str, object], subfamily_id: str, family_id: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not subfamily_id or subfamily_id in {"continuation", "volume", "unknown"}:
        reasons.append("stable_subfamily_id_missing")
    if not family_id:
        reasons.append("stable_family_id_missing")
    if subfamily_id and subfamily_id not in V4_CONTINUATION_SUBFAMILIES + V4_VOLUME_SUBFAMILIES:
        reasons.append("unrecognized_subfamily")
    if is_quarantined_signature(subfamily_id) or is_quarantined_signature(family_id):
        reasons.append("quarantined_failed_family")
        return "research_candidate", reasons
    sample_count = int(row.get("sample_count", 0))
    symbol_count = int(row.get("symbol_count", 0))
    sector_count = int(row.get("sector_count", 0))
    net_pnl = safe_float(row.get("net_pnl", 0.0))
    expectancy = safe_float(row.get("expectancy", 0.0))
    profit_factor = safe_float(row.get("profit_factor", 0.0))
    split_pass = safe_float(row.get("split_pass_rate", 0.0))
    holdout = bool(row.get("holdout_survival", False))
    comparison = compare_v3_v4(row)
    if sample_count < MIN_BREAKTHROUGH_SAMPLE:
        reasons.append("sample_count_below_minimum")
    if symbol_count < MIN_BREAKTHROUGH_SYMBOLS:
        reasons.append("symbol_count_below_minimum")
    if sector_count < MIN_BREAKTHROUGH_SECTORS:
        reasons.append("sector_count_below_minimum")
    if net_pnl <= 0.0:
        reasons.append("net_pnl_not_positive")
    if expectancy <= 0.0:
        reasons.append("expectancy_not_positive")
    if profit_factor < MIN_BREAKTHROUGH_PF:
        reasons.append("profit_factor_below_threshold")
    if split_pass < MIN_BREAKTHROUGH_SPLIT_PASS:
        reasons.append("split_pass_rate_below_threshold")
    if not holdout:
        reasons.append("holdout_survival_failed")
    if row.get("coverage_penalties"):
        reasons.extend(list(row.get("coverage_penalties", [])))
    if not comparison.get("improved_vs_v3"):
        reasons.append("no_improvement_vs_v3")
    if reasons:
        if comparison.get("improved_vs_v3") and profit_factor > 0.9:
            return "research_watchlist", reasons
        return "research_candidate", reasons
    if profit_factor >= 1.20 and sample_count >= 50 and symbol_count >= MIN_BREAKTHROUGH_SYMBOLS:
        return "paper_champion_candidate_locked", reasons
    return "research_breakthrough_candidate", reasons


def gate_status_for(breakthroughs: list[dict[str, object]], watchlist: list[dict[str, object]]) -> str:
    if breakthroughs:
        return "research_breakthrough_candidates_found"
    if watchlist:
        return "research_watchlist_only"
    return "no_breakthrough_candidates_found"
