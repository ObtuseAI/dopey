"""Public signal research scoreboard V3."""
from __future__ import annotations

import csv

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import RESEARCH_ROOT as V1_ROOT
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import SCOREBOARD_ROOT, read_json_file, record_with_hash, write_jsonl_file
from dopey_scoreboard.public_signal_research_dashboard_v3 import (
    render_public_signal_research_dashboard_markdown_v3,
    render_public_signal_research_dashboard_v3,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v3.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_rows_v3.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v3.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v3.md"
QUALITY_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_quality_flags_v3.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v3_proof.jsonl"


def run_public_signal_research_scoreboard_v3() -> dict[str, object]:
    v1 = read_json_file(V1_ROOT / "research_candidate_generator_v1_summary.json")
    v2 = read_json_file(RESEARCH_V2_ROOT / "research_candidate_generator_v2_summary.json")
    v2_tournament = read_json_file(RESEARCH_V2_ROOT / "research_tournament_v2_summary.json")
    v3_candidates = read_json_file(RESEARCH_V3_ROOT / "research_candidate_generator_v3_summary.json")
    v3_tournament = read_json_file(RESEARCH_V3_ROOT / "research_tournament_v3_summary.json")
    v3_gate = read_json_file(RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_summary.json")
    v3_mutation_exec = read_json_file(RESEARCH_V3_ROOT / "research_mutation_queue_executor_v3_summary.json")
    v3_mutation = read_json_file(RESEARCH_V3_ROOT / "research_mutation_queue_v3_summary.json")
    v3_templates = read_json_file(RESEARCH_V3_ROOT / "stable_family_template_repair_v3_summary.json")
    return build_public_signal_research_scoreboard_v3(
        v1, v2, v2_tournament, v3_candidates, v3_tournament, v3_gate, v3_mutation_exec, v3_mutation, v3_templates
    )


def build_public_signal_research_scoreboard_v3(
    v1, v2, v2_tournament, v3_candidates, v3_tournament, v3_gate, v3_mutation_exec, v3_mutation, v3_templates
) -> dict[str, object]:
    rows = [
        {
            "family_id": v3_tournament.get("top_family", ""),
            "net_pnl": v3_tournament.get("top_net_pnl", 0.0),
            "profit_factor": v3_tournament.get("top_profit_factor", 0.0),
            "symbol_count": v3_tournament.get("top_symbol_count", 0),
            "sector_count": v3_tournament.get("top_sector_count", 0),
            "improved_vs_v2": v3_tournament.get("improved_vs_v2_count", 0),
        }
    ]
    scoreboard = {
        "artifact_type": "public_signal_research_scoreboard_v3",
        "public_signal_research_scoreboard_v3_version": "dopey-public-signal-research-scoreboard-v3",
        "scoreboard_status": "public_signal_research_scoreboard_written_v3",
        "v1_symbol_count": v1.get("symbol_count", 0),
        "v2_symbol_count": v2.get("symbol_count", 0),
        "v3_symbol_count": v3_candidates.get("symbol_count", 0),
        "v2_top_profit_factor": v2_tournament.get("top_profit_factor", 0.0),
        "v3_top_profit_factor": v3_tournament.get("top_profit_factor", 0.0),
        "executed_mutation_count": v3_mutation_exec.get("executed_mutation_count", 0),
        "input_mutation_count": v3_mutation_exec.get("input_mutation_count", 0),
        "continuation_template_enabled": v3_templates.get("continuation_template_enabled", False),
        "volume_template_enabled": v3_templates.get("volume_template_enabled", False),
        "continuation_candidate_count": v3_candidates.get("continuation_candidate_count", 0),
        "volume_candidate_count": v3_candidates.get("volume_candidate_count", 0),
        "breakthrough_candidate_count": v3_gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": v3_gate.get("watchlist_count", 0),
        "mutation_queue_count": v3_mutation.get("mutation_queue_count", 0),
        "top_family": v3_tournament.get("top_family", ""),
        "top_net_pnl": v3_tournament.get("top_net_pnl", 0.0),
        "improved_vs_v2_count": v3_tournament.get("improved_vs_v2_count", 0),
        "live_gate_status": "disabled_live_gate_locked",
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_csv_rows(rows)
    HTML_PATH.write_text(render_public_signal_research_dashboard_v3(summary), encoding="utf-8")
    MD_PATH.write_text(render_public_signal_research_dashboard_markdown_v3(summary), encoding="utf-8")
    write_jsonl_file(
        QUALITY_PATH,
        [record_with_hash({"artifact_type": "public_signal_research_scoreboard_quality_flag_v3", "flag_id": "live_trading_disabled", "passed": True, **live_safety_fields()}, "record_hash")],
    )
    write_stage_proof(PROOF_PATH, "public-signal-research-scoreboard-v3", str(summary["scoreboard_status"]), summary)
    return {**summary, "artifact_paths": {"public_signal_research_scoreboard_v3": str(SCOREBOARD_PATH)}}


def write_csv_rows(rows: list[dict[str, object]]) -> None:
    fieldnames = ["family_id", "net_pnl", "profit_factor", "symbol_count", "sector_count", "improved_vs_v2"]
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
