"""Public champion repair scoreboard V1."""
from __future__ import annotations

import csv

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.champion_repair_common import REPAIR_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import SCOREBOARD_ROOT, read_json_file, record_with_hash, write_jsonl_file
from dopey_scoreboard.public_champion_repair_dashboard_v1 import (
    render_public_champion_repair_dashboard_markdown_v1,
    render_public_champion_repair_dashboard_v1,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_champion_repair_scoreboard_v1.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_champion_repair_scoreboard_rows_v1.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_champion_repair_dashboard_v1.html"
MD_PATH = SCOREBOARD_ROOT / "public_champion_repair_dashboard_v1.md"
QUALITY_FLAGS_PATH = SCOREBOARD_ROOT / "public_champion_repair_scoreboard_quality_flags_v1.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_champion_repair_scoreboard_v1_proof.jsonl"


def run_public_champion_repair_scoreboard_v1() -> dict[str, object]:
    hardening = read_json_file(REPAIR_ROOT.parent / "champion_hardening" / "public_champion_hardening_gate_v1_summary.json")
    retune_gate = read_json_file(REPAIR_ROOT / "conditional_champion_retune_hardening_gate_v1_summary.json")
    salvage = read_json_file(REPAIR_ROOT / "demoted_champion_salvage_analyzer_v1_summary.json")
    comparison = __import__("dopey_autonomy.public_champion_common", fromlist=["read_jsonl_file"]).read_jsonl_file(
        REPAIR_ROOT / "conditional_champion_before_after_comparison_v1.jsonl"
    )
    return build_public_champion_repair_scoreboard_v1(hardening, retune_gate, salvage, comparison)


def build_public_champion_repair_scoreboard_v1(hardening, retune_gate, salvage, comparison) -> dict[str, object]:
    rows = [{
        "parent_champion_id": row.get("parent_champion_id", ""),
        "before_net_pnl": row.get("before_net_pnl", 0.0),
        "after_net_pnl": row.get("after_net_pnl", 0.0),
        "improvement_score": row.get("improvement_score", 0.0),
    } for row in comparison]
    scoreboard = {
        "artifact_type": "public_champion_repair_scoreboard_v1",
        "public_champion_repair_scoreboard_version": "dopey-public-champion-repair-scoreboard-v1",
        "scoreboard_status": "public_champion_repair_scoreboard_written",
        "original_champion_count": hardening.get("input_public_champion_count", 0),
        "conditional_champion_names": hardening.get("conditional_champion_names", []),
        "demoted_champion_names": hardening.get("demoted_champion_names", []),
        "retuned_hardened_names": retune_gate.get("retuned_hardened_names", []),
        "retuned_conditional_names": retune_gate.get("retuned_conditional_names", []),
        "retuned_demoted_names": retune_gate.get("retuned_demoted_names", []),
        "salvage_candidate_count": salvage.get("salvage_candidate_count", 0),
        "kill_confirmed_count": salvage.get("kill_confirmed_count", 0),
        "before_after_rows": rows,
        "live_gate_status": "disabled_live_gate_locked",
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_csv_rows(rows)
    HTML_PATH.write_text(render_public_champion_repair_dashboard_v1(summary), encoding="utf-8")
    MD_PATH.write_text(render_public_champion_repair_dashboard_markdown_v1(summary), encoding="utf-8")
    write_jsonl_file(QUALITY_FLAGS_PATH, [record_with_hash({"artifact_type": "public_champion_repair_scoreboard_quality_flag_v1", "flag_id": "live_trading_disabled", "passed": True, **live_safety_fields()}, "record_hash")])
    write_stage_proof(PROOF_PATH, "public-champion-repair-scoreboard-v1", str(summary["scoreboard_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def write_csv_rows(rows: list[dict[str, object]]) -> None:
    fieldnames = ["parent_champion_id", "before_net_pnl", "after_net_pnl", "improvement_score"]
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def artifact_paths() -> dict[str, str]:
    return {"public_champion_repair_scoreboard_v1": str(SCOREBOARD_PATH)}
