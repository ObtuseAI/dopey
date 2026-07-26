"""Public champion hardening scoreboard V1."""
from __future__ import annotations

import csv

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    live_safety_fields,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
)
from dopey_scoreboard.public_champion_hardening_dashboard_v1 import (
    render_public_champion_hardening_dashboard_markdown_v1,
    render_public_champion_hardening_dashboard_v1,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_champion_hardening_scoreboard_v1.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_champion_hardening_scoreboard_rows_v1.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_champion_hardening_dashboard_v1.html"
MD_PATH = SCOREBOARD_ROOT / "public_champion_hardening_dashboard_v1.md"
QUALITY_FLAGS_PATH = SCOREBOARD_ROOT / "public_champion_hardening_scoreboard_quality_flags_v1.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_champion_hardening_scoreboard_v1_proof.jsonl"

GATE_SUMMARY_PATH = HARDENING_ROOT / "public_champion_hardening_gate_v1_summary.json"
STRESS_SUMMARY_PATH = HARDENING_ROOT / "public_champion_deep_stress_matrix_v1_summary.json"
HOLDOUT_SUMMARY_PATH = HARDENING_ROOT / "public_champion_holdout_expansion_v1_summary.json"
DECAY_SUMMARY_PATH = HARDENING_ROOT / "public_champion_decay_monitor_v1_summary.json"
REPAIR_SUMMARY_PATH = HARDENING_ROOT / "public_champion_hardening_repair_summary_v1.json"
GATE_RESULTS_PATH = HARDENING_ROOT / "public_champion_hardening_gate_results_v1.jsonl"


def run_public_champion_hardening_scoreboard_v1() -> dict[str, object]:
    gate_summary = read_json_file(GATE_SUMMARY_PATH)
    stress_summary = read_json_file(STRESS_SUMMARY_PATH)
    holdout_summary = read_json_file(HOLDOUT_SUMMARY_PATH)
    decay_summary = read_json_file(DECAY_SUMMARY_PATH)
    repair_summary = read_json_file(REPAIR_SUMMARY_PATH)
    gate_results = read_jsonl_file(GATE_RESULTS_PATH)
    return build_public_champion_hardening_scoreboard_v1(
        gate_summary, stress_summary, holdout_summary, decay_summary, repair_summary, gate_results,
    )


def build_public_champion_hardening_scoreboard_v1(
    gate_summary: dict[str, object],
    stress_summary: dict[str, object],
    holdout_summary: dict[str, object],
    decay_summary: dict[str, object],
    repair_summary: dict[str, object],
    gate_results: list[dict[str, object]],
) -> dict[str, object]:
    rows = [
        {
            "champion_name": result.get("champion_name", ""),
            "hardening_status": result.get("hardening_status", ""),
            "core_stress_survival_rate": result.get("core_stress_survival_rate", 0.0),
            "holdout_survival_rate": result.get("holdout_survival_rate", 0.0),
            "decay_alert_count": result.get("decay_alert_count", 0),
        }
        for result in gate_results
    ]
    scoreboard = {
        "artifact_type": "public_champion_hardening_scoreboard_v1",
        "public_champion_hardening_scoreboard_version": "dopey-public-champion-hardening-scoreboard-v1",
        "scoreboard_status": "public_champion_hardening_scoreboard_written",
        "original_champion_names": gate_summary.get("input_public_champion_count", 0),
        "original_champion_count": gate_summary.get("input_public_champion_count", 0),
        "hardened_champion_names": gate_summary.get("hardened_champion_names", []),
        "conditional_champion_names": gate_summary.get("conditional_champion_names", []),
        "demoted_champion_names": gate_summary.get("demoted_champion_names", []),
        "stress_survival_matrix": stress_summary.get("champion_core_survival", {}),
        "holdout_performance": holdout_summary.get("champion_holdout_survival_counts", {}),
        "decay_alerts": decay_summary.get("decay_alert_count", 0),
        "top_failure_reasons": stress_summary.get("top_failure_reasons", {}),
        "repair_queue_count": repair_summary.get("repair_queue_count", 0),
        "live_gate_status": "disabled_live_gate_locked",
        "public_data_only": True,
        **live_safety_fields(),
    }
    scoreboard["original_champion_names"] = [
        *gate_summary.get("hardened_champion_names", []),
        *gate_summary.get("conditional_champion_names", []),
        *gate_summary.get("demoted_champion_names", []),
    ]
    summary = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_csv_rows(rows)
    HTML_PATH.write_text(render_public_champion_hardening_dashboard_v1(summary), encoding="utf-8")
    MD_PATH.write_text(render_public_champion_hardening_dashboard_markdown_v1(summary), encoding="utf-8")
    quality_flags = [
        record_with_hash({
            "artifact_type": "public_champion_hardening_scoreboard_quality_flag_v1",
            "flag_id": "live_trading_disabled",
            "passed": summary.get("live_trading_enabled") is False,
            **live_safety_fields(),
        }, "record_hash"),
    ]
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(PROOF_PATH, "public-champion-hardening-scoreboard-v1", str(summary["scoreboard_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def write_csv_rows(rows: list[dict[str, object]]) -> None:
    fieldnames = ["champion_name", "hardening_status", "core_stress_survival_rate", "holdout_survival_rate", "decay_alert_count"]
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_hardening_scoreboard_v1": str(SCOREBOARD_PATH),
        "public_champion_hardening_scoreboard_rows_v1": str(ROWS_PATH),
        "public_champion_hardening_dashboard_v1_html": str(HTML_PATH),
        "public_champion_hardening_dashboard_v1_md": str(MD_PATH),
        "public_champion_hardening_scoreboard_quality_flags_v1": str(QUALITY_FLAGS_PATH),
        "public_champion_hardening_scoreboard_v1_proof": str(PROOF_PATH),
    }
