"""Research breakthrough gate V3."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import is_quarantined_signature
from dopey_autonomy.signal_research_v3_common import (
    BREAKTHROUGH_V3_PATH,
    LEADERBOARD_V3_PATH,
    MIN_BREAKTHROUGH_PF,
    MIN_BREAKTHROUGH_SAMPLE,
    MIN_BREAKTHROUGH_SECTORS,
    MIN_BREAKTHROUGH_SPLIT_PASS,
    MIN_BREAKTHROUGH_SYMBOLS,
    RESEARCH_V3_ROOT,
    WATCHLIST_V3_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_signal_research.research_v2_v3_comparison_v3 import compare_v2_v3


REJECTIONS_PATH = RESEARCH_V3_ROOT / "research_breakthrough_rejections_v3.jsonl"
SUMMARY_PATH = RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_proof.jsonl"


def run_research_breakthrough_gate_v3() -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    leaderboard = read_jsonl_file(LEADERBOARD_V3_PATH)
    breakthroughs: list[dict[str, object]] = []
    watchlist: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    locked: list[dict[str, object]] = []
    rejection_reasons: Counter[str] = Counter()
    improved_watchlist = 0

    for row in leaderboard:
        family_id = str(row.get("discovery_family_id", row.get("family_id", "")))
        status, reasons = classify_breakthrough_v3(row)
        comparison = compare_v2_v3(row)
        for reason in reasons:
            rejection_reasons[reason] += 1
        record = record_with_hash(
            {
                "artifact_type": "research_breakthrough_gate_result_v3",
                "discovery_family_id": family_id,
                "family_id": family_id,
                "status": status,
                "reasons": reasons,
                "improved_vs_v2": comparison.get("improved_vs_v2", False),
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
            if comparison.get("improved_vs_v2"):
                improved_watchlist += 1
        else:
            rejections.append(record)
            if comparison.get("improved_vs_v2") and safe_float(row.get("profit_factor", 0.0)) > 0.8:
                watchlist.append(record)
                improved_watchlist += 1

    gate_status = gate_status_for(breakthroughs, watchlist)
    summary = {
        "artifact_type": "research_breakthrough_gate_v3_summary",
        "research_breakthrough_gate_v3_version": "dopey-public-research-breakthrough-gate-v3",
        "research_breakthrough_gate_v3_status": gate_status,
        "candidate_count": len(leaderboard),
        "breakthrough_candidate_count": len(breakthroughs),
        "watchlist_count": len(watchlist),
        "improved_watchlist_count": improved_watchlist,
        "rejection_count": len(rejections),
        "top_rejection_reasons": dict(rejection_reasons.most_common(10)),
        "paper_champion_candidate_locked_count": len(locked),
        "watchlist_mutation_required": len(watchlist) > 0 and len(breakthroughs) == 0,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(BREAKTHROUGH_V3_PATH, breakthroughs)
    write_jsonl_file(WATCHLIST_V3_PATH, watchlist)
    write_jsonl_file(REJECTIONS_PATH, rejections)
    write_stage_proof(PROOF_PATH, "research-breakthrough-gate-v3", gate_status, summary)
    return {**summary, "artifact_paths": {"research_breakthrough_gate_v3_summary": str(SUMMARY_PATH)}}


def classify_breakthrough_v3(row: dict[str, object]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    family_id = str(row.get("discovery_family_id", row.get("family_id", "")))
    if not family_id or family_id in {"continuation", "volume", "unknown"}:
        reasons.append("stable_family_id_missing")
    if is_quarantined_signature(family_id):
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
    comparison = compare_v2_v3(row)
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
    if not comparison.get("improved_vs_v2"):
        reasons.append("no_improvement_vs_v2")
    if reasons:
        if comparison.get("improved_vs_v2") and profit_factor > 0.9:
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
