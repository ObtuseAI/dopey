"""Public signal research scoreboard V2."""
from __future__ import annotations

import csv

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import RESEARCH_ROOT as V1_ROOT
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import SCOREBOARD_ROOT, read_json_file, record_with_hash, write_jsonl_file
from dopey_scoreboard.public_signal_research_dashboard_v2 import (
    render_public_signal_research_dashboard_markdown_v2,
    render_public_signal_research_dashboard_v2,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v2.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_rows_v2.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v2.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v2.md"
QUALITY_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_quality_flags_v2.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v2_proof.jsonl"


def run_public_signal_research_scoreboard_v2() -> dict[str, object]:
    v1_candidates = read_json_file(V1_ROOT / "research_candidate_generator_v1_summary.json")
    v2_candidates = read_json_file(RESEARCH_V2_ROOT / "research_candidate_generator_v2_summary.json")
    tournament = read_json_file(RESEARCH_V2_ROOT / "research_tournament_v2_summary.json")
    gate = read_json_file(RESEARCH_V2_ROOT / "research_breakthrough_gate_v2_summary.json")
    mutation = read_json_file(RESEARCH_V2_ROOT / "research_mutation_queue_v2_summary.json")
    extractor = read_json_file(RESEARCH_V2_ROOT / "watchlist_candidate_extractor_v2_summary.json")
    density = read_json_file(RESEARCH_V2_ROOT / "symbol_sector_density_scheduler_v2_summary.json")
    return build_public_signal_research_scoreboard_v2(v1_candidates, v2_candidates, tournament, gate, mutation, extractor, density)


def build_public_signal_research_scoreboard_v2(v1, v2, tournament, gate, mutation, extractor, density) -> dict[str, object]:
    rows = [{
        "family_id": tournament.get("top_family", ""),
        "net_pnl": tournament.get("top_net_pnl", 0.0),
        "profit_factor": tournament.get("top_profit_factor", 0.0),
        "symbol_count": tournament.get("top_symbol_count", 0),
        "sector_count": tournament.get("top_sector_count", 0),
    }]
    scoreboard = {
        "artifact_type": "public_signal_research_scoreboard_v2",
        "public_signal_research_scoreboard_v2_version": "dopey-public-signal-research-scoreboard-v2",
        "scoreboard_status": "public_signal_research_scoreboard_written_v2",
        "v1_symbol_count": v1.get("symbol_count", 0),
        "v1_sector_count": v1.get("sector_count", 0),
        "v2_symbol_count": v2.get("symbol_count", 0),
        "v2_sector_count": v2.get("sector_count", 0),
        "watchlist_candidate_count": extractor.get("watchlist_candidate_count", 0),
        "stable_family_id_count": extractor.get("stable_family_id_count", 0),
        "covered_symbol_count": density.get("covered_symbol_count", 0),
        "covered_sector_count": density.get("covered_sector_count", 0),
        "breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": gate.get("watchlist_count", 0),
        "mutation_queue_count": mutation.get("mutation_queue_count", 0),
        "top_family": tournament.get("top_family", ""),
        "top_net_pnl": tournament.get("top_net_pnl", 0.0),
        "live_gate_status": "disabled_live_gate_locked",
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_csv_rows(rows)
    HTML_PATH.write_text(render_public_signal_research_dashboard_v2(summary), encoding="utf-8")
    MD_PATH.write_text(render_public_signal_research_dashboard_markdown_v2(summary), encoding="utf-8")
    write_jsonl_file(QUALITY_PATH, [record_with_hash({"artifact_type": "public_signal_research_scoreboard_quality_flag_v2", "flag_id": "live_trading_disabled", "passed": True, **live_safety_fields()}, "record_hash")])
    write_stage_proof(PROOF_PATH, "public-signal-research-scoreboard-v2", str(summary["scoreboard_status"]), summary)
    return {**summary, "artifact_paths": {"public_signal_research_scoreboard_v2": str(SCOREBOARD_PATH)}}


def write_csv_rows(rows: list[dict[str, object]]) -> None:
    fieldnames = ["family_id", "net_pnl", "profit_factor", "symbol_count", "sector_count"]
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
