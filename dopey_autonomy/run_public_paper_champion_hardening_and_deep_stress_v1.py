"""Full orchestrator for DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    HARDENING_VERSION,
    hardening_proof_record,
    live_safety_fields,
    robinhood_policy_fields,
)
from dopey_autonomy.public_champion_common import (
    proof_record,
    read_jsonl_file,
    record_with_hash,
    sha256_file,
    write_json_file,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_champion.run_public_champion_decay_monitor_v1 import run_public_champion_decay_monitor_v1
from dopey_champion.run_public_champion_deep_stress_matrix_v1 import run_public_champion_deep_stress_matrix_v1
from dopey_champion.run_public_champion_hardening_gate_v1 import run_public_champion_hardening_gate_v1
from dopey_champion.run_public_champion_holdout_expansion_v1 import run_public_champion_holdout_expansion_v1
from dopey_champion.run_public_champion_inventory_v1 import run_public_champion_inventory_v1
from dopey_evolution.run_public_champion_hardening_repair_queue_v1 import run_public_champion_hardening_repair_queue_v1
from dopey_live_gate.run_public_champion_hardening_live_gate_status_v3 import run_public_champion_hardening_live_gate_status_v3
from dopey_market_intake.run_public_lake_final_state_lock_v2 import run_public_lake_final_state_lock_v2
from dopey_scoreboard.run_public_champion_hardening_scoreboard_v1 import run_public_champion_hardening_scoreboard_v1
from dopey_signal_engine.run_public_signal_artifact_cleaner_v1 import run_public_signal_artifact_cleaner_v1
from dopey_validation.run_champion_hardening_preflight import run_champion_hardening_preflight
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


SUMMARY_PATH = HARDENING_ROOT / "public_paper_champion_hardening_and_deep_stress_v1_summary.json"
STEPS_PATH = HARDENING_ROOT / "public_paper_champion_hardening_and_deep_stress_v1_steps.jsonl"
QUALITY_FLAGS_PATH = HARDENING_ROOT / "public_paper_champion_hardening_and_deep_stress_v1_quality_flags.jsonl"
PROOF_PATH = HARDENING_ROOT / "public_paper_champion_hardening_and_deep_stress_v1_proof.jsonl"
VALIDATION_SUMMARY_PATH = HARDENING_ROOT / "public_paper_champion_hardening_and_deep_stress_v1_validation_summary.json"
TIMEOUT_RECORDS_PATH = HARDENING_ROOT / "public_paper_champion_hardening_and_deep_stress_v1_timeout_records.jsonl"

REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1_COMMANDS.md"
HANDOFF_FOLDER_NAME = "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1"


def run_public_paper_champion_hardening_and_deep_stress_v1() -> dict[str, object]:
    HARDENING_ROOT.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []

    preflight = run_champion_hardening_preflight()
    steps.append(record_step("champion_hardening_preflight", preflight))

    cleaner = run_public_signal_artifact_cleaner_v1()
    steps.append(record_step("public_signal_artifact_cleaner_v1", cleaner))

    lake = run_public_lake_final_state_lock_v2()
    steps.append(record_step("public_lake_final_state_lock_v2", lake))

    inventory = run_public_champion_inventory_v1()
    steps.append(record_step("public_champion_inventory_v1", inventory))

    stress = run_public_champion_deep_stress_matrix_v1()
    steps.append(record_step("public_champion_deep_stress_matrix_v1", stress))

    holdout = run_public_champion_holdout_expansion_v1()
    steps.append(record_step("public_champion_holdout_expansion_v1", holdout))

    decay = run_public_champion_decay_monitor_v1()
    steps.append(record_step("public_champion_decay_monitor_v1", decay))

    gate = run_public_champion_hardening_gate_v1()
    steps.append(record_step("public_champion_hardening_gate_v1", gate))

    repair = run_public_champion_hardening_repair_queue_v1()
    steps.append(record_step("public_champion_hardening_repair_queue_v1", repair))

    scoreboard = run_public_champion_hardening_scoreboard_v1()
    steps.append(record_step("public_champion_hardening_scoreboard_v1", scoreboard))

    live_gate = run_public_champion_hardening_live_gate_status_v3()
    steps.append(record_step("public_champion_hardening_live_gate_status_v3", live_gate))

    validation = write_validation_summary("pending_watchdog_validation")
    steps.append(record_step("validation_summary", validation))

    docs = write_bundle_docs(preflight, cleaner, inventory, stress, holdout, decay, gate, repair, scoreboard, live_gate, validation)
    steps.append(record_step("audit_report_export_review_docs", docs))

    handoff = copy_shared_handoff(build_handoff_file_list())
    steps.append(record_step("shared_handoff", handoff))

    if int(cleaner.get("simv2_rows_remaining", 0)) != 0:
        quality_flags.append(record_with_hash({
            "artifact_type": "public_champion_hardening_quality_flag",
            "flag_id": "simv2_rows_remaining_in_signal_candidates",
            "severity": "warning",
            "value": cleaner.get("simv2_rows_remaining", 0),
            **live_safety_fields(),
        }, "record_hash"))

    status = hardening_status(gate, lake, preflight)
    summary = build_orchestrator_summary(
        status, preflight, cleaner, inventory, stress, holdout, decay, gate, repair, scoreboard, live_gate, handoff,
    )
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    if not TIMEOUT_RECORDS_PATH.exists():
        write_jsonl_file(TIMEOUT_RECORDS_PATH, [])
    write_jsonl_file(PROOF_PATH, [hardening_proof_record("public-paper-champion-hardening-and-deep-stress-v1", status, summary)])
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def record_step(step_id: str, result: dict[str, object]) -> dict[str, object]:
    status = (
        result.get("champion_hardening_preflight_status")
        or result.get("signal_artifact_cleaner_status")
        or result.get("public_lake_final_state_status")
        or result.get("public_champion_inventory_status")
        or result.get("deep_stress_status")
        or result.get("holdout_expansion_status")
        or result.get("decay_monitor_status")
        or result.get("champion_hardening_gate_status")
        or result.get("repair_queue_status")
        or result.get("scoreboard_status")
        or result.get("live_gate_status")
        or result.get("validation_status")
        or "ok"
    )
    return record_with_hash({
        "artifact_type": "public_paper_champion_hardening_and_deep_stress_v1_step",
        "step_id": step_id,
        "status": status,
        "summary_hash": result.get("summary_hash", ""),
        "live_trading_enabled": bool(result.get("live_trading_enabled", False)),
    }, "record_hash")


def hardening_status(gate_summary: dict[str, object], lake_summary: dict[str, object], preflight: dict[str, object]) -> str:
    if str(lake_summary.get("public_lake_final_state_status", "")) != "public_lake_locked_clean":
        return "public_lake_degraded_repair_required"
    if str(preflight.get("champion_hardening_preflight_status", "")) != "ready_for_champion_hardening":
        return "champion_hardening_preflight_blocked"
    gate_status = str(gate_summary.get("champion_hardening_gate_status", ""))
    if gate_status == "hardened_public_paper_champions_found_live_gate_locked":
        return "hardened_public_paper_champions_found_live_gate_locked"
    if gate_status == "conditional_public_champions_require_repair":
        return "conditional_public_champions_require_repair"
    return "all_public_champions_demoted_after_deep_stress"


def next_recommended_target(status: str) -> str:
    if status == "hardened_public_paper_champions_found_live_gate_locked":
        return "DOPEY_HARDENED_PUBLIC_CHAMPION_EXTENDED_PAPER_SHADOW_V1"
    if status == "conditional_public_champions_require_repair":
        return "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1"
    if status == "public_lake_degraded_repair_required":
        return "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1"


def build_orchestrator_summary(
    status: str,
    preflight: dict[str, object],
    cleaner: dict[str, object],
    inventory: dict[str, object],
    stress: dict[str, object],
    holdout: dict[str, object],
    decay: dict[str, object],
    gate: dict[str, object],
    repair: dict[str, object],
    scoreboard: dict[str, object],
    live_gate: dict[str, object],
    handoff: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_type": "public_paper_champion_hardening_and_deep_stress_v1_summary",
        "public_paper_champion_hardening_version": HARDENING_VERSION,
        "champion_hardening_status": status,
        "champion_hardening_preflight_status": preflight.get("champion_hardening_preflight_status"),
        "signal_artifact_cleaner_status": cleaner.get("signal_artifact_cleaner_status"),
        "input_public_champion_count": inventory.get("public_paper_champion_count", 0),
        "hardened_champion_count": gate.get("hardened_champion_count", 0),
        "conditional_champion_count": gate.get("conditional_champion_count", 0),
        "demoted_champion_count": gate.get("demoted_champion_count", 0),
        "hardened_champion_names": gate.get("hardened_champion_names", []),
        "conditional_champion_names": gate.get("conditional_champion_names", []),
        "demoted_champion_names": gate.get("demoted_champion_names", []),
        "removed_test_signal_count": cleaner.get("removed_test_signal_count", 0),
        "simv2_rows_remaining": cleaner.get("simv2_rows_remaining", 0),
        "stress_case_count": stress.get("stress_case_count", 0),
        "champions_survived_core": stress.get("champions_survived_core", 0),
        "holdout_survivor_count": holdout.get("holdout_survivor_count", 0),
        "decay_alert_count": decay.get("decay_alert_count", 0),
        "repair_queue_count": repair.get("repair_queue_count", 0),
        "live_gate_status": live_gate.get("live_gate_status"),
        "shared_copy_status": handoff.get("shared_copy_status", "not_attempted"),
        "next_recommended_target": next_recommended_target(status),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def write_validation_summary(validation_status: str) -> dict[str, object]:
    timeout_records = read_jsonl_file(TIMEOUT_RECORDS_PATH)
    summary = {
        "artifact_type": "public_paper_champion_hardening_and_deep_stress_v1_validation_summary",
        "validation_status": validation_status,
        "timeout_records": timeout_records,
        "timeout_recorded_as_pass": False,
        "targeted_test_command": ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_paper_champion_hardening_and_deep_stress_v1.py -q",
        **live_safety_fields(),
    }
    return write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)


def write_bundle_docs(*summaries) -> dict[str, object]:
    preflight, cleaner, inventory, stress, holdout, decay, gate, repair, scoreboard, live_gate, validation = summaries
    REPORT_PATH.write_text(render_report(preflight, cleaner, inventory, stress, holdout, decay, gate, repair, scoreboard, live_gate, validation), encoding="utf-8")
    LEDGER_PATH.write_text(render_ledger(), encoding="utf-8")
    COMMANDS_PATH.write_text(render_commands(), encoding="utf-8")
    return {
        "artifact_type": "public_champion_hardening_docs",
        "report_path": str(REPORT_PATH),
        "ledger_path": str(LEDGER_PATH),
        "commands_path": str(COMMANDS_PATH),
        "live_trading_enabled": False,
    }


def render_report(*summaries) -> str:
    preflight, cleaner, inventory, stress, holdout, decay, gate, repair, scoreboard, live_gate, validation = summaries
    status = hardening_status(gate, {"public_lake_final_state_status": "public_lake_locked_clean"}, preflight)
    lines = [
        "# DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1_REPORT",
        "",
        "## Preflight",
        f"- champion_hardening_preflight_status: `{preflight.get('champion_hardening_preflight_status')}`",
        f"- public_paper_champion_count: `{preflight.get('public_paper_champion_count')}`",
        "",
        "## Signal artifact cleaner",
        f"- removed_test_signal_count: `{cleaner.get('removed_test_signal_count')}`",
        f"- simv2_rows_remaining: `{cleaner.get('simv2_rows_remaining')}`",
        "",
        "## Deep stress",
        f"- stress_case_count: `{stress.get('stress_case_count')}`",
        f"- champions_survived_core: `{stress.get('champions_survived_core')}`",
        "",
        "## Holdout expansion",
        f"- holdout_survivor_count: `{holdout.get('holdout_survivor_count')}`",
        "",
        "## Decay monitor",
        f"- decay_alert_count: `{decay.get('decay_alert_count')}`",
        "",
        "## Hardening gate",
        f"- hardened_champion_count: `{gate.get('hardened_champion_count')}`",
        f"- conditional_champion_count: `{gate.get('conditional_champion_count')}`",
        f"- demoted_champion_count: `{gate.get('demoted_champion_count')}`",
        "",
        "## Live gate V3",
        f"- live_gate_status: `{live_gate.get('live_gate_status')}`",
        f"- live_trading_enabled: `{live_gate.get('live_trading_enabled')}`",
        "",
        "## Validation",
        f"- validation_status: `{validation.get('validation_status')}`",
        "",
        "## Next target",
        f"- next_recommended_target: `{next_recommended_target(status)}`",
        "",
        "No live readiness or profitability claim is made. Champions are hardened or demoted honestly on public paper data only.",
    ]
    return "\n".join(lines) + "\n"


def render_ledger() -> str:
    paths = [
        "artifacts/dopey/champion_hardening/champion_hardening_preflight_summary.json",
        "artifacts/dopey/champion_hardening/public_signal_artifact_cleaner_summary.json",
        "artifacts/dopey/champion_hardening/public_champion_inventory_v1_summary.json",
        "artifacts/dopey/champion_hardening/public_champion_deep_stress_matrix_v1_summary.json",
        "artifacts/dopey/champion_hardening/public_champion_holdout_expansion_v1_summary.json",
        "artifacts/dopey/champion_hardening/public_champion_decay_monitor_v1_summary.json",
        "artifacts/dopey/champion_hardening/public_champion_hardening_gate_v1_summary.json",
        "artifacts/dopey/scoreboard/public_champion_hardening_scoreboard_v1.json",
        "artifacts/dopey/live_gate/public_champion_hardening_live_gate_status_v3.json",
        "artifacts/dopey/champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_summary.json",
        "artifacts/dopey/champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_validation_summary.json",
    ]
    lines = ["# DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1_ARTIFACT_LEDGER", ""]
    for path in paths:
        lines.append(f"- `{path}`")
    return "\n".join(lines) + "\n"


def render_commands() -> str:
    commands = [
        ".\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_paper_champion_hardening_and_deep_stress_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_validation.run_champion_hardening_preflight",
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_engine.run_public_signal_artifact_cleaner_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_champion.run_public_champion_inventory_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_champion.run_public_champion_deep_stress_matrix_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_champion.run_public_champion_holdout_expansion_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_champion.run_public_champion_decay_monitor_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_champion.run_public_champion_hardening_gate_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_evolution.run_public_champion_hardening_repair_queue_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_scoreboard.run_public_champion_hardening_scoreboard_v1",
        ".\\.venv\\Scripts\\python.exe -m dopey_live_gate.run_public_champion_hardening_live_gate_status_v3",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_paper_champion_hardening_and_deep_stress_v1.py -q",
    ]
    lines = ["# DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1_COMMANDS", "", "All commands use the explicit repo venv. No live broker/order commands.", ""]
    for command in commands:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_handoff_file_list() -> list[Path]:
    raw_paths = [
        REPORT_PATH, LEDGER_PATH, COMMANDS_PATH,
        HARDENING_ROOT / "champion_hardening_preflight_summary.json",
        HARDENING_ROOT / "public_signal_artifact_cleaner_summary.json",
        HARDENING_ROOT / "public_champion_inventory_v1_summary.json",
        HARDENING_ROOT / "public_champion_deep_stress_matrix_v1_summary.json",
        HARDENING_ROOT / "public_champion_holdout_expansion_v1_summary.json",
        HARDENING_ROOT / "public_champion_decay_monitor_v1_summary.json",
        HARDENING_ROOT / "public_champion_hardening_gate_v1_summary.json",
        HARDENING_ROOT / "public_champion_hardening_repair_summary_v1.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_champion_hardening_scoreboard_v1.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_champion_hardening_dashboard_v1.html",
        REPO_ROOT / "artifacts" / "dopey" / "live_gate" / "public_champion_hardening_live_gate_status_v3.json",
        SUMMARY_PATH, VALIDATION_SUMMARY_PATH, TIMEOUT_RECORDS_PATH,
    ]
    return [path for path in raw_paths if path.exists()]


def copy_shared_handoff(files: list[Path]) -> dict[str, object]:
    roots = [
        Path("C:/Users/CH/Desktop/Shared Folder"),
        Path("C:/Users/chris/Desktop/Shared Folder"),
        Path("//FRANKENSTEIN/Shared Folder"),
        Path("Z:/"),
    ]
    attempts: list[dict[str, object]] = []
    for root in roots:
        try:
            if not root.exists():
                attempts.append({"root": str(root), "status": "missing"})
                continue
            target_root = root / HANDOFF_FOLDER_NAME
            target_root.mkdir(parents=True, exist_ok=True)
            copied = copy_files_to_target(files, target_root)
            manifest = {
                "artifact_type": "session_copy_manifest",
                "target_root": str(target_root),
                "copied_count": len(copied),
                "copied_files": copied,
                "live_trading_enabled": False,
            }
            manifest_path = target_root / "SESSION_COPY_MANIFEST.json"
            write_json_file(manifest_path, manifest)
            return {
                "artifact_type": "shared_handoff_summary",
                "shared_copy_status": "copied",
                "target_root": str(target_root),
                "copied_count": len(copied),
                "session_copy_manifest": str(manifest_path),
                "attempts": attempts,
                "live_trading_enabled": False,
            }
        except OSError as exc:
            attempts.append({"root": str(root), "status": "copy_failed", "error": f"{type(exc).__name__}: {exc}"})
    return {
        "artifact_type": "shared_handoff_summary",
        "shared_copy_status": "not_copied_no_available_target",
        "target_root": "",
        "copied_count": 0,
        "session_copy_manifest": "",
        "attempts": attempts,
        "live_trading_enabled": False,
    }


def copy_files_to_target(files: list[Path], target_root: Path) -> list[dict[str, object]]:
    copied: list[dict[str, object]] = []
    for source in files:
        destination = target_root / source.name
        shutil.copy2(source, destination)
        copied.append({
            "source": str(source),
            "destination": str(destination),
            "sha256": sha256_file(destination),
            "size_bytes": destination.stat().st_size,
        })
    return copied


def orchestrator_artifact_paths() -> dict[str, str]:
    return {
        "public_paper_champion_hardening_and_deep_stress_v1_summary": str(SUMMARY_PATH),
        "public_paper_champion_hardening_and_deep_stress_v1_steps": str(STEPS_PATH),
        "public_paper_champion_hardening_and_deep_stress_v1_quality_flags": str(QUALITY_FLAGS_PATH),
        "public_paper_champion_hardening_and_deep_stress_v1_proof": str(PROOF_PATH),
        "public_paper_champion_hardening_and_deep_stress_v1_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "public_paper_champion_hardening_and_deep_stress_v1_timeout_records": str(TIMEOUT_RECORDS_PATH),
    }


def main() -> int:
    summary = run_public_paper_champion_hardening_and_deep_stress_v1()
    print(json.dumps({
        "champion_hardening_status": summary["champion_hardening_status"],
        "input_public_champion_count": summary["input_public_champion_count"],
        "hardened_champion_count": summary["hardened_champion_count"],
        "conditional_champion_count": summary["conditional_champion_count"],
        "demoted_champion_count": summary["demoted_champion_count"],
        "live_gate_status": summary["live_gate_status"],
        "next_recommended_target": summary["next_recommended_target"],
        "summary_path": summary["artifact_paths"]["public_paper_champion_hardening_and_deep_stress_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
