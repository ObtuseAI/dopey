"""Full orchestrator for DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2.

Runs the complete signal-deepening pipeline: public lake lock, cohort
canonicalizer, dense signal mutation V4, model-priced path simulator V4,
cohort walk-forward tournament V4, champion gate V2, deep mutation loop V2,
scoreboard V4, live gate lock V2, docs, validation summary, shared handoff.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_autonomy.public_champion_common import (
    proof_record,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    sha256_file,
    write_json_file,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_deepening_common import DEEPENING_ROOT
from dopey_champion.run_public_paper_champion_gate_v2 import run_public_paper_champion_gate_v2
from dopey_evolution.run_public_signal_deepening_loop_v2 import run_public_signal_deepening_loop_v2
from dopey_live_gate.run_public_signal_deepening_live_gate_status_v2 import run_public_signal_deepening_live_gate_status_v2
from dopey_market_intake.run_public_lake_final_state_lock_v2 import run_public_lake_final_state_lock_v2
from dopey_options_engine.run_model_priced_path_simulator_v4 import run_model_priced_path_simulator_v4
from dopey_scoreboard.run_public_signal_deepening_scoreboard_v4 import run_public_signal_deepening_scoreboard_v4
from dopey_signal_engine.run_public_signal_mutation_factory_v4 import run_public_signal_mutation_factory_v4
from dopey_strategy_cohorts.run_strategy_id_canonicalizer import run_strategy_id_canonicalizer
from dopey_tournament.run_public_cohort_walk_forward_tournament_v4 import run_public_cohort_walk_forward_tournament_v4
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


SUMMARY_PATH = DEEPENING_ROOT / "public_market_signal_mutation_deepening_v2_summary.json"
STEPS_PATH = DEEPENING_ROOT / "public_market_signal_mutation_deepening_v2_steps.jsonl"
QUALITY_FLAGS_PATH = DEEPENING_ROOT / "public_market_signal_mutation_deepening_v2_quality_flags.jsonl"
PROOF_PATH = DEEPENING_ROOT / "public_market_signal_mutation_deepening_v2_proof.jsonl"
VALIDATION_SUMMARY_PATH = DEEPENING_ROOT / "public_market_signal_mutation_deepening_v2_validation_summary.json"
TIMEOUT_RECORDS_PATH = DEEPENING_ROOT / "public_market_signal_mutation_deepening_v2_timeout_records.jsonl"

REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_COMMANDS.md"

HANDOFF_FOLDER_NAME = "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2"


def run_public_market_signal_mutation_deepening_v2() -> dict[str, object]:
    steps: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []

    lake_summary = run_public_lake_final_state_lock_v2()
    steps.append(record_step("public_lake_final_state_lock_v2", lake_summary))

    cohort_summary = run_strategy_id_canonicalizer()
    steps.append(record_step("strategy_id_canonicalizer", cohort_summary))

    signal_summary = run_public_signal_mutation_factory_v4()
    steps.append(record_step("public_signal_mutation_factory_v4", signal_summary))

    cohort_summary = run_strategy_id_canonicalizer()
    steps.append(record_step("strategy_id_canonicalizer_post_signal", cohort_summary))

    simulator_summary = run_model_priced_path_simulator_v4()
    steps.append(record_step("model_priced_path_simulator_v4", simulator_summary))

    tournament_summary = run_public_cohort_walk_forward_tournament_v4()
    steps.append(record_step("public_cohort_walk_forward_tournament_v4", tournament_summary))

    champion_summary = run_public_paper_champion_gate_v2()
    steps.append(record_step("public_paper_champion_gate_v2", champion_summary))

    deepening_summary = run_public_signal_deepening_loop_v2()
    steps.append(record_step("public_signal_deepening_loop_v2", deepening_summary))

    scoreboard_summary = run_public_signal_deepening_scoreboard_v4()
    steps.append(record_step("public_signal_deepening_scoreboard_v4", scoreboard_summary))

    live_gate_summary = run_public_signal_deepening_live_gate_status_v2()
    steps.append(record_step("public_signal_deepening_live_gate_status_v2", live_gate_summary))

    validation_summary = write_validation_summary("pending_watchdog_validation")
    steps.append(record_step("validation_summary", validation_summary))

    docs = write_bundle_docs(lake_summary, signal_summary, simulator_summary, tournament_summary, champion_summary, deepening_summary, scoreboard_summary, live_gate_summary, validation_summary)
    steps.append(record_step("audit_report_export_review_docs", docs))

    handoff = copy_shared_handoff(build_handoff_file_list())
    steps.append(record_step("shared_handoff", handoff))

    if int(lake_summary.get("active_fixture_symbol_count", 0)) != 0:
        quality_flags.append(record_with_hash({"artifact_type": "public_signal_deepening_quality_flag", "flag_id": "fixture_active_symbols_present", "severity": "error"}, "record_hash"))

    status = deepening_status(champion_summary, lake_summary, deepening_summary)
    summary = build_orchestrator_summary(status, lake_summary, signal_summary, simulator_summary, tournament_summary, champion_summary, deepening_summary, scoreboard_summary, live_gate_summary, handoff)
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    if not TIMEOUT_RECORDS_PATH.exists():
        write_jsonl_file(TIMEOUT_RECORDS_PATH, [])
    write_jsonl_file(PROOF_PATH, [proof_record("public-market-signal-mutation-deepening-v2", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def record_step(step_id: str, result: dict[str, object]) -> dict[str, object]:
    status = (
        result.get("public_lake_final_state_status")
        or result.get("strategy_cohort_status")
        or result.get("public_signal_mutation_status")
        or result.get("model_priced_path_simulator_status")
        or result.get("public_cohort_walk_forward_status")
        or result.get("public_paper_champion_gate_status")
        or result.get("public_signal_deepening_status")
        or result.get("scoreboard_status")
        or result.get("live_gate_status")
        or result.get("validation_status")
        or "ok"
    )
    return record_with_hash({
        "artifact_type": "public_market_signal_mutation_deepening_v2_step",
        "step_id": step_id,
        "status": status,
        "summary_hash": result.get("summary_hash", ""),
        "live_trading_enabled": bool(result.get("live_trading_enabled", False)),
    }, "record_hash")


def deepening_status(champion_summary: dict[str, object], lake_summary: dict[str, object], deepening_summary: dict[str, object]) -> str:
    if str(lake_summary.get("public_lake_final_state_status", "")) != "public_lake_locked_clean":
        return "public_lake_degraded_repair_required"
    champion_count = int(champion_summary.get("public_paper_champion_count", 0))
    near_count = int(champion_summary.get("near_champion_count", 0))
    if champion_count > 0:
        return "public_paper_champions_found_live_gate_locked"
    if near_count > 0 and int(deepening_summary.get("mutations_generated", 0)) > 0:
        return "near_champions_improved_no_full_champion"
    return "no_champion_yet_signal_density_expanded"


def next_recommended_target(status: str) -> str:
    if status == "public_paper_champions_found_live_gate_locked":
        return "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1"
    if status == "near_champions_improved_no_full_champion":
        return "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V3"
    if status == "no_champion_yet_signal_density_expanded":
        return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1"
    if status == "public_lake_degraded_repair_required":
        return "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    return "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1"


def build_orchestrator_summary(
    status: str,
    lake_summary: dict[str, object],
    signal_summary: dict[str, object],
    simulator_summary: dict[str, object],
    tournament_summary: dict[str, object],
    champion_summary: dict[str, object],
    deepening_summary: dict[str, object],
    scoreboard_summary: dict[str, object],
    live_gate_summary: dict[str, object],
    handoff: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_type": "public_market_signal_mutation_deepening_v2_summary",
        "public_market_signal_mutation_deepening_version": "dopey-public-market-signal-mutation-deepening-v2",
        "public_signal_deepening_status": status,
        "active_public_symbol_count": lake_summary.get("active_public_symbol_count", 0),
        "active_fixture_symbol_count": lake_summary.get("active_fixture_symbol_count", 0),
        "public_rows_active": lake_summary.get("public_rows_active", 0),
        "signal_candidate_count": signal_summary.get("signal_variant_count", 0),
        "near_champion_expansion_count": signal_summary.get("near_champion_expansion_count", 0),
        "simulated_trade_count": simulator_summary.get("simulated_trade_count", 0),
        "cohort_counts": tournament_summary.get("cohort_counts", {}),
        "strategy_count": tournament_summary.get("strategy_count", 0),
        "split_count": tournament_summary.get("split_count", 0),
        "top_strategy": tournament_summary.get("top_strategy", ""),
        "top_cohort_level": tournament_summary.get("top_cohort_level", ""),
        "top_net_pnl": tournament_summary.get("top_net_pnl", 0.0),
        "top_profit_factor": tournament_summary.get("top_profit_factor", 0.0),
        "top_max_drawdown": tournament_summary.get("top_max_drawdown", 0.0),
        "top_sample_count": tournament_summary.get("top_sample_count", 0),
        "top_split_pass_rate": tournament_summary.get("top_split_pass_rate", 0.0),
        "near_champion_count": champion_summary.get("near_champion_count", 0),
        "sample_repair_candidate_count": champion_summary.get("sample_repair_candidate_count", 0),
        "walk_forward_repair_candidate_count": champion_summary.get("walk_forward_repair_candidate_count", 0),
        "public_paper_champion_count": champion_summary.get("public_paper_champion_count", 0),
        "champion_names": champion_summary.get("champion_names", []),
        "killed_cohort_count": deepening_summary.get("kill_queue_count", 0),
        "mutation_queue_count": deepening_summary.get("mutations_generated", 0),
        "robinhood_official_market_data_lane_allowed": True,
        "live_gate_status": live_gate_summary.get("live_gate_status", ""),
        "live_trading_enabled": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "real_orders_placed": False,
        "shared_copy_status": handoff.get("shared_copy_status", "not_attempted"),
        "next_recommended_target": next_recommended_target(status),
    }


def write_validation_summary(validation_status: str) -> dict[str, object]:
    timeout_records = read_jsonl_file(TIMEOUT_RECORDS_PATH)
    summary = {
        "artifact_type": "public_market_signal_mutation_deepening_v2_validation_summary",
        "validation_status": validation_status,
        "timeout_records": timeout_records,
        "timeout_recorded_as_pass": False,
        "targeted_test_command": ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_market_signal_mutation_deepening_v2.py -q",
        "live_trading_enabled": False,
    }
    return write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)


def write_bundle_docs(
    lake_summary: dict[str, object],
    signal_summary: dict[str, object],
    simulator_summary: dict[str, object],
    tournament_summary: dict[str, object],
    champion_summary: dict[str, object],
    deepening_summary: dict[str, object],
    scoreboard_summary: dict[str, object],
    live_gate_summary: dict[str, object],
    validation_summary: dict[str, object],
) -> dict[str, object]:
    REPORT_PATH.write_text(render_report(lake_summary, signal_summary, simulator_summary, tournament_summary, champion_summary, deepening_summary, scoreboard_summary, live_gate_summary, validation_summary), encoding="utf-8")
    LEDGER_PATH.write_text(render_ledger(), encoding="utf-8")
    COMMANDS_PATH.write_text(render_commands(), encoding="utf-8")
    return {
        "artifact_type": "public_signal_deepening_v2_docs",
        "report_path": str(REPORT_PATH),
        "ledger_path": str(LEDGER_PATH),
        "commands_path": str(COMMANDS_PATH),
        "live_trading_enabled": False,
    }


def render_report(lake_summary, signal_summary, simulator_summary, tournament_summary, champion_summary, deepening_summary, scoreboard_summary, live_gate_summary, validation_summary) -> str:
    lines = [
        "# DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_REPORT",
        "",
        "## Public lake state",
        f"- public_lake_final_state_status: `{lake_summary.get('public_lake_final_state_status')}`",
        f"- active_public_symbol_count: `{lake_summary.get('active_public_symbol_count')}`",
        f"- active_fixture_symbol_count: `{lake_summary.get('active_fixture_symbol_count')}`",
        f"- public_rows_active: `{lake_summary.get('public_rows_active')}`",
        "",
        "## Strategy-cohort correction",
        "- Cohort canonicalizer attaches variant_id, micro_cohort_id, setup_cohort_id, family_cohort_id, regime_cohort_id, symbol_cluster_cohort_id, canonical_champion_id.",
        f"- micro_cohort_count: `{tournament_summary.get('cohort_counts', {}).get('micro_cohort_id', 0)}`",
        f"- setup_cohort_count: `{tournament_summary.get('cohort_counts', {}).get('setup_cohort_id', 0)}`",
        "",
        "## Signal density",
        f"- signal_candidate_count: `{signal_summary.get('signal_variant_count')}`",
        f"- near_champion_expansion_count: `{signal_summary.get('near_champion_expansion_count')}`",
        f"- unique_micro_cohort_count: `{signal_summary.get('unique_micro_cohort_count')}`",
        "",
        "## Simulated trades",
        f"- simulated_trade_count: `{simulator_summary.get('simulated_trade_count')}`",
        f"- long_call_count: `{simulator_summary.get('long_call_count')}`",
        f"- long_put_count: `{simulator_summary.get('long_put_count')}`",
        f"- short_option_count: `{simulator_summary.get('short_option_count')}`",
        f"- spread_structure_count: `{simulator_summary.get('spread_structure_count')}`",
        f"- fixture_trade_count: `{simulator_summary.get('fixture_trade_count')}`",
        "",
        "## Cohort tournament",
        f"- top_strategy: `{tournament_summary.get('top_strategy')}`",
        f"- top_cohort_level: `{tournament_summary.get('top_cohort_level')}`",
        f"- top_net_pnl: `{tournament_summary.get('top_net_pnl')}`",
        f"- top_profit_factor: `{tournament_summary.get('top_profit_factor')}`",
        f"- top_sample_count: `{tournament_summary.get('top_sample_count')}`",
        f"- top_split_pass_rate: `{tournament_summary.get('top_split_pass_rate')}`",
        "",
        "## Champion gate V2",
        f"- champion_gate_status: `{champion_summary.get('public_paper_champion_gate_status')}`",
        f"- public_paper_champion_count: `{champion_summary.get('public_paper_champion_count')}`",
        f"- champion_names: `{champion_summary.get('champion_names', [])}`",
        f"- near_champion_count: `{champion_summary.get('near_champion_count')}`",
        f"- sample_repair_candidate_count: `{champion_summary.get('sample_repair_candidate_count')}`",
        f"- walk_forward_repair_candidate_count: `{champion_summary.get('walk_forward_repair_candidate_count')}`",
        f"- top_rejection_reasons: `{champion_summary.get('top_rejection_reasons', {})}`",
        f"- thresholds_lowered: `{champion_summary.get('thresholds_lowered')}`",
        "",
        "## Deep mutation loop V2",
        f"- generation_count: `{deepening_summary.get('generation_count')}`",
        f"- mutation_queue_count: `{deepening_summary.get('mutations_generated')}`",
        f"- killed_cohort_count: `{deepening_summary.get('kill_queue_count')}`",
        f"- repair_queue_count: `{deepening_summary.get('repair_queue_count')}`",
        "",
        "## Scoreboard V4",
        f"- total_public_paper_pnl: `{scoreboard_summary.get('total_public_paper_pnl')}`",
        f"- trade_count: `{scoreboard_summary.get('trade_count')}`",
        "",
        "## Live gate V2",
        f"- live_gate_status: `{live_gate_summary.get('live_gate_status')}`",
        f"- live_trading_enabled: `{live_gate_summary.get('live_trading_enabled')}`",
        f"- env_present: `{live_gate_summary.get('env_present')}`",
        "- Robinhood policy: official agent/MCP market-data access allowed for research/paper scoring if official terms permit; unofficial access, scraping, reverse-engineering, and live trading blocked.",
        "",
        "## Validation",
        f"- validation_status: `{validation_summary.get('validation_status')}`",
        "- timeout remains inconclusive, not pass.",
        "",
        "## Next target",
        f"- next_recommended_target: `{next_recommended_target(deepening_status(champion_summary, lake_summary, deepening_summary))}`",
        "",
        "No live readiness or profitability claim is made. This is public-data paper research only. No git commit performed.",
    ]
    return "\n".join(lines) + "\n"


def render_ledger() -> str:
    artifact_paths_list = [
        "artifacts/dopey/public_signal_deepening/public_lake_final_state_lock_v2_summary.json",
        "artifacts/dopey/public_signal_deepening/strategy_cohort_summary.json",
        "artifacts/dopey/signals/public_signal_mutation_factory_v4_summary.json",
        "artifacts/dopey/signals/public_signal_mutation_candidates_v4.jsonl",
        "artifacts/dopey/signals/near_champion_signal_expansion_v4.jsonl",
        "artifacts/dopey/signals/public_signal_density_schedule_v4.jsonl",
        "artifacts/dopey/options_engine/model_priced_path_simulator_v4_summary.json",
        "artifacts/dopey/options_engine/model_priced_path_simulator_v4_trades.jsonl",
        "artifacts/dopey/tournament/public_cohort_walk_forward_tournament_v4_summary.json",
        "artifacts/dopey/tournament/public_cohort_tournament_leaderboard_v4.jsonl",
        "artifacts/dopey/champions/public_paper_champion_gate_v2_summary.json",
        "artifacts/dopey/champions/public_paper_champion_gate_v2_near_champions.jsonl",
        "artifacts/dopey/champions/public_paper_champion_gate_v2_sample_repair_plan.jsonl",
        "artifacts/dopey/evolution/public_signal_deepening_loop_v2_summary.json",
        "artifacts/dopey/evolution/cohort_loser_elimination_v2.jsonl",
        "artifacts/dopey/scoreboard/public_signal_deepening_scoreboard_v4.json",
        "artifacts/dopey/scoreboard/public_signal_deepening_dashboard_v4.html",
        "artifacts/dopey/live_gate/public_signal_deepening_live_gate_status_v2.json",
        "artifacts/dopey/public_signal_deepening/public_market_signal_mutation_deepening_v2_summary.json",
        "artifacts/dopey/public_signal_deepening/public_market_signal_mutation_deepening_v2_validation_summary.json",
    ]
    lines = ["# DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_ARTIFACT_LEDGER", ""]
    for path in artifact_paths_list:
        lines.append(f"- `{path}`")
    return "\n".join(lines) + "\n"


def render_commands() -> str:
    commands = [
        ".\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_market_signal_mutation_deepening_v2",
        ".\\.venv\\Scripts\\python.exe -m dopey_market_intake.run_public_lake_final_state_lock_v2",
        ".\\.venv\\Scripts\\python.exe -m dopey_strategy_cohorts.run_strategy_id_canonicalizer",
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_engine.run_public_signal_mutation_factory_v4",
        ".\\.venv\\Scripts\\python.exe -m dopey_options_engine.run_model_priced_path_simulator_v4",
        ".\\.venv\\Scripts\\python.exe -m dopey_tournament.run_public_cohort_walk_forward_tournament_v4",
        ".\\.venv\\Scripts\\python.exe -m dopey_champion.run_public_paper_champion_gate_v2",
        ".\\.venv\\Scripts\\python.exe -m dopey_evolution.run_public_signal_deepening_loop_v2",
        ".\\.venv\\Scripts\\python.exe -m dopey_scoreboard.run_public_signal_deepening_scoreboard_v4",
        ".\\.venv\\Scripts\\python.exe -m dopey_live_gate.run_public_signal_deepening_live_gate_status_v2",
        ".\\.venv\\Scripts\\python.exe -m pytest tests/test_public_market_signal_mutation_deepening_v2.py -q",
    ]
    lines = ["# DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_COMMANDS", "", "All commands use the explicit repo venv. No live broker/order commands.", ""]
    for command in commands:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_handoff_file_list() -> list[Path]:
    raw_paths = [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        DEEPENING_ROOT / "public_lake_final_state_lock_v2_summary.json",
        DEEPENING_ROOT / "strategy_cohort_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "signals" / "public_signal_mutation_factory_v4_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "options_engine" / "model_priced_path_simulator_v4_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "tournament" / "public_cohort_walk_forward_tournament_v4_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "champions" / "public_paper_champion_gate_v2_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "evolution" / "public_signal_deepening_loop_v2_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_signal_deepening_scoreboard_v4.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_signal_deepening_dashboard_v4.html",
        REPO_ROOT / "artifacts" / "dopey" / "live_gate" / "public_signal_deepening_live_gate_status_v2.json",
        SUMMARY_PATH,
        VALIDATION_SUMMARY_PATH,
        TIMEOUT_RECORDS_PATH,
    ]
    return [path for path in raw_paths if path.exists()]


def copy_shared_handoff(files: list[Path]) -> dict[str, object]:
    roots = [
        Path("C:/Users/chris/Desktop/Shared Folder"),
        Path("C:/Users/CH/Desktop/Shared Folder"),
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


def artifact_paths() -> dict[str, str]:
    return {
        "public_market_signal_mutation_deepening_v2_summary": str(SUMMARY_PATH),
        "public_market_signal_mutation_deepening_v2_steps": str(STEPS_PATH),
        "public_market_signal_mutation_deepening_v2_quality_flags": str(QUALITY_FLAGS_PATH),
        "public_market_signal_mutation_deepening_v2_proof": str(PROOF_PATH),
        "public_market_signal_mutation_deepening_v2_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "public_market_signal_mutation_deepening_v2_timeout_records": str(TIMEOUT_RECORDS_PATH),
    }


def main() -> int:
    summary = run_public_market_signal_mutation_deepening_v2()
    print(json.dumps({
        "public_signal_deepening_status": summary["public_signal_deepening_status"],
        "active_public_symbol_count": summary["active_public_symbol_count"],
        "active_fixture_symbol_count": summary["active_fixture_symbol_count"],
        "signal_candidate_count": summary["signal_candidate_count"],
        "simulated_trade_count": summary["simulated_trade_count"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "near_champion_count": summary["near_champion_count"],
        "live_gate_status": summary["live_gate_status"],
        "next_recommended_target": summary["next_recommended_target"],
        "summary_path": summary["artifact_paths"]["public_market_signal_mutation_deepening_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
