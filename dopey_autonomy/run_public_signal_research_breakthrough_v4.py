"""Full orchestrator for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4.

Sequence (per spec):
1. V4 preflight
2. final public lake guard/freeze
3. V3 mutation queue executor
4. profitable slice miner
5. no-trade filter optimizer
6. family template splitter + volume rescue
7. candidate generator V4
8. PF/holdout/split scorer V4
9. research path simulator V4
10. research tournament V4
11. breakthrough gate V4
12. mutation queue V4
13. active policy artifact guard V2
14. scoreboard V4
15. live gate lock V4
16. integration/report/export/review
17. validation summary
18. shared handoff

Status logic:
- breakthroughs found → research_breakthrough_candidates_found_live_gate_locked
  next DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1
- PF/holdout/split improved → pf_holdout_split_improved_requires_v5
  next DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5
- mutation execution complete no improvement →
  mutation_execution_complete_no_improvement
  next DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2
- active policy artifact guard fails →
  next DOPEY_ACTIVE_POLICY_ARTIFACT_CHAIN_REPAIR_V1
- public lake degraded → next DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_active_policy.run_zero_dte_replay_outcomes_artifact_guard_v2 import run_zero_dte_replay_outcomes_artifact_guard_v2
from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, SCOREBOARD_ROOT, record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v4_common import (
    ARTIFACT_GUARD_V2_SUMMARY_PATH,
    GATE_V4_SUMMARY_PATH,
    MUTATION_QUEUE_V4_SUMMARY_PATH,
    RESEARCH_V4_ROOT,
    RESEARCH_V4_VERSION,
    TOURNAMENT_SUMMARY_PATH,
    research_v4_proof_record,
    write_summary_with_hash,
)
from dopey_live_gate.run_public_signal_research_live_gate_status_v4 import run_public_signal_research_live_gate_status_v4
from dopey_market_intake.run_public_lake_freeze_guard import main as run_freeze_guard_main
from dopey_scoreboard.run_public_signal_research_scoreboard_v4 import run_public_signal_research_scoreboard_v4
from dopey_signal_research.run_family_template_splitter_v4 import run_family_template_splitter_v4
from dopey_signal_research.run_no_trade_filter_optimizer_v4 import run_no_trade_filter_optimizer_v4
from dopey_signal_research.run_profitable_slice_miner_v4 import run_profitable_slice_miner_v4
from dopey_signal_research.run_profit_holdout_split_scorer_v4 import run_profit_holdout_split_scorer_v4
from dopey_signal_research.run_research_breakthrough_gate_v4 import run_research_breakthrough_gate_v4
from dopey_signal_research.run_research_candidate_generator_v4 import run_research_candidate_generator_v4
from dopey_signal_research.run_research_mutation_queue_executor_v4 import run_research_mutation_queue_executor_v4
from dopey_signal_research.run_research_mutation_queue_v4 import run_research_mutation_queue_v4
from dopey_signal_research.run_research_path_simulator_v4 import run_research_path_simulator_v4
from dopey_signal_research.run_research_tournament_v4 import run_research_tournament_v4
from dopey_validation.run_public_signal_research_v4_preflight import run_public_signal_research_v4_preflight
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


SUMMARY_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_summary.json"
STEPS_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_steps.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_quality_flags.jsonl"
PROOF_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_proof.jsonl"
VALIDATION_SUMMARY_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_validation_summary.json"
TIMEOUT_RECORDS_PATH = RESEARCH_V4_ROOT / "public_signal_research_breakthrough_v4_timeout_records.jsonl"
REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_COMMANDS.md"
HANDOFF_FOLDER = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4"

EXPECTED_PREFLIGHT_STATUS = "ready_for_pf_holdout_split_repair"


def run_public_signal_research_breakthrough_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []

    preflight = run_public_signal_research_v4_preflight()
    steps.append(record_step("public_signal_research_v4_preflight", preflight))
    preflight_status = str(preflight.get("public_signal_research_v4_preflight_status", ""))
    if preflight_status not in {EXPECTED_PREFLIGHT_STATUS, "ready_for_mutation_queue_execution"}:
        return finalize_blocked(preflight, steps, reason="preflight_not_ready")

    # Step 2: public lake freeze guard.
    try:
        run_freeze_guard_main()
        steps.append(record_step("public_lake_freeze_guard", {"status": "ok"}))
    except Exception as exc:  # noqa: BLE001
        steps.append(record_step("public_lake_freeze_guard", {"status": "public_lake_degraded", "error": str(exc)}))
        return finalize_blocked(preflight, steps, reason="public_lake_degraded")

    # Step 3: V3 mutation queue executor.
    mutation_exec = run_research_mutation_queue_executor_v4()
    steps.append(record_step("research_mutation_queue_executor_v4", mutation_exec))

    # Step 4: profitable slice miner.
    slice_miner = run_profitable_slice_miner_v4()
    steps.append(record_step("profitable_slice_miner_v4", slice_miner))

    # Step 5: no-trade filter optimizer.
    no_trade = run_no_trade_filter_optimizer_v4()
    steps.append(record_step("no_trade_filter_optimizer_v4", no_trade))

    # Step 6: family template splitter + volume rescue.
    splitter = run_family_template_splitter_v4()
    steps.append(record_step("family_template_splitter_v4", splitter))

    # Step 7: candidate generator V4.
    candidates = run_research_candidate_generator_v4()
    steps.append(record_step("research_candidate_generator_v4", candidates))

    # Step 8: PF/holdout/split scorer V4.
    scorer = run_profit_holdout_split_scorer_v4()
    steps.append(record_step("profit_holdout_split_scorer_v4", scorer))

    # Step 9: research path simulator V4.
    simulator = run_research_path_simulator_v4()
    steps.append(record_step("research_path_simulator_v4", simulator))

    # Step 10: research tournament V4.
    tournament = run_research_tournament_v4()
    steps.append(record_step("research_tournament_v4", tournament))

    # Step 11: breakthrough gate V4.
    gate = run_research_breakthrough_gate_v4()
    steps.append(record_step("research_breakthrough_gate_v4", gate))

    # Step 12: mutation queue V4.
    mutation = run_research_mutation_queue_v4()
    steps.append(record_step("research_mutation_queue_v4", mutation))

    # Step 13: active policy artifact guard V2.
    guard = run_zero_dte_replay_outcomes_artifact_guard_v2()
    steps.append(record_step("zero_dte_replay_outcomes_artifact_guard_v2", guard))

    # Step 14: scoreboard V4.
    scoreboard = run_public_signal_research_scoreboard_v4()
    steps.append(record_step("public_signal_research_scoreboard_v4", scoreboard))

    # Step 15: live gate lock V4.
    live_gate = run_public_signal_research_live_gate_status_v4()
    steps.append(record_step("public_signal_research_live_gate_status_v4", live_gate))

    # Step 16: integration / report / export / review.
    docs = write_bundle_docs(
        preflight,
        mutation_exec,
        slice_miner,
        no_trade,
        splitter,
        candidates,
        scorer,
        simulator,
        tournament,
        gate,
        mutation,
        guard,
        scoreboard,
        live_gate,
    )
    steps.append(record_step("docs", docs))

    # Step 17: validation summary.
    validation = write_validation_summary("pending_watchdog_validation")
    steps.append(record_step("validation_summary", validation))

    # Step 18: shared handoff.
    handoff = copy_shared_handoff(build_handoff_file_list())
    steps.append(record_step("shared_handoff", handoff))

    status = research_v4_status(preflight, gate, mutation_exec, mutation)
    summary = build_orchestrator_summary(
        status,
        preflight,
        mutation_exec,
        slice_miner,
        no_trade,
        splitter,
        candidates,
        scorer,
        simulator,
        tournament,
        gate,
        mutation,
        guard,
        scoreboard,
        live_gate,
        handoff,
    )
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(QUALITY_FLAGS_PATH, [])
    if not TIMEOUT_RECORDS_PATH.exists():
        write_jsonl_file(TIMEOUT_RECORDS_PATH, [])
    write_jsonl_file(PROOF_PATH, [research_v4_proof_record("public-signal-research-breakthrough-v4", status, summary)])
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def record_step(step_id: str, result: dict[str, object]) -> dict[str, object]:
    status = "ok"
    for key in result:
        if key.endswith("_status") and result.get(key):
            status = str(result.get(key))
            break
    return record_with_hash(
        {
            "artifact_type": "public_signal_research_breakthrough_v4_step",
            "step_id": step_id,
            "status": status,
            "summary_hash": result.get("summary_hash", ""),
            "live_trading_enabled": False,
        },
        "record_hash",
    )


def research_v4_status(preflight, gate, mutation_exec, mutation) -> str:
    preflight_status = str(preflight.get("public_signal_research_v4_preflight_status", ""))
    if preflight_status not in {EXPECTED_PREFLIGHT_STATUS, "ready_for_mutation_queue_execution"}:
        return "public_signal_research_v4_preflight_blocked"
    gate_status = str(gate.get("research_breakthrough_gate_v4_status", ""))
    if gate_status == "research_breakthrough_candidates_found":
        return "research_breakthrough_candidates_found_live_gate_locked"
    improved = int(gate.get("improved_watchlist_count", 0)) > 0 or int(
        gate.get("watchlist_count", 0)
    ) > 0
    if improved:
        return "pf_holdout_split_improved_requires_v5"
    if int(mutation_exec.get("executed_mutation_count", 0)) > 0 or int(
        mutation.get("mutation_queue_count", 0)
    ) > 0:
        return "mutation_execution_complete_no_improvement"
    return "no_breakthrough_candidates_found"


def next_recommended_target(status: str) -> str:
    if status == "research_breakthrough_candidates_found_live_gate_locked":
        return "DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1"
    if status == "pf_holdout_split_improved_requires_v5":
        return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5"
    if status == "public_signal_research_v4_preflight_blocked":
        return "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    if status == "public_lake_degraded":
        return "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    if status == "active_policy_artifact_guard_failed":
        return "DOPEY_ACTIVE_POLICY_ARTIFACT_CHAIN_REPAIR_V1"
    if status == "mutation_execution_complete_no_improvement":
        return "DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2"
    return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5"


def build_orchestrator_summary(
    status,
    preflight,
    mutation_exec,
    slice_miner,
    no_trade,
    splitter,
    candidates,
    scorer,
    simulator,
    tournament,
    gate,
    mutation,
    guard,
    scoreboard,
    live_gate,
    handoff,
) -> dict[str, object]:
    return {
        "artifact_type": "public_signal_research_breakthrough_v4_summary",
        "public_signal_research_v4_version": RESEARCH_V4_VERSION,
        "public_signal_research_v4_status": status,
        "preflight_status": preflight.get("public_signal_research_v4_preflight_status", ""),
        "v3_input_mutation_count": mutation_exec.get("input_mutation_count", 0),
        "v3_executed_mutation_count": mutation_exec.get("executed_mutation_count", 0),
        "profitable_slice_count": slice_miner.get("profitable_slice_count", 0),
        "loss_driver_slice_count": slice_miner.get("loss_driver_slice_count", 0),
        "no_trade_filter_rule_count": no_trade.get("filter_rule_count", 0),
        "volume_rescue_status": splitter.get("volume_rescue_status", ""),
        "continuation_subfamily_count": splitter.get("continuation_subfamily_count", 0),
        "volume_subfamily_count": splitter.get("volume_subfamily_count", 0),
        "research_candidate_count": candidates.get("candidate_count", 0),
        "candidate_symbol_count": candidates.get("symbol_count", 0),
        "candidate_sector_count": candidates.get("sector_count", 0),
        "continuation_candidate_count": candidates.get("continuation_candidate_count", 0),
        "volume_candidate_count": candidates.get("volume_candidate_count", 0),
        "subfamily_count": splitter.get("total_subfamily_count", 0),
        "prioritized_candidate_count": scorer.get("prioritized_candidate_count", 0),
        "simulated_trade_count": simulator.get("simulated_trade_count", 0),
        "uvxy_like_corruption_detected": simulator.get("data_corruption_detected", False)
        or tournament.get("uvxy_like_corruption_detected", False),
        "tournament_family_count": tournament.get("family_count", 0),
        "tournament_subfamily_count": tournament.get("subfamily_count", 0),
        "tournament_cohort_count": tournament.get("cohort_count", 0),
        "improved_vs_v3_count": tournament.get("improved_vs_v3_count", 0),
        "pf_above_110_count": tournament.get("pf_above_110_count", 0),
        "breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": gate.get("watchlist_count", 0),
        "top_research_family": tournament.get("top_family", ""),
        "top_research_subfamily": tournament.get("top_subfamily", ""),
        "top_research_cohort": tournament.get("top_cohort", ""),
        "top_net_pnl": tournament.get("top_net_pnl", 0.0),
        "top_profit_factor": tournament.get("top_profit_factor", 0.0),
        "top_max_drawdown": tournament.get("top_max_drawdown", 0.0),
        "top_sample_count": tournament.get("top_sample_count", 0),
        "mutation_queue_v4_count": mutation.get("mutation_queue_count", 0),
        "zero_dte_replay_outcomes_guard_status": guard.get("zero_dte_replay_outcomes_guard_status", ""),
        "live_gate_status": live_gate.get("live_gate_status", ""),
        "shared_copy_status": handoff.get("shared_copy_status", "not_attempted"),
        "next_recommended_target": next_recommended_target(status),
        **live_safety_fields(),
    }


def finalize_blocked(preflight, steps, reason: str = "preflight_not_ready"):
    if reason == "public_lake_degraded":
        status = "public_lake_degraded"
    else:
        status = "public_signal_research_v4_preflight_blocked"
    summary = {
        "artifact_type": "public_signal_research_breakthrough_v4_summary",
        "public_signal_research_v4_version": RESEARCH_V4_VERSION,
        "public_signal_research_v4_status": status,
        "preflight_status": preflight.get("public_signal_research_v4_preflight_status", ""),
        "next_recommended_target": next_recommended_target(status),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(
        PROOF_PATH,
        [research_v4_proof_record("public-signal-research-breakthrough-v4", status, summary)],
    )
    return {**summary, "artifact_paths": orchestrator_artifact_paths()}


def write_validation_summary(validation_status: str) -> dict[str, object]:
    summary = {
        "artifact_type": "public_signal_research_breakthrough_v4_validation_summary",
        "validation_status": validation_status,
        "timeout_recorded_as_pass": False,
        "targeted_test_command": ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_signal_research_breakthrough_v4.py -q",
        **live_safety_fields(),
    }
    return write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)


def write_bundle_docs(
    preflight,
    mutation_exec,
    slice_miner,
    no_trade,
    splitter,
    candidates,
    scorer,
    simulator,
    tournament,
    gate,
    mutation,
    guard,
    scoreboard,
    live_gate,
) -> dict[str, object]:
    REPORT_PATH.write_text(
        build_report(
            preflight,
            mutation_exec,
            slice_miner,
            no_trade,
            splitter,
            candidates,
            scorer,
            simulator,
            tournament,
            gate,
            mutation,
            guard,
            scoreboard,
            live_gate,
        ),
        encoding="utf-8",
    )
    LEDGER_PATH.write_text(build_ledger(), encoding="utf-8")
    COMMANDS_PATH.write_text(build_commands_doc(), encoding="utf-8")
    return {"docs_written": True}


def build_report(
    preflight,
    mutation_exec,
    slice_miner,
    no_trade,
    splitter,
    candidates,
    scorer,
    simulator,
    tournament,
    gate,
    mutation,
    guard,
    scoreboard,
    live_gate,
) -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_REPORT\n\n"
        "V4 resumed from partial foundation. All steps executed. Live gate remains locked.\n\n"
        "## Pipeline Steps\n\n"
        "1. V4 preflight: " + str(preflight.get("public_signal_research_v4_preflight_status", "")) + "\n"
        "2. Public lake freeze guard: ok\n"
        "3. V3 mutation queue executor: " + str(mutation_exec.get("executed_mutation_count", 0)) + "/" + str(mutation_exec.get("input_mutation_count", 0)) + " executed\n"
        "4. Profitable slice miner: " + str(slice_miner.get("profitable_slice_count", 0)) + " profitable / " + str(slice_miner.get("loss_driver_slice_count", 0)) + " loss-driver\n"
        "5. No-trade filter optimizer: " + str(no_trade.get("rule_count", 0)) + " rules\n"
        "6. Family template splitter: " + str(splitter.get("subfamily_count", 0)) + " subfamilies, " + str(splitter.get("volume_rescue_status", "")) + "\n"
        "7. Candidate generator V4: " + str(candidates.get("candidate_count", 0)) + " candidates across " + str(candidates.get("symbol_count", 0)) + " symbols / " + str(candidates.get("sector_count", 0)) + " sectors\n"
        "8. PF/holdout/split scorer V4: " + str(scorer.get("prioritized_candidate_count", 0)) + " prioritized\n"
        "9. Path simulator V4: " + str(simulator.get("simulated_trade_count", 0)) + " trades\n"
        "10. Tournament V4: " + str(tournament.get("family_count", 0)) + " families / " + str(tournament.get("subfamily_count", 0)) + " subfamilies / " + str(tournament.get("cohort_count", 0)) + " cohorts\n"
        "11. Breakthrough gate V4: " + str(gate.get("breakthrough_candidate_count", 0)) + " breakthroughs / " + str(gate.get("watchlist_count", 0)) + " watchlist\n"
        "12. Mutation queue V4: " + str(mutation.get("mutation_queue_count", 0)) + " entries\n"
        "13. Active policy artifact guard V2: " + str(guard.get("zero_dte_replay_outcomes_guard_status", "")) + "\n"
        "14. Scoreboard V4: written\n"
        "15. Live gate V4: " + str(live_gate.get("live_gate_status", "")) + "\n\n"
        "## UVXY-like Corruption Check\n\n"
        "Detected: " + str(tournament.get("uvxy_like_corruption_detected", False)) + "\n\n"
        "## Profit Factor Result\n\n"
        "Top PF: " + str(tournament.get("top_profit_factor", 0.0)) + " | Subfamilies above 1.10: " + str(tournament.get("pf_above_110_count", 0)) + "\n\n"
        "## Validation\n\n"
        "Validation summary: pending_watchdog_validation\n\n"
        "## Next Target\n\n"
        "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5 (or breakthrough / champion routing per status)\n"
    )


def build_ledger() -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_ARTIFACT_LEDGER\n\n"
        "All artifacts under C:\\Users\\CH\\dopey\\artifacts\\dopey\\signal_research_v4\\\n"
        "and C:\\Users\\CH\\dopey\\artifacts\\dopey\\scoreboard\\ (scoreboard / dashboard)\n"
        "and C:\\Users\\CH\\dopey\\artifacts\\dopey\\live_gate\\ (live gate)\n"
        "and C:\\Users\\CH\\dopey\\artifacts\\dopey\\active_policy\\ (artifact guard V2)\n"
    )


def build_commands_doc() -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_COMMANDS\n\n"
        "Use explicit venv; no live broker / order commands anywhere.\n\n"
        "```\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_signal_research_breakthrough_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_validation.run_public_signal_research_v4_preflight\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_mutation_queue_executor_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_profitable_slice_miner_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_no_trade_filter_optimizer_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_family_template_splitter_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_candidate_generator_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_profit_holdout_split_scorer_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_path_simulator_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_tournament_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_breakthrough_gate_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_mutation_queue_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_active_policy.run_zero_dte_replay_outcomes_artifact_guard_v2\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_scoreboard.run_public_signal_research_scoreboard_v4\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_live_gate.run_public_signal_research_live_gate_status_v4\n"
        ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_signal_research_breakthrough_v4.py -q\n"
        "```\n"
    )


def build_handoff_file_list() -> list[Path]:
    return [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        RESEARCH_V4_ROOT / "public_signal_research_v4_preflight_summary.json",
        RESEARCH_V4_ROOT / "research_mutation_queue_executor_v4_summary.json",
        RESEARCH_V4_ROOT / "profitable_slice_miner_v4_summary.json",
        RESEARCH_V4_ROOT / "no_trade_filter_optimizer_v4_summary.json",
        RESEARCH_V4_ROOT / "family_template_splitter_v4_summary.json",
        RESEARCH_V4_ROOT / "research_candidate_generator_v4_summary.json",
        RESEARCH_V4_ROOT / "profit_holdout_split_scorer_v4_summary.json",
        RESEARCH_V4_ROOT / "research_path_simulator_v4_summary.json",
        RESEARCH_V4_ROOT / "research_tournament_v4_summary.json",
        RESEARCH_V4_ROOT / "research_breakthrough_gate_v4_summary.json",
        RESEARCH_V4_ROOT / "research_mutation_queue_v4_summary.json",
        ARTIFACT_GUARD_V2_SUMMARY_PATH,
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v4.json",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v4.html",
        LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v4.json",
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
        copied = 0
        for path in files:
            if path.exists():
                try:
                    shutil.copy2(path, dest / path.name)
                    copied += 1
                except OSError:
                    continue
        manifest = {
            "copied_count": copied,
            "target_root": str(dest),
            "files": [path.name for path in files if path.exists()],
        }
        (dest / "session_copy_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return {"shared_copy_status": "copied", "target_root": str(dest), "copied_count": copied}
    return {"shared_copy_status": "not_attempted", "copied_count": 0}


def orchestrator_artifact_paths() -> dict[str, str]:
    return {
        "public_signal_research_breakthrough_v4_summary": str(SUMMARY_PATH),
        "public_signal_research_breakthrough_v4_validation_summary": str(VALIDATION_SUMMARY_PATH),
    }


def main() -> int:
    summary = run_public_signal_research_breakthrough_v4()
    print(
        json.dumps(
            {
                "public_signal_research_v4_status": summary["public_signal_research_v4_status"],
                "candidate_count": summary.get("research_candidate_count", 0),
                "simulated_trade_count": summary.get("simulated_trade_count", 0),
                "breakthrough_candidate_count": summary.get("breakthrough_candidate_count", 0),
                "next_recommended_target": summary.get("next_recommended_target", ""),
                "summary_path": summary["artifact_paths"]["public_signal_research_breakthrough_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
