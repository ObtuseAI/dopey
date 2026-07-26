"""Full orchestrator for DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.champion_repair_common import (
    REPAIR_ROOT,
    REPAIR_VERSION,
    repair_proof_record,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, sha256_file, write_json_file, write_jsonl_file
from dopey_champion.run_conditional_champion_repair_planner_v1 import run_conditional_champion_repair_planner_v1
from dopey_champion.run_conditional_champion_retune_hardening_gate_v1 import run_conditional_champion_retune_hardening_gate_v1
from dopey_champion.run_demoted_champion_salvage_analyzer_v1 import run_demoted_champion_salvage_analyzer_v1
from dopey_live_gate.run_public_champion_repair_live_gate_status_v1 import run_public_champion_repair_live_gate_status_v1
from dopey_options_engine.run_conditional_champion_retune_path_simulator_v1 import run_conditional_champion_retune_path_simulator_v1
from dopey_scoreboard.run_public_champion_repair_scoreboard_v1 import run_public_champion_repair_scoreboard_v1
from dopey_signal_engine.run_conditional_champion_signal_retune_v1 import run_conditional_champion_signal_retune_v1
from dopey_tournament.run_conditional_champion_retune_tournament_v1 import run_conditional_champion_retune_tournament_v1
from dopey_validation.run_public_champion_artifact_guard_v1 import run_public_champion_artifact_guard_v1
from dopey_validation.run_public_champion_repair_preflight_v1 import run_public_champion_repair_preflight_v1
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


SUMMARY_PATH = REPAIR_ROOT / "public_champion_repair_and_retune_v1_summary.json"
STEPS_PATH = REPAIR_ROOT / "public_champion_repair_and_retune_v1_steps.jsonl"
QUALITY_FLAGS_PATH = REPAIR_ROOT / "public_champion_repair_and_retune_v1_quality_flags.jsonl"
PROOF_PATH = REPAIR_ROOT / "public_champion_repair_and_retune_v1_proof.jsonl"
VALIDATION_SUMMARY_PATH = REPAIR_ROOT / "public_champion_repair_and_retune_v1_validation_summary.json"
TIMEOUT_RECORDS_PATH = REPAIR_ROOT / "public_champion_repair_and_retune_v1_timeout_records.jsonl"
REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1_COMMANDS.md"
HANDOFF_FOLDER = "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1"


def run_public_champion_repair_and_retune_v1() -> dict[str, object]:
    REPAIR_ROOT.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []

    preflight = run_public_champion_repair_preflight_v1()
    steps.append(record_step("public_champion_repair_preflight_v1", preflight))
    guard = run_public_champion_artifact_guard_v1()
    steps.append(record_step("public_champion_artifact_guard_v1", guard))
    planner = run_conditional_champion_repair_planner_v1()
    steps.append(record_step("conditional_champion_repair_planner_v1", planner))
    retune = run_conditional_champion_signal_retune_v1()
    steps.append(record_step("conditional_champion_signal_retune_v1", retune))
    simulator = run_conditional_champion_retune_path_simulator_v1()
    steps.append(record_step("conditional_champion_retune_path_simulator_v1", simulator))
    tournament = run_conditional_champion_retune_tournament_v1()
    steps.append(record_step("conditional_champion_retune_tournament_v1", tournament))
    gate = run_conditional_champion_retune_hardening_gate_v1()
    steps.append(record_step("conditional_champion_retune_hardening_gate_v1", gate))
    salvage = run_demoted_champion_salvage_analyzer_v1()
    steps.append(record_step("demoted_champion_salvage_analyzer_v1", salvage))
    scoreboard = run_public_champion_repair_scoreboard_v1()
    steps.append(record_step("public_champion_repair_scoreboard_v1", scoreboard))
    live_gate = run_public_champion_repair_live_gate_status_v1()
    steps.append(record_step("public_champion_repair_live_gate_status_v1", live_gate))
    validation = write_validation_summary("pending_watchdog_validation")
    steps.append(record_step("validation_summary", validation))
    docs = write_bundle_docs(preflight, guard, planner, retune, simulator, tournament, gate, salvage, scoreboard, live_gate, validation)
    steps.append(record_step("docs", docs))
    handoff = copy_shared_handoff(build_handoff_file_list())
    steps.append(record_step("shared_handoff", handoff))

    status = repair_status(preflight, guard, gate)
    summary = build_orchestrator_summary(status, preflight, guard, planner, retune, simulator, tournament, gate, salvage, scoreboard, live_gate, handoff)
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(QUALITY_FLAGS_PATH, [])
    if not TIMEOUT_RECORDS_PATH.exists():
        write_jsonl_file(TIMEOUT_RECORDS_PATH, [])
    write_jsonl_file(PROOF_PATH, [repair_proof_record("public-champion-repair-and-retune-v1", status, summary)])
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def record_step(step_id: str, result: dict[str, object]) -> dict[str, object]:
    status = (
        result.get("public_champion_repair_preflight_status")
        or result.get("artifact_guard_status")
        or result.get("conditional_champion_repair_planner_status")
        or result.get("conditional_champion_signal_retune_status")
        or result.get("conditional_champion_retune_path_status")
        or result.get("conditional_champion_retune_tournament_status")
        or result.get("conditional_champion_retune_hardening_status")
        or result.get("demoted_champion_salvage_status")
        or result.get("scoreboard_status")
        or result.get("live_gate_status")
        or result.get("validation_status")
        or "ok"
    )
    return record_with_hash({"artifact_type": "public_champion_repair_and_retune_v1_step", "step_id": step_id, "status": status, "summary_hash": result.get("summary_hash", ""), "live_trading_enabled": False}, "record_hash")


def repair_status(preflight: dict[str, object], guard: dict[str, object], gate: dict[str, object]) -> str:
    if str(preflight.get("public_champion_repair_preflight_status", "")) != "ready_for_repair_and_retune":
        return "public_champion_repair_preflight_blocked"
    if str(guard.get("artifact_guard_status", "")) == "artifact_guard_shrinkage_unresolved":
        return "artifact_guard_failed"
    gate_status = str(gate.get("conditional_champion_retune_hardening_status", ""))
    if gate_status == "retuned_hardened_champions_found":
        return "retuned_hardened_champions_found_live_gate_locked"
    if gate_status == "conditional_champions_improved_require_more_repair":
        return "conditional_champions_improved_require_more_repair"
    return "conditional_champions_demoted_after_retune"


def next_recommended_target(status: str) -> str:
    if status == "retuned_hardened_champions_found_live_gate_locked":
        return "DOPEY_HARDENED_PUBLIC_CHAMPION_EXTENDED_PAPER_SHADOW_V1"
    if status == "conditional_champions_improved_require_more_repair":
        return "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V2"
    if status == "artifact_guard_failed":
        return "DOPEY_PUBLIC_CHAMPION_ARTIFACT_GUARD_REPAIR_V1"
    return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1"


def build_orchestrator_summary(status, preflight, guard, planner, retune, simulator, tournament, gate, salvage, scoreboard, live_gate, handoff) -> dict[str, object]:
    return {
        "artifact_type": "public_champion_repair_and_retune_v1_summary",
        "public_champion_repair_version": REPAIR_VERSION,
        "public_champion_repair_status": status,
        "preflight_status": preflight.get("public_champion_repair_preflight_status"),
        "artifact_guard_status": guard.get("artifact_guard_status"),
        "conditional_champion_count": preflight.get("conditional_champion_count", 0),
        "retune_candidate_count": retune.get("retune_candidate_count", 0),
        "retune_simulated_trade_count": simulator.get("simulated_trade_count", 0),
        "retuned_hardened_count": gate.get("retuned_hardened_count", 0),
        "retuned_conditional_count": gate.get("retuned_conditional_count", 0),
        "retuned_demoted_count": gate.get("retuned_demoted_count", 0),
        "retuned_hardened_names": gate.get("retuned_hardened_names", []),
        "retuned_conditional_names": gate.get("retuned_conditional_names", []),
        "retuned_demoted_names": gate.get("retuned_demoted_names", []),
        "salvage_candidate_count": salvage.get("salvage_candidate_count", 0),
        "kill_confirmed_count": salvage.get("kill_confirmed_count", 0),
        "repair_plan_count": planner.get("repair_plan_count", 0),
        "improved_candidate_count": tournament.get("improved_candidate_count", 0),
        "live_gate_status": live_gate.get("live_gate_status"),
        "shared_copy_status": handoff.get("shared_copy_status", "not_attempted"),
        "next_recommended_target": next_recommended_target(status),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def write_validation_summary(validation_status: str) -> dict[str, object]:
    summary = {"artifact_type": "public_champion_repair_and_retune_v1_validation_summary", "validation_status": validation_status, "timeout_recorded_as_pass": False, "targeted_test_command": ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_champion_repair_and_retune_v1.py -q", **live_safety_fields()}
    return write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)


def write_bundle_docs(*args) -> dict[str, object]:
    REPORT_PATH.write_text("# DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1_REPORT\n\nRepair and retune bundle for conditional champions. Live gate locked.\n", encoding="utf-8")
    LEDGER_PATH.write_text("# DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1_ARTIFACT_LEDGER\n\n- artifacts/dopey/champion_repair/\n", encoding="utf-8")
    COMMANDS_PATH.write_text("# DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1_COMMANDS\n\n- `.\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_champion_repair_and_retune_v1`\n", encoding="utf-8")
    return {"artifact_type": "public_champion_repair_docs", "live_trading_enabled": False}


def build_handoff_file_list() -> list[Path]:
    paths = [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        SUMMARY_PATH,
        VALIDATION_SUMMARY_PATH,
        TIMEOUT_RECORDS_PATH,
        REPAIR_ROOT / "public_champion_repair_preflight_v1_summary.json",
        REPAIR_ROOT / "public_champion_artifact_guard_v1_summary.json",
        REPAIR_ROOT / "conditional_champion_repair_planner_v1_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "signals" / "conditional_champion_signal_retune_v1_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "options_engine" / "conditional_champion_retune_path_simulator_v1_summary.json",
        REPAIR_ROOT / "conditional_champion_retune_tournament_v1_summary.json",
        REPAIR_ROOT / "conditional_champion_retune_hardening_gate_v1_summary.json",
        REPAIR_ROOT / "demoted_champion_salvage_analyzer_v1_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_champion_repair_scoreboard_v1.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_champion_repair_dashboard_v1.html",
        REPO_ROOT / "artifacts" / "dopey" / "live_gate" / "public_champion_repair_live_gate_status_v1.json",
    ]
    return [path for path in paths if path.exists()]


def copy_shared_handoff(files: list[Path]) -> dict[str, object]:
    for root in [Path("C:/Users/CH/Desktop/Shared Folder"), Path("C:/Users/chris/Desktop/Shared Folder"), Path("//FRANKENSTEIN/Shared Folder"), Path("Z:/")]:
        try:
            if not root.exists():
                continue
            target = root / HANDOFF_FOLDER
            target.mkdir(parents=True, exist_ok=True)
            copied = []
            for source in files:
                dest = target / source.name
                shutil.copy2(source, dest)
                copied.append({"source": str(source), "destination": str(dest), "sha256": sha256_file(dest)})
            manifest = {"artifact_type": "session_copy_manifest", "target_root": str(target), "copied_count": len(copied), "copied_files": copied, "live_trading_enabled": False}
            write_json_file(target / "SESSION_COPY_MANIFEST.json", manifest)
            return {"shared_copy_status": "copied", "target_root": str(target), "copied_count": len(copied)}
        except OSError:
            continue
    return {"shared_copy_status": "not_copied_no_available_target", "copied_count": 0}


def orchestrator_artifact_paths() -> dict[str, str]:
    return {"public_champion_repair_and_retune_v1_summary": str(SUMMARY_PATH), "public_champion_repair_and_retune_v1_validation_summary": str(VALIDATION_SUMMARY_PATH)}


def main() -> int:
    summary = run_public_champion_repair_and_retune_v1()
    print(json.dumps({"public_champion_repair_status": summary["public_champion_repair_status"], "retuned_hardened_count": summary["retuned_hardened_count"], "next_recommended_target": summary["next_recommended_target"], "summary_path": summary["artifact_paths"]["public_champion_repair_and_retune_v1_summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
