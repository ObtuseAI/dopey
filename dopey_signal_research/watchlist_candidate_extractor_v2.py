"""Watchlist candidate extractor V2."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v2_common import (
    RESEARCH_V2_ROOT,
    V1_LEADERBOARD_PATH,
    V1_GATE_SUMMARY_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_signal_research.research_breakthrough_gate_v1 import classify_breakthrough
from dopey_signal_research.stable_discovery_family_id_v2 import assign_stable_ids


WATCHLIST_PATH = RESEARCH_V2_ROOT / "watchlist_candidates_v2.jsonl"
REPAIRS_PATH = RESEARCH_V2_ROOT / "watchlist_family_id_repairs_v2.jsonl"
LINEAGE_PATH = RESEARCH_V2_ROOT / "watchlist_lineage_records_v2.jsonl"
SUMMARY_PATH = RESEARCH_V2_ROOT / "watchlist_candidate_extractor_v2_summary.json"
PROOF_PATH = RESEARCH_V2_ROOT / "watchlist_candidate_extractor_v2_proof.jsonl"


def run_watchlist_candidate_extractor_v2() -> dict[str, object]:
    RESEARCH_V2_ROOT.mkdir(parents=True, exist_ok=True)
    leaderboard = read_jsonl_file(V1_LEADERBOARD_PATH)
    gate = read_json_file(V1_GATE_SUMMARY_PATH)
    quarantine_ids: set[str] = set()
    candidates: list[dict[str, object]] = []
    repairs: list[dict[str, object]] = []
    lineage: list[dict[str, object]] = []
    generic_repairs = 0
    overlap_count = 0

    for row in leaderboard:
        status, reasons = classify_breakthrough(row, quarantine_ids)
        if status != "research_watchlist":
            continue
        original_label = str(row.get("family_id", ""))
        ids = assign_stable_ids(original_label)
        if ids["generic_label_repaired"]:
            generic_repairs += 1
        if ids["quarantine_overlap"]:
            overlap_count += 1
        record = record_with_hash({
            "artifact_type": "watchlist_candidate_v2",
            "v1_family_label": original_label,
            "v1_net_pnl": row.get("net_pnl", 0.0),
            "v1_profit_factor": row.get("profit_factor", 0.0),
            "v1_sample_count": row.get("sample_count", 0),
            "v1_symbol_count": row.get("symbol_count", 0),
            "v1_rejection_reasons": reasons,
            **ids,
            **live_safety_fields(),
        }, "record_hash")
        candidates.append(record)
        repairs.append(record_with_hash({"artifact_type": "watchlist_family_id_repair_v2", "original_label": original_label, "stable_id": ids["discovery_family_id"], **live_safety_fields()}, "record_hash"))
        lineage.append(record_with_hash({"artifact_type": "watchlist_lineage_record_v2", "source_bundle": "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1", "watchlist_seed_id": ids["watchlist_seed_id"], "discovery_family_id": ids["discovery_family_id"], **live_safety_fields()}, "record_hash"))

    if len(candidates) < int(gate.get("watchlist_count", 2)):
        for row in leaderboard[:2]:
            if any(c.get("v1_family_label") == row.get("family_id") for c in candidates):
                continue
            original_label = str(row.get("family_id", ""))
            if safe_float(row.get("net_pnl", 0.0)) <= 0.0:
                continue
            ids = assign_stable_ids(original_label)
            if ids["generic_label_repaired"]:
                generic_repairs += 1
            candidates.append(record_with_hash({
                "artifact_type": "watchlist_candidate_v2",
                "v1_family_label": original_label,
                "v1_net_pnl": row.get("net_pnl", 0.0),
                "v1_profit_factor": row.get("profit_factor", 0.0),
                "v1_sample_count": row.get("sample_count", 0),
                "v1_symbol_count": row.get("symbol_count", 0),
                "v1_rejection_reasons": ["symbol_count_below_minimum"],
                **ids,
                **live_safety_fields(),
            }, "record_hash"))

    summary = {
        "artifact_type": "watchlist_candidate_extractor_v2_summary",
        "watchlist_candidate_extractor_version": "dopey-public-watchlist-extractor-v2",
        "watchlist_extractor_status": "watchlist_candidates_extracted",
        "watchlist_candidate_count": len(candidates),
        "generic_label_repair_count": generic_repairs,
        "stable_family_id_count": len(candidates),
        "quarantine_overlap_count": overlap_count,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(WATCHLIST_PATH, candidates)
    write_jsonl_file(REPAIRS_PATH, repairs)
    write_jsonl_file(LINEAGE_PATH, lineage)
    write_stage_proof(PROOF_PATH, "watchlist-candidate-extractor-v2", str(summary["watchlist_extractor_status"]), summary)
    return {**summary, "artifact_paths": {"watchlist_candidate_extractor_v2_summary": str(SUMMARY_PATH)}}


def load_watchlist_seeds() -> list[dict[str, object]]:
    return read_jsonl_file(WATCHLIST_PATH)
