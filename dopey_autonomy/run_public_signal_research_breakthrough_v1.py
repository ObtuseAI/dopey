"""Full orchestrator for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import RESEARCH_ROOT, RESEARCH_VERSION, research_proof_record, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, SCOREBOARD_ROOT, record_with_hash, sha256_file, write_jsonl_file
from dopey_champion.run_failed_champion_family_quarantine_v1 import run_failed_champion_family_quarantine_v1
from dopey_live_gate.run_public_signal_research_live_gate_status_v1 import run_public_signal_research_live_gate_status_v1
from dopey_market_intake.run_public_lake_freeze_guard import main as run_freeze_guard_main
from dopey_scoreboard.run_public_signal_research_scoreboard_v1 import run_public_signal_research_scoreboard_v1
from dopey_signal_research.run_discovery_signal_family_generator_v1 import run_discovery_signal_family_generator_v1
from dopey_signal_research.run_public_feature_miner_v1 import run_public_feature_miner_v1
from dopey_signal_research.run_research_breakthrough_gate_v1 import run_research_breakthrough_gate_v1
from dopey_signal_research.run_research_candidate_generator_v1 import run_research_candidate_generator_v1
from dopey_signal_research.run_research_mutation_queue_v1 import run_research_mutation_queue_v1
from dopey_signal_research.run_research_path_simulator_v1 import run_research_path_simulator_v1
from dopey_signal_research.run_research_tournament_v1 import run_research_tournament_v1
from dopey_validation.run_public_signal_research_preflight_v1 import run_public_signal_research_preflight_v1
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


SUMMARY_PATH = RESEARCH_ROOT / "public_signal_research_breakthrough_v1_summary.json"
STEPS_PATH = RESEARCH_ROOT / "public_signal_research_breakthrough_v1_steps.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_ROOT / "public_signal_research_breakthrough_v1_quality_flags.jsonl"
PROOF_PATH = RESEARCH_ROOT / "public_signal_research_breakthrough_v1_proof.jsonl"
VALIDATION_SUMMARY_PATH = RESEARCH_ROOT / "public_signal_research_breakthrough_v1_validation_summary.json"
TIMEOUT_RECORDS_PATH = RESEARCH_ROOT / "public_signal_research_breakthrough_v1_timeout_records.jsonl"
REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1_COMMANDS.md"
HANDOFF_FOLDER = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1"


def run_public_signal_research_breakthrough_v1() -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []

    preflight = run_public_signal_research_preflight_v1(run_lake_guard=False)
    steps.append(record_step("public_signal_research_preflight_v1", preflight))
    if str(preflight.get("public_signal_research_preflight_status", "")) != "ready_for_signal_research_breakthrough":
        return finalize_blocked(preflight, steps, "public_signal_research_preflight_blocked")

    run_freeze_guard_main()
    quarantine = run_failed_champion_family_quarantine_v1()
    steps.append(record_step("failed_champion_family_quarantine_v1", quarantine))
    feature = run_public_feature_miner_v1()
    steps.append(record_step("public_feature_miner_v1", feature))
    discovery = run_discovery_signal_family_generator_v1()
    steps.append(record_step("discovery_signal_family_generator_v1", discovery))
    candidates = run_research_candidate_generator_v1()
    steps.append(record_step("research_candidate_generator_v1", candidates))
    simulator = run_research_path_simulator_v1()
    steps.append(record_step("research_path_simulator_v1", simulator))
    tournament = run_research_tournament_v1()
    steps.append(record_step("research_tournament_v1", tournament))
    gate = run_research_breakthrough_gate_v1()
    steps.append(record_step("research_breakthrough_gate_v1", gate))
    mutation = run_research_mutation_queue_v1()
    steps.append(record_step("research_mutation_queue_v1", mutation))
    scoreboard = run_public_signal_research_scoreboard_v1()
    steps.append(record_step("public_signal_research_scoreboard_v1", scoreboard))
    live_gate = run_public_signal_research_live_gate_status_v1()
    steps.append(record_step("public_signal_research_live_gate_status_v1", live_gate))
    validation = write_validation_summary("pending_watchdog_validation")
    steps.append(record_step("validation_summary", validation))
    docs = write_bundle_docs(preflight, quarantine, feature, discovery, candidates, simulator, tournament, gate, mutation, scoreboard, live_gate)
    steps.append(record_step("docs", docs))
    handoff = copy_shared_handoff(build_handoff_file_list())
    steps.append(record_step("shared_handoff", handoff))

    status = research_status(preflight, gate)
    summary = build_orchestrator_summary(status, preflight, quarantine, feature, discovery, candidates, simulator, tournament, gate, mutation, scoreboard, live_gate, handoff)
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(QUALITY_FLAGS_PATH, [])
    if not TIMEOUT_RECORDS_PATH.exists():
        write_jsonl_file(TIMEOUT_RECORDS_PATH, [])
    write_jsonl_file(PROOF_PATH, [research_proof_record("public-signal-research-breakthrough-v1", status, summary)])
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def record_step(step_id: str, result: dict[str, object]) -> dict[str, object]:
    status = next((str(result[key]) for key in result if key.endswith("_status") and result.get(key)), "ok")
    return record_with_hash({"artifact_type": "public_signal_research_breakthrough_v1_step", "step_id": step_id, "status": status, "summary_hash": result.get("summary_hash", ""), "live_trading_enabled": False}, "record_hash")


def research_status(preflight: dict[str, object], gate: dict[str, object]) -> str:
    if str(preflight.get("public_signal_research_preflight_status", "")) != "ready_for_signal_research_breakthrough":
        return "public_signal_research_preflight_blocked"
    gate_status = str(gate.get("research_breakthrough_gate_status", ""))
    if gate_status == "research_breakthrough_candidates_found":
        return "research_breakthrough_candidates_found_live_gate_locked"
    if gate_status == "research_watchlist_only":
        return "research_watchlist_created_requires_deeper_mutation"
    return "no_breakthrough_candidates_found"


def next_recommended_target(status: str) -> str:
    if status == "research_breakthrough_candidates_found_live_gate_locked":
        return "DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1"
    if status == "research_watchlist_created_requires_deeper_mutation":
        return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V2"
    if status == "public_signal_research_preflight_blocked":
        return "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    return "DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2"


def build_orchestrator_summary(status, preflight, quarantine, feature, discovery, candidates, simulator, tournament, gate, mutation, scoreboard, live_gate, handoff) -> dict[str, object]:
    return {
        "artifact_type": "public_signal_research_breakthrough_v1_summary",
        "public_signal_research_breakthrough_version": RESEARCH_VERSION,
        "public_signal_research_status": status,
        "preflight_status": preflight.get("public_signal_research_preflight_status", ""),
        "failed_family_quarantine_status": quarantine.get("failed_family_quarantine_status", ""),
        "feature_count": feature.get("feature_count", 0),
        "discovery_family_count": discovery.get("new_family_count", 0),
        "research_candidate_count": candidates.get("candidate_count", 0),
        "simulated_trade_count": simulator.get("simulated_trade_count", 0),
        "tournament_family_count": tournament.get("family_count", 0),
        "tournament_cohort_count": tournament.get("cohort_count", 0),
        "breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": gate.get("watchlist_count", 0),
        "top_research_family": tournament.get("top_family", ""),
        "top_research_cohort": tournament.get("top_cohort", ""),
        "top_net_pnl": tournament.get("top_net_pnl", 0.0),
        "top_profit_factor": tournament.get("top_profit_factor", 0.0),
        "top_sample_count": tournament.get("top_sample_count", 0),
        "mutation_queue_count": mutation.get("mutation_queue_count", 0),
        "live_gate_status": live_gate.get("live_gate_status", ""),
        "shared_copy_status": handoff.get("shared_copy_status", "not_attempted"),
        "next_recommended_target": next_recommended_target(status),
        **live_safety_fields(),
    }


def finalize_blocked(preflight, steps, status):
    summary = build_orchestrator_summary(status, preflight, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {"shared_copy_status": "skipped"})
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(PROOF_PATH, [research_proof_record("public-signal-research-breakthrough-v1", status, summary)])
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def write_validation_summary(validation_status: str) -> dict[str, object]:
    summary = {"artifact_type": "public_signal_research_breakthrough_v1_validation_summary", "validation_status": validation_status, "timeout_recorded_as_pass": False, "targeted_test_command": ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_signal_research_breakthrough_v1.py -q", **live_safety_fields()}
    return write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)


def write_bundle_docs(*_args) -> dict[str, object]:
    REPORT_PATH.write_text("# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1_REPORT\n\nPublic-data signal research breakthrough bundle. Live gate locked.\n", encoding="utf-8")
    LEDGER_PATH.write_text("# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1_ARTIFACT_LEDGER\n\nArtifacts under artifacts/dopey/signal_research/\n", encoding="utf-8")
    COMMANDS_PATH.write_text("# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1_COMMANDS\n\n`.\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_signal_research_breakthrough_v1`\n", encoding="utf-8")
    return {"docs_written": True}


def build_handoff_file_list() -> list[Path]:
    return [
        REPORT_PATH, LEDGER_PATH, COMMANDS_PATH,
        RESEARCH_ROOT / "public_signal_research_preflight_v1_summary.json",
        RESEARCH_ROOT / "failed_champion_family_quarantine_v1_summary.json",
        RESEARCH_ROOT / "public_feature_miner_v1_summary.json",
        RESEARCH_ROOT / "discovery_signal_family_generator_v1_summary.json",
        RESEARCH_ROOT / "research_candidate_generator_v1_summary.json",
        RESEARCH_ROOT / "research_path_simulator_v1_summary.json",
        RESEARCH_ROOT / "research_tournament_v1_summary.json",
        RESEARCH_ROOT / "research_breakthrough_gate_v1_summary.json",
        RESEARCH_ROOT / "research_mutation_queue_v1_summary.json",
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v1.json",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v1.html",
        LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v1.json",
        SUMMARY_PATH, VALIDATION_SUMMARY_PATH, TIMEOUT_RECORDS_PATH,
    ]


def copy_shared_handoff(files: list[Path]) -> dict[str, object]:
    targets = [
        Path("C:/Users/CH/Desktop/Shared Folder"),
        Path("C:/Users/chris/Desktop/Shared Folder"),
        Path("//FRANKENSTEIN/Shared Folder"),
        Path("Z:/"),
    ]
    for base in targets:
        if not base.exists():
            continue
        dest = base / HANDOFF_FOLDER
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for path in files:
            if path.exists():
                shutil.copy2(path, dest / path.name)
                copied += 1
        manifest = dest / "session_copy_manifest.json"
        manifest.write_text(json.dumps({"copied_count": copied, "files": [path.name for path in files if path.exists()]}, indent=2), encoding="utf-8")
        return {"shared_copy_status": "copied", "target_root": str(dest), "copied_count": copied}
    return {"shared_copy_status": "not_attempted", "copied_count": 0}


def orchestrator_artifact_paths() -> dict[str, str]:
    return {"public_signal_research_breakthrough_v1_summary": str(SUMMARY_PATH), "public_signal_research_breakthrough_v1_validation_summary": str(VALIDATION_SUMMARY_PATH)}


def main() -> int:
    summary = run_public_signal_research_breakthrough_v1()
    print(json.dumps({
        "public_signal_research_status": summary["public_signal_research_status"],
        "breakthrough_candidate_count": summary.get("breakthrough_candidate_count", 0),
        "next_recommended_target": summary.get("next_recommended_target", ""),
        "summary_path": summary["artifact_paths"]["public_signal_research_breakthrough_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
