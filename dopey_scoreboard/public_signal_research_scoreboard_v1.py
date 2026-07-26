"""Public signal research scoreboard V1."""
from __future__ import annotations

import csv

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import RESEARCH_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import SCOREBOARD_ROOT, read_json_file, record_with_hash, write_jsonl_file
from dopey_scoreboard.public_signal_research_dashboard_v1 import (
    render_public_signal_research_dashboard_markdown_v1,
    render_public_signal_research_dashboard_v1,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v1.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_rows_v1.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v1.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v1.md"
QUALITY_FLAGS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_quality_flags_v1.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v1_proof.jsonl"


def run_public_signal_research_scoreboard_v1() -> dict[str, object]:
    feature = read_json_file(RESEARCH_ROOT / "public_feature_miner_v1_summary.json")
    candidates = read_json_file(RESEARCH_ROOT / "research_candidate_generator_v1_summary.json")
    tournament = read_json_file(RESEARCH_ROOT / "research_tournament_v1_summary.json")
    gate = read_json_file(RESEARCH_ROOT / "research_breakthrough_gate_v1_summary.json")
    quarantine = read_json_file(RESEARCH_ROOT / "failed_champion_family_quarantine_v1_summary.json")
    mutation = read_json_file(RESEARCH_ROOT / "research_mutation_queue_v1_summary.json")
    return build_public_signal_research_scoreboard_v1(feature, candidates, tournament, gate, quarantine, mutation)


def build_public_signal_research_scoreboard_v1(feature, candidates, tournament, gate, quarantine, mutation) -> dict[str, object]:
    rows = [{
        "family_id": tournament.get("top_family", ""),
        "net_pnl": tournament.get("top_net_pnl", 0.0),
        "profit_factor": tournament.get("top_profit_factor", 0.0),
        "sample_count": tournament.get("top_sample_count", 0),
    }]
    scoreboard = {
        "artifact_type": "public_signal_research_scoreboard_v1",
        "public_signal_research_scoreboard_version": "dopey-public-signal-research-scoreboard-v1",
        "scoreboard_status": "public_signal_research_scoreboard_written",
        "feature_count": feature.get("feature_count", 0),
        "candidate_count": candidates.get("candidate_count", 0),
        "family_count": tournament.get("family_count", 0),
        "breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": gate.get("watchlist_count", 0),
        "quarantined_family_count": quarantine.get("quarantined_family_count", 0),
        "mutation_queue_count": mutation.get("mutation_queue_count", 0),
        "top_family": tournament.get("top_family", ""),
        "top_net_pnl": tournament.get("top_net_pnl", 0.0),
        "live_gate_status": "disabled_live_gate_locked",
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_csv_rows(rows)
    HTML_PATH.write_text(render_public_signal_research_dashboard_v1(summary), encoding="utf-8")
    MD_PATH.write_text(render_public_signal_research_dashboard_markdown_v1(summary), encoding="utf-8")
    write_jsonl_file(QUALITY_FLAGS_PATH, [record_with_hash({"artifact_type": "public_signal_research_scoreboard_quality_flag_v1", "flag_id": "live_trading_disabled", "passed": True, **live_safety_fields()}, "record_hash")])
    write_stage_proof(PROOF_PATH, "public-signal-research-scoreboard-v1", str(summary["scoreboard_status"]), summary)
    return {**summary, "artifact_paths": {"public_signal_research_scoreboard_v1": str(SCOREBOARD_PATH)}}


def write_csv_rows(rows: list[dict[str, object]]) -> None:
    fieldnames = ["family_id", "net_pnl", "profit_factor", "sample_count"]
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
