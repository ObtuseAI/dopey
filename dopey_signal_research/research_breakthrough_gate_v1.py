"""Research breakthrough gate V1."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import (
    BREAKTHROUGH_PATH,
    LEADERBOARD_PATH,
    MIN_BREAKTHROUGH_PF,
    MIN_BREAKTHROUGH_SAMPLE,
    MIN_BREAKTHROUGH_SPLIT_PASS,
    MIN_BREAKTHROUGH_SYMBOLS,
    QUARANTINE_PATH,
    RESEARCH_ROOT,
    is_quarantined_signature,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file


REJECTIONS_PATH = RESEARCH_ROOT / "research_breakthrough_rejections_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "research_breakthrough_gate_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "research_breakthrough_gate_v1_proof.jsonl"


def run_research_breakthrough_gate_v1() -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    leaderboard = read_jsonl_file(LEADERBOARD_PATH)
    quarantine_ids = {str(row.get("family_id", "")) for row in read_jsonl_file(QUARANTINE_PATH)}
    breakthroughs: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    watchlist: list[dict[str, object]] = []
    locked: list[dict[str, object]] = []
    rejection_reasons: Counter[str] = Counter()

    for row in leaderboard:
        family_id = str(row.get("family_id", ""))
        status, reasons = classify_breakthrough(row, quarantine_ids)
        for reason in reasons:
            rejection_reasons[reason] += 1
        record = record_with_hash({
            "artifact_type": "research_breakthrough_gate_result_v1",
            "family_id": family_id,
            "status": status,
            "reasons": reasons,
            **live_safety_fields(),
        }, "record_hash")
        if status == "research_breakthrough_candidate":
            breakthroughs.append(record)
        elif status == "paper_champion_candidate_locked":
            locked.append(record)
            breakthroughs.append(record)
        elif status == "research_watchlist":
            watchlist.append(record)
        else:
            rejections.append(record)

    gate_status = breakthrough_status(breakthroughs, watchlist)
    summary = {
        "artifact_type": "research_breakthrough_gate_v1_summary",
        "research_breakthrough_gate_version": "dopey-public-research-breakthrough-gate-v1",
        "research_breakthrough_gate_status": gate_status,
        "candidate_count": len(leaderboard),
        "breakthrough_candidate_count": len(breakthroughs),
        "watchlist_count": len(watchlist),
        "rejection_count": len(rejections),
        "top_rejection_reasons": dict(rejection_reasons.most_common(10)),
        "paper_champion_candidate_locked_count": len(locked),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(BREAKTHROUGH_PATH, breakthroughs)
    write_jsonl_file(REJECTIONS_PATH, rejections)
    write_stage_proof(PROOF_PATH, "research-breakthrough-gate-v1", gate_status, summary)
    return {**summary, "artifact_paths": {"research_breakthrough_gate_v1_summary": str(SUMMARY_PATH)}}


def classify_breakthrough(row: dict[str, object], quarantine_ids: set[str]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    family_id = str(row.get("family_id", ""))
    if family_id in quarantine_ids or is_quarantined_signature(family_id):
        reasons.append("quarantined_failed_family")
        return "research_candidate", reasons
    sample_count = int(row.get("sample_count", 0))
    symbol_count = int(row.get("symbol_count", 0))
    net_pnl = safe_float(row.get("net_pnl", 0.0))
    expectancy = safe_float(row.get("expectancy", 0.0))
    profit_factor = safe_float(row.get("profit_factor", 0.0))
    split_pass = safe_float(row.get("split_pass_rate", 0.0))
    holdout = bool(row.get("holdout_survival", False))
    if sample_count < MIN_BREAKTHROUGH_SAMPLE:
        reasons.append("sample_count_below_minimum")
    if symbol_count < MIN_BREAKTHROUGH_SYMBOLS:
        reasons.append("symbol_count_below_minimum")
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
    if reasons:
        if net_pnl > 0.0 and profit_factor > 1.0:
            return "research_watchlist", reasons
        return "research_candidate", reasons
    if profit_factor >= 1.20 and sample_count >= 50:
        return "paper_champion_candidate_locked", reasons
    return "research_breakthrough_candidate", reasons


def breakthrough_status(breakthroughs: list[dict[str, object]], watchlist: list[dict[str, object]]) -> str:
    if breakthroughs:
        return "research_breakthrough_candidates_found"
    if watchlist:
        return "research_watchlist_only"
    return "no_breakthrough_candidates_found"


def artifact_paths() -> dict[str, str]:
    return {"research_breakthrough_gate_v1_summary": str(SUMMARY_PATH)}
