"""Full orchestrator for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_active_policy.run_zero_dte_replay_outcomes_artifact_repair_v1 import run_zero_dte_replay_outcomes_artifact_repair_v1
from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, SCOREBOARD_ROOT, record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT, RESEARCH_V3_VERSION, research_v3_proof_record, write_summary_with_hash
from dopey_live_gate.run_public_signal_research_live_gate_status_v3 import run_public_signal_research_live_gate_status_v3
from dopey_market_intake.run_public_lake_freeze_guard import main as run_freeze_guard_main
from dopey_scoreboard.run_public_signal_research_scoreboard_v3 import run_public_signal_research_scoreboard_v3
from dopey_signal_research.run_profit_holdout_repair_scorer_v3 import run_profit_holdout_repair_scorer_v3
from dopey_signal_research.run_research_breakthrough_gate_v3 import run_research_breakthrough_gate_v3
from dopey_signal_research.run_research_candidate_generator_v3 import run_research_candidate_generator_v3
from dopey_signal_research.run_research_mutation_queue_executor_v3 import run_research_mutation_queue_executor_v3
from dopey_signal_research.run_research_mutation_queue_v3 import run_research_mutation_queue_v3
from dopey_signal_research.run_research_path_simulator_v3 import run_research_path_simulator_v3
from dopey_signal_research.run_research_tournament_v3 import run_research_tournament_v3
from dopey_signal_research.run_stable_family_template_repair_v3 import run_stable_family_template_repair_v3
from dopey_validation.run_public_signal_research_v3_preflight import run_public_signal_research_v3_preflight
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


SUMMARY_PATH = RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_summary.json"
STEPS_PATH = RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_steps.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_quality_flags.jsonl"
PROOF_PATH = RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_proof.jsonl"
VALIDATION_SUMMARY_PATH = RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_validation_summary.json"
TIMEOUT_RECORDS_PATH = RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_timeout_records.jsonl"
REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3_COMMANDS.md"
HANDOFF_FOLDER = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3"


def run_public_signal_research_breakthrough_v3() -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []

    preflight = run_public_signal_research_v3_preflight(run_lake_guard=False)
    steps.append(record_step("public_signal_research_v3_preflight", preflight))
    if str(preflight.get("public_signal_research_v3_preflight_status", "")) != "ready_for_mutation_queue_execution":
        return finalize_blocked(preflight, steps)

    run_freeze_guard_main()
    mutation_exec = run_research_mutation_queue_executor_v3()
    steps.append(record_step("research_mutation_queue_executor_v3", mutation_exec))
    templates = run_stable_family_template_repair_v3()
    steps.append(record_step("stable_family_template_repair_v3", templates))
    candidates = run_research_candidate_generator_v3()
    steps.append(record_step("research_candidate_generator_v3", candidates))
    scorer = run_profit_holdout_repair_scorer_v3()
    steps.append(record_step("profit_holdout_repair_scorer_v3", scorer))
    simulator = run_research_path_simulator_v3()
    steps.append(record_step("research_path_simulator_v3", simulator))
    tournament = run_research_tournament_v3()
    steps.append(record_step("research_tournament_v3", tournament))
    gate = run_research_breakthrough_gate_v3()
    steps.append(record_step("research_breakthrough_gate_v3", gate))
    mutation = run_research_mutation_queue_v3()
    steps.append(record_step("research_mutation_queue_v3", mutation))
    artifact_repair = run_zero_dte_replay_outcomes_artifact_repair_v1()
    steps.append(record_step("zero_dte_replay_outcomes_artifact_repair_v1", artifact_repair))
    scoreboard = run_public_signal_research_scoreboard_v3()
    steps.append(record_step("public_signal_research_scoreboard_v3", scoreboard))
    live_gate = run_public_signal_research_live_gate_status_v3()
    steps.append(record_step("public_signal_research_live_gate_status_v3", live_gate))
    validation = write_validation_summary("pending_watchdog_validation")
    steps.append(record_step("validation_summary", validation))
    docs = write_bundle_docs()
    steps.append(record_step("docs", docs))
    handoff = copy_shared_handoff(build_handoff_file_list())
    steps.append(record_step("shared_handoff", handoff))

    status = research_v3_status(preflight, gate, scoreboard, mutation_exec)
    summary = build_orchestrator_summary(
        status, preflight, mutation_exec, templates, candidates, scorer, simulator, tournament, gate, mutation, artifact_repair, scoreboard, live_gate, handoff
    )
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(QUALITY_FLAGS_PATH, [])
    if not TIMEOUT_RECORDS_PATH.exists():
        write_jsonl_file(TIMEOUT_RECORDS_PATH, [])
    write_jsonl_file(PROOF_PATH, [research_v3_proof_record("public-signal-research-breakthrough-v3", status, summary)])
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def record_step(step_id: str, result: dict[str, object]) -> dict[str, object]:
    status = next((str(result[key]) for key in result if key.endswith("_status") and result.get(key)), "ok")
    return record_with_hash(
        {
            "artifact_type": "public_signal_research_breakthrough_v3_step",
            "step_id": step_id,
            "status": status,
            "summary_hash": result.get("summary_hash", ""),
            "live_trading_enabled": False,
        },
        "record_hash",
    )


def research_v3_status(preflight, gate, scoreboard, mutation_exec) -> str:
    if str(preflight.get("public_signal_research_v3_preflight_status", "")) != "ready_for_mutation_queue_execution":
        return "public_signal_research_v3_preflight_blocked"
    gate_status = str(gate.get("research_breakthrough_gate_v3_status", ""))
    if gate_status == "research_breakthrough_candidates_found":
        return "research_breakthrough_candidates_found_live_gate_locked"
    improved = int(scoreboard.get("improved_vs_v2_count", 0)) > 0 or int(gate.get("improved_watchlist_count", 0)) > 0
    if gate_status == "research_watchlist_only" or (improved and int(gate.get("watchlist_count", 0)) > 0):
        return "research_watchlist_improved_requires_v4"
    if int(mutation_exec.get("executed_mutation_count", 0)) > 0:
        return "mutation_execution_complete_no_breakthrough"
    return "no_breakthrough_candidates_found"


def next_recommended_target(status: str) -> str:
    if status == "research_breakthrough_candidates_found_live_gate_locked":
        return "DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1"
    if status == "research_watchlist_improved_requires_v4":
        return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4"
    if status == "public_signal_research_v3_preflight_blocked":
        return "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    if status == "mutation_execution_complete_no_breakthrough":
        return "DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2"
    return "DOPEY_ACTIVE_POLICY_ARTIFACT_CHAIN_REPAIR_V1"


def build_orchestrator_summary(
    status, preflight, mutation_exec, templates, candidates, scorer, simulator, tournament, gate, mutation, artifact_repair, scoreboard, live_gate, handoff
) -> dict[str, object]:
    return {
        "artifact_type": "public_signal_research_breakthrough_v3_summary",
        "public_signal_research_v3_version": RESEARCH_V3_VERSION,
        "public_signal_research_v3_status": status,
        "preflight_status": preflight.get("public_signal_research_v3_preflight_status", ""),
        "input_mutation_count": mutation_exec.get("input_mutation_count", 0),
        "executed_mutation_count": mutation_exec.get("executed_mutation_count", 0),
        "continuation_template_enabled": templates.get("continuation_template_enabled", False),
        "volume_template_enabled": templates.get("volume_template_enabled", False),
        "continuation_candidate_count": candidates.get("continuation_candidate_count", 0),
        "volume_candidate_count": candidates.get("volume_candidate_count", 0),
        "no_trade_filtered_count": candidates.get("no_trade_filtered_count", 0),
        "research_candidate_count": candidates.get("candidate_count", 0),
        "candidate_symbol_count": candidates.get("symbol_count", 0),
        "candidate_sector_count": candidates.get("sector_count", 0),
        "prioritized_candidate_count": scorer.get("prioritized_candidate_count", 0),
        "simulated_trade_count": simulator.get("simulated_trade_count", 0),
        "tournament_family_count": tournament.get("family_count", 0),
        "tournament_cohort_count": tournament.get("cohort_count", 0),
        "improved_vs_v2_count": tournament.get("improved_vs_v2_count", 0),
        "breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": gate.get("watchlist_count", 0),
        "top_research_family": tournament.get("top_family", ""),
        "top_research_cohort": tournament.get("top_cohort", ""),
        "top_net_pnl": tournament.get("top_net_pnl", 0.0),
        "top_profit_factor": tournament.get("top_profit_factor", 0.0),
        "top_sample_count": tournament.get("top_sample_count", 0),
        "mutation_queue_v3_count": mutation.get("mutation_queue_count", 0),
        "zero_dte_replay_outcomes_repair_status": artifact_repair.get("zero_dte_replay_outcomes_repair_status", ""),
        "live_gate_status": live_gate.get("live_gate_status", ""),
        "shared_copy_status": handoff.get("shared_copy_status", "not_attempted"),
        "next_recommended_target": next_recommended_target(status),
        **live_safety_fields(),
    }


def finalize_blocked(preflight, steps):
    status = "public_signal_research_v3_preflight_blocked"
    summary = {
        "artifact_type": "public_signal_research_breakthrough_v3_summary",
        "public_signal_research_v3_status": status,
        "preflight_status": preflight.get("public_signal_research_v3_preflight_status", ""),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(PROOF_PATH, [research_v3_proof_record("public-signal-research-breakthrough-v3", status, summary)])
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def write_validation_summary(validation_status: str) -> dict[str, object]:
    summary = {
        "artifact_type": "public_signal_research_breakthrough_v3_validation_summary",
        "validation_status": validation_status,
        "timeout_recorded_as_pass": False,
        "targeted_test_command": ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_signal_research_breakthrough_v3.py -q",
        **live_safety_fields(),
    }
    return write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)


def write_bundle_docs() -> dict[str, object]:
    REPORT_PATH.write_text(
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3_REPORT\n\n"
        "V3 executes V2 mutation queue, repairs volume dry-up template matching, adds selective no-trade filters, "
        "and compares repair outcomes vs V2. Live gate remains locked.\n",
        encoding="utf-8",
    )
    LEDGER_PATH.write_text(
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3_ARTIFACT_LEDGER\n\n"
        "Artifacts under artifacts/dopey/signal_research_v3/\n",
        encoding="utf-8",
    )
    COMMANDS_PATH.write_text(
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3_COMMANDS\n\n"
        "`.\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_signal_research_breakthrough_v3`\n",
        encoding="utf-8",
    )
    return {"docs_written": True}


def build_handoff_file_list() -> list[Path]:
    return [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        RESEARCH_V3_ROOT / "public_signal_research_v3_preflight_summary.json",
        RESEARCH_V3_ROOT / "research_mutation_queue_executor_v3_summary.json",
        RESEARCH_V3_ROOT / "stable_family_template_repair_v3_summary.json",
        RESEARCH_V3_ROOT / "research_candidate_generator_v3_summary.json",
        RESEARCH_V3_ROOT / "profit_holdout_repair_scorer_v3_summary.json",
        RESEARCH_V3_ROOT / "research_path_simulator_v3_summary.json",
        RESEARCH_V3_ROOT / "research_tournament_v3_summary.json",
        RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_summary.json",
        RESEARCH_V3_ROOT / "research_mutation_queue_v3_summary.json",
        REPO_ROOT / "artifacts/dopey/active_policy/zero_dte_replay_outcomes_artifact_repair_v1_summary.json",
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v3.json",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v3.html",
        LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v3.json",
        SUMMARY_PATH,
        VALIDATION_SUMMARY_PATH,
        TIMEOUT_RECORDS_PATH,
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
        copied = sum(1 for path in files if path.exists() and (shutil.copy2(path, dest / path.name) or True))
        (dest / "session_copy_manifest.json").write_text(json.dumps({"copied_count": copied}, indent=2), encoding="utf-8")
        return {"shared_copy_status": "copied", "target_root": str(dest), "copied_count": copied}
    return {"shared_copy_status": "not_attempted", "copied_count": 0}


def orchestrator_artifact_paths() -> dict[str, str]:
    return {
        "public_signal_research_breakthrough_v3_summary": str(SUMMARY_PATH),
        "public_signal_research_breakthrough_v3_validation_summary": str(VALIDATION_SUMMARY_PATH),
    }


def main() -> int:
    summary = run_public_signal_research_breakthrough_v3()
    print(
        json.dumps(
            {
                "public_signal_research_v3_status": summary["public_signal_research_v3_status"],
                "executed_mutation_count": summary.get("executed_mutation_count", 0),
                "continuation_candidate_count": summary.get("continuation_candidate_count", 0),
                "volume_candidate_count": summary.get("volume_candidate_count", 0),
                "breakthrough_candidate_count": summary.get("breakthrough_candidate_count", 0),
                "next_recommended_target": summary.get("next_recommended_target", ""),
                "summary_path": summary["artifact_paths"]["public_signal_research_breakthrough_v3_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
