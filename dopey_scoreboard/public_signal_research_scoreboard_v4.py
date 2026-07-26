"""Public signal research scoreboard V4.

Copies V3 scoreboard pattern, points at V4 artifacts, includes V1/V2/V3/V4
comparison, UVXY-like corruption check, and family/subfamily separation.
"""
from __future__ import annotations

import csv

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    read_json_file,
    record_with_hash,
    write_jsonl_file,
)
from dopey_autonomy.signal_research_common import RESEARCH_ROOT as V1_ROOT
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT
from dopey_autonomy.signal_research_v4_common import (
    CANDIDATE_GENERATOR_SUMMARY_PATH,
    GATE_V4_SUMMARY_PATH,
    MUTATION_QUEUE_V4_SUMMARY_PATH,
    RESEARCH_V4_ROOT,
    TOURNAMENT_SUMMARY_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_scoreboard.public_signal_research_dashboard_v4 import (
    render_public_signal_research_dashboard_markdown_v4,
    render_public_signal_research_dashboard_v4,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v4.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_rows_v4.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v4.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v4.md"
QUALITY_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_quality_flags_v4.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v4_proof.jsonl"


def run_public_signal_research_scoreboard_v4() -> dict[str, object]:
    v1 = read_json_file(V1_ROOT / "research_candidate_generator_v1_summary.json")
    v2 = read_json_file(RESEARCH_V2_ROOT / "research_candidate_generator_v2_summary.json")
    v2_tournament = read_json_file(RESEARCH_V2_ROOT / "research_tournament_v2_summary.json")
    v3_candidates = read_json_file(RESEARCH_V3_ROOT / "research_candidate_generator_v3_summary.json")
    v3_tournament = read_json_file(RESEARCH_V3_ROOT / "research_tournament_v3_summary.json")
    v3_mutation_exec = read_json_file(RESEARCH_V3_ROOT / "research_mutation_queue_executor_v3_summary.json")
    v3_split = read_json_file(RESEARCH_V3_ROOT / "stable_family_template_repair_v3_summary.json")
    v4_candidates = read_json_file(CANDIDATE_GENERATOR_SUMMARY_PATH)
    v4_tournament = read_json_file(TOURNAMENT_SUMMARY_PATH)
    v4_gate = read_json_file(GATE_V4_SUMMARY_PATH)
    v4_mutation = read_json_file(MUTATION_QUEUE_V4_SUMMARY_PATH)
    return build_public_signal_research_scoreboard_v4(
        v1,
        v2,
        v2_tournament,
        v3_candidates,
        v3_tournament,
        v3_mutation_exec,
        v3_split,
        v4_candidates,
        v4_tournament,
        v4_gate,
        v4_mutation,
    )


def build_public_signal_research_scoreboard_v4(
    v1,
    v2,
    v2_tournament,
    v3_candidates,
    v3_tournament,
    v3_mutation_exec,
    v3_split,
    v4_candidates,
    v4_tournament,
    v4_gate,
    v4_mutation,
) -> dict[str, object]:
    rows = [
        {
            "family_id": v4_tournament.get("top_family", ""),
            "subfamily_id": v4_tournament.get("top_subfamily", ""),
            "net_pnl": v4_tournament.get("top_net_pnl", 0.0),
            "profit_factor": v4_tournament.get("top_profit_factor", 0.0),
            "symbol_count": v4_tournament.get("top_symbol_count", 0),
            "sector_count": v4_tournament.get("top_sector_count", 0),
            "improved_vs_v3": v4_tournament.get("improved_vs_v3_count", 0),
        }
    ]
    scoreboard = {
        "artifact_type": "public_signal_research_scoreboard_v4",
        "public_signal_research_scoreboard_v4_version": "dopey-public-signal-research-scoreboard-v4",
        "scoreboard_status": "public_signal_research_scoreboard_written_v4",
        "v1_symbol_count": v1.get("symbol_count", 0),
        "v2_symbol_count": v2.get("symbol_count", 0),
        "v3_symbol_count": v3_candidates.get("symbol_count", 0),
        "v4_symbol_count": v4_candidates.get("symbol_count", 0),
        "v2_top_profit_factor": v2_tournament.get("top_profit_factor", 0.0),
        "v3_top_profit_factor": v3_tournament.get("top_profit_factor", 0.0),
        "v4_top_profit_factor": v4_tournament.get("top_profit_factor", 0.0),
        "v3_executed_mutation_count": v3_mutation_exec.get("executed_mutation_count", 0),
        "v3_input_mutation_count": v3_mutation_exec.get("input_mutation_count", 0),
        "v3_continuation_template_enabled": v3_split.get("continuation_template_enabled", False),
        "v3_volume_template_enabled": v3_split.get("volume_template_enabled", False),
        "v3_continuation_candidate_count": v3_candidates.get("continuation_candidate_count", 0),
        "v3_volume_candidate_count": v3_candidates.get("volume_candidate_count", 0),
        "v4_continuation_candidate_count": v4_candidates.get("continuation_candidate_count", 0),
        "v4_volume_candidate_count": v4_candidates.get("volume_candidate_count", 0),
        "v4_subfamily_count": v4_tournament.get("subfamily_count", 0),
        "v4_family_count": v4_tournament.get("family_count", 0),
        "v4_cohort_count": v4_tournament.get("cohort_count", 0),
        "uvxy_like_corruption_detected": v4_tournament.get("uvxy_like_corruption_detected", False),
        "v4_breakthrough_candidate_count": v4_gate.get("breakthrough_candidate_count", 0),
        "v4_watchlist_count": v4_gate.get("watchlist_count", 0),
        "v4_mutation_queue_count": v4_mutation.get("mutation_queue_count", 0),
        "v4_improved_vs_v3_count": v4_tournament.get("improved_vs_v3_count", 0),
        "top_family": v4_tournament.get("top_family", ""),
        "top_subfamily": v4_tournament.get("top_subfamily", ""),
        "top_net_pnl": v4_tournament.get("top_net_pnl", 0.0),
        "live_gate_status": "disabled_live_gate_locked",
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_csv_rows(rows)
    HTML_PATH.write_text(render_public_signal_research_dashboard_v4(summary), encoding="utf-8")
    MD_PATH.write_text(render_public_signal_research_dashboard_markdown_v4(summary), encoding="utf-8")
    write_jsonl_file(
        QUALITY_PATH,
        [
            record_with_hash(
                {
                    "artifact_type": "public_signal_research_scoreboard_quality_flag_v4",
                    "flag_id": "live_trading_disabled",
                    "passed": True,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        ],
    )
    write_stage_proof(
        PROOF_PATH,
        "public-signal-research-scoreboard-v4",
        str(summary["scoreboard_status"]),
        summary,
    )
    return {**summary, "artifact_paths": {"public_signal_research_scoreboard_v4": str(SCOREBOARD_PATH)}}


def write_csv_rows(rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "family_id",
        "subfamily_id",
        "net_pnl",
        "profit_factor",
        "symbol_count",
        "sector_count",
        "improved_vs_v3",
    ]
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
