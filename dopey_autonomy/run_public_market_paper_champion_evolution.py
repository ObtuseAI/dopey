"""Full public-market paper champion evolution orchestrator."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_autonomy.public_champion_common import (
    PUBLIC_CHAMPION_ROOT,
    active_manifest,
    proof_record,
    read_json_file,
    read_jsonl_file,
    sha256_file,
    write_json_file,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_champion.run_public_paper_champion_gate import run_public_paper_champion_gate
from dopey_evolution.public_champion_evolution_loop import run_public_champion_evolution_generations
from dopey_live_gate.run_public_champion_live_gate_status import run_public_champion_live_gate_status
from dopey_market_intake.market_data_cache_manager import run_market_data_cache_manager
from dopey_market_intake.market_lake_public_promotion import run_market_lake_public_promotion
from dopey_market_intake.public_lake_freeze_guard import run_public_lake_freeze_guard
from dopey_market_intake.public_universe_expansion_v2 import expand_public_universe, candidate_symbol_universe_v2
from dopey_options_engine.run_model_priced_path_simulator_v3 import run_model_priced_path_simulator_v3
from dopey_risk_engine.run_public_champion_risk_engine_v3 import run_public_champion_risk_engine_v3
from dopey_scoreboard.run_public_champion_scoreboard_v3 import run_public_champion_scoreboard_v3
from dopey_signal_engine.run_public_signal_mutation_factory_v3 import run_public_signal_mutation_factory_v3
from dopey_tournament.run_public_walk_forward_tournament_v3 import run_public_walk_forward_tournament_v3
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


SUMMARY_PATH = PUBLIC_CHAMPION_ROOT / "public_market_paper_champion_evolution_summary.json"
STEPS_PATH = PUBLIC_CHAMPION_ROOT / "public_market_paper_champion_evolution_steps.jsonl"
QUALITY_FLAGS_PATH = PUBLIC_CHAMPION_ROOT / "public_market_paper_champion_evolution_quality_flags.jsonl"
PROOF_PATH = PUBLIC_CHAMPION_ROOT / "public_market_paper_champion_evolution_proof.jsonl"
VALIDATION_SUMMARY_PATH = PUBLIC_CHAMPION_ROOT / "public_market_paper_champion_validation_summary.json"
TIMEOUT_RECORDS_PATH = PUBLIC_CHAMPION_ROOT / "public_market_paper_champion_timeout_records.jsonl"

REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_COMMANDS.md"

HANDOFF_FOLDER_NAME = "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1"


def run_public_market_paper_champion_evolution(refresh_missing_public: bool, generation_cap: int) -> dict[str, object]:
    steps: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    freeze_start = record_step("public_lake_freeze_guard", run_public_lake_freeze_guard())
    steps.append(freeze_start)
    universe_summary = expand_public_universe(candidate_symbol_universe_v2(), refresh_missing_public, 180)
    steps.append(record_step("public_universe_expansion_v2", universe_summary))
    steps.append(record_step("market_cache_manager", run_market_data_cache_manager(14)))
    steps.append(record_step("market_lake_public_promotion", run_market_lake_public_promotion(False)))
    chart_summary = run_chart_vision_stage()
    steps.append(record_step("chart_vision", chart_summary))
    signal_summary = run_public_signal_mutation_factory_v3()
    steps.append(record_step("public_signal_mutation_factory_v3", signal_summary))
    simulator_summary = run_model_priced_path_simulator_v3()
    steps.append(record_step("model_priced_path_simulator_v3", simulator_summary))
    tournament_summary = run_public_walk_forward_tournament_v3()
    steps.append(record_step("public_walk_forward_tournament_v3", tournament_summary))
    risk_summary = run_public_champion_risk_engine_v3()
    steps.append(record_step("public_champion_risk_engine_v3", risk_summary))
    champion_summary = run_public_paper_champion_gate()
    steps.append(record_step("public_paper_champion_gate", champion_summary))
    scoreboard_summary = run_public_champion_scoreboard_v3()
    steps.append(record_step("public_champion_scoreboard_v3_initial", scoreboard_summary))
    evolution_summary = run_public_champion_evolution_generations(generation_cap)
    steps.append(record_step("public_champion_evolution_loop", evolution_summary))
    scoreboard_summary = run_public_champion_scoreboard_v3()
    steps.append(record_step("public_champion_scoreboard_v3_final", scoreboard_summary))
    live_gate_summary = run_public_champion_live_gate_status()
    steps.append(record_step("public_champion_live_gate_status", live_gate_summary))
    freeze_final = run_public_lake_freeze_guard()
    steps.append(record_step("public_lake_freeze_guard_final", freeze_final))
    validation_summary = write_validation_summary("pending_watchdog_validation", [], [])
    docs = write_bundle_docs(freeze_final, universe_summary, signal_summary, simulator_summary, tournament_summary, champion_summary, scoreboard_summary, evolution_summary, risk_summary, live_gate_summary, validation_summary)
    steps.append(record_step("audit_report_export_review_docs", docs))
    handoff = copy_shared_handoff(build_handoff_file_list(validation_summary))
    steps.append(record_step("shared_handoff", handoff))
    if int(freeze_final.get("active_fixture_symbol_count", 0)) != 0:
        quality_flags.append({"artifact_type": "public_market_paper_champion_quality_flag", "flag_id": "fixture_active_symbols_present", "severity": "error"})
    status = public_champion_status(champion_summary, freeze_final, evolution_summary)
    summary = build_orchestrator_summary(status, freeze_final, universe_summary, signal_summary, simulator_summary, tournament_summary, champion_summary, scoreboard_summary, evolution_summary, risk_summary, live_gate_summary, handoff)
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    if not TIMEOUT_RECORDS_PATH.exists():
        write_jsonl_file(TIMEOUT_RECORDS_PATH, [])
    write_jsonl_file(PROOF_PATH, [proof_record("public-market-paper-champion-evolution", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def record_step(step_id: str, result: dict[str, object]) -> dict[str, object]:
    return {
        "artifact_type": "public_market_paper_champion_evolution_step",
        "step_id": step_id,
        "status": result.get("public_lake_guard_status") or result.get("public_universe_expansion_status") or result.get("model_priced_path_simulator_status") or result.get("public_walk_forward_status") or result.get("public_paper_champion_gate_status") or result.get("public_champion_evolution_status") or result.get("live_gate_status") or result.get("scoreboard_status") or result.get("public_champion_risk_status") or result.get("chart_vision_status") or result.get("market_data_cache_status") or result.get("active_lake_status") or "ok",
        "summary_hash": result.get("summary_hash", ""),
        "live_trading_enabled": bool(result.get("live_trading_enabled", False)),
    }


def run_chart_vision_stage() -> dict[str, object]:
    manifest = active_manifest()
    file_count = int(manifest.get("file_count", 0))
    existing = read_json_file(REPO_ROOT / "artifacts" / "dopey" / "chart_vision" / "chart_vision_summary.json")
    if file_count > 80 and existing:
        return {
            **existing,
            "chart_vision_status": "charts_reused_watchdog_capped_large_public_lake",
            "watchdog_capped": True,
            "active_public_symbol_count": file_count,
            "live_trading_enabled": False,
        }
    from dopey_chart_vision.run_chart_vision_engine import run_chart_vision_engine

    return run_chart_vision_engine()


def public_champion_status(champion_summary: dict[str, object], freeze_summary: dict[str, object], evolution_summary: dict[str, object]) -> str:
    if str(freeze_summary.get("public_lake_guard_status", "")) != "public_lake_clean":
        return "public_lake_degraded_repair_required"
    if int(champion_summary.get("public_paper_champion_count", 0)) > 0:
        return "public_data_paper_champions_found_live_gate_locked"
    if int(evolution_summary.get("generation_count", 0)) > 0:
        return "no_champion_yet_public_evolution_complete"
    return "public_evolution_incomplete"


def build_orchestrator_summary(
    status: str,
    freeze_summary: dict[str, object],
    universe_summary: dict[str, object],
    signal_summary: dict[str, object],
    simulator_summary: dict[str, object],
    tournament_summary: dict[str, object],
    champion_summary: dict[str, object],
    scoreboard_summary: dict[str, object],
    evolution_summary: dict[str, object],
    risk_summary: dict[str, object],
    live_gate_summary: dict[str, object],
    handoff: dict[str, object],
) -> dict[str, object]:
    manifest = active_manifest()
    next_target = next_recommended_target(status)
    return {
        "artifact_type": "public_market_paper_champion_evolution_summary",
        "public_market_paper_champion_evolution_version": "dopey-public-market-paper-champion-evolution-v1",
        "public_champion_evolution_status": status,
        "active_public_symbol_count": freeze_summary.get("active_public_symbol_count", 0),
        "active_fixture_symbol_count": freeze_summary.get("active_fixture_symbol_count", 0),
        "public_rows_active": manifest.get("row_count", 0),
        "signal_variant_count": signal_summary.get("signal_variant_count", 0),
        "simulated_trade_count": simulator_summary.get("simulated_trade_count", 0),
        "walk_forward_trade_count": tournament_summary.get("trade_count", 0),
        "strategy_count": tournament_summary.get("strategy_count", 0),
        "public_paper_champion_count": champion_summary.get("public_paper_champion_count", 0),
        "live_gate_candidate_locked_count": champion_summary.get("live_gate_candidate_locked_count", 0),
        "top_strategy": tournament_summary.get("top_strategy", ""),
        "top_net_pnl": tournament_summary.get("top_strategy_net_pnl", 0.0),
        "top_profit_factor": tournament_summary.get("top_strategy_profit_factor", 0.0),
        "top_max_drawdown": tournament_summary.get("top_strategy_max_drawdown", 0.0),
        "top_sample_count": tournament_summary.get("top_strategy_sample_count", 0),
        "risk_throttle_count": risk_summary.get("risk_throttle_count", 0),
        "loser_kill_count": evolution_summary.get("losers_killed", 0),
        "mutation_queue_count": evolution_summary.get("mutations_generated", 0),
        "fixture_trade_count": simulator_summary.get("fixture_trade_count", 0),
        "live_trading_enabled": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "real_orders_placed": False,
        "live_gate_status": live_gate_summary.get("live_gate_status", ""),
        "shared_copy_status": handoff.get("shared_copy_status", "not_attempted"),
        "next_recommended_target": next_target,
    }


def next_recommended_target(status: str) -> str:
    if status == "public_data_paper_champions_found_live_gate_locked":
        return "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1"
    if status == "no_champion_yet_public_evolution_complete":
        return "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2"
    if status == "public_lake_degraded_repair_required":
        return "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    return "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2"


def write_validation_summary(validation_status: str, targeted_results: list[dict[str, object]], smoke_results: list[dict[str, object]]) -> dict[str, object]:
    timeout_records = read_jsonl_file(TIMEOUT_RECORDS_PATH)
    summary = {
        "artifact_type": "public_market_paper_champion_validation_summary",
        "validation_status": validation_status,
        "targeted_tests": targeted_results,
        "smokes": smoke_results,
        "timeout_records": timeout_records,
        "timeout_recorded_as_pass": False,
        "collect_only_status": "not_run_by_orchestrator",
        "live_trading_enabled": False,
    }
    return write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)


def write_bundle_docs(
    freeze_summary: dict[str, object],
    universe_summary: dict[str, object],
    signal_summary: dict[str, object],
    simulator_summary: dict[str, object],
    tournament_summary: dict[str, object],
    champion_summary: dict[str, object],
    scoreboard_summary: dict[str, object],
    evolution_summary: dict[str, object],
    risk_summary: dict[str, object],
    live_gate_summary: dict[str, object],
    validation_summary: dict[str, object],
) -> dict[str, object]:
    REPORT_PATH.write_text(render_report(freeze_summary, universe_summary, signal_summary, simulator_summary, tournament_summary, champion_summary, evolution_summary, risk_summary, live_gate_summary, validation_summary), encoding="utf-8")
    LEDGER_PATH.write_text(render_ledger(), encoding="utf-8")
    COMMANDS_PATH.write_text(render_commands(), encoding="utf-8")
    return {
        "artifact_type": "public_champion_docs",
        "report_path": str(REPORT_PATH),
        "ledger_path": str(LEDGER_PATH),
        "commands_path": str(COMMANDS_PATH),
        "scoreboard_path": scoreboard_summary.get("artifact_paths", {}).get("public_champion_scoreboard_v3", ""),
        "live_trading_enabled": False,
    }


def render_report(
    freeze_summary: dict[str, object],
    universe_summary: dict[str, object],
    signal_summary: dict[str, object],
    simulator_summary: dict[str, object],
    tournament_summary: dict[str, object],
    champion_summary: dict[str, object],
    evolution_summary: dict[str, object],
    risk_summary: dict[str, object],
    live_gate_summary: dict[str, object],
    validation_summary: dict[str, object],
) -> str:
    lines = ["# DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_REPORT", ""]
    lines.append(f"- public_lake_guard_status: `{freeze_summary.get('public_lake_guard_status')}`")
    lines.append(f"- real_public_symbol_count: `{freeze_summary.get('active_public_symbol_count')}`")
    lines.append(f"- real_public_row_count: `{active_manifest().get('row_count', 0)}`")
    lines.append(f"- universe_expansion_status: `{universe_summary.get('public_universe_expansion_status')}`")
    lines.append(f"- signal_variants_generated: `{signal_summary.get('signal_variant_count')}`")
    lines.append(f"- path_simulator_status: `{simulator_summary.get('model_priced_path_simulator_status')}`")
    lines.append(f"- simulated_trade_count: `{simulator_summary.get('simulated_trade_count')}`")
    lines.append(f"- walk_forward_status: `{tournament_summary.get('public_walk_forward_status')}`")
    lines.append(f"- top_public_strategy: `{tournament_summary.get('top_strategy')}`")
    lines.append(f"- top_net_pnl: `{tournament_summary.get('top_strategy_net_pnl')}`")
    lines.append(f"- top_profit_factor: `{tournament_summary.get('top_strategy_profit_factor')}`")
    lines.append(f"- top_max_drawdown: `{tournament_summary.get('top_strategy_max_drawdown')}`")
    lines.append(f"- champion_gate_status: `{champion_summary.get('public_paper_champion_gate_status')}`")
    lines.append(f"- champions: `{champion_summary.get('champion_names', [])}`")
    lines.append(f"- rejected_reason_counts: `{champion_summary.get('top_rejection_reasons', {})}`")
    lines.append(f"- mutation_queue: `{evolution_summary.get('mutations_generated')}`")
    lines.append(f"- losers_killed: `{evolution_summary.get('losers_killed')}`")
    lines.append(f"- risk_throttles: `{risk_summary.get('risk_throttle_count')}`")
    lines.append(f"- live_gate: `{live_gate_summary.get('live_gate_status')}`")
    lines.append(f"- live_trading_enabled: `{live_gate_summary.get('live_trading_enabled')}`")
    lines.append(f"- validation_status: `{validation_summary.get('validation_status')}`")
    lines.append("")
    lines.append("No live readiness or profitability claim is made. This is public-data paper research only.")
    return "\n".join(lines) + "\n"


def render_ledger() -> str:
    artifact_paths = [
        "artifacts/dopey/public_champion_evolution/public_lake_freeze_guard_summary.json",
        "artifacts/dopey/public_champion_evolution/public_universe_expansion_v2_summary.json",
        "artifacts/dopey/signals/public_signal_mutation_factory_v3_summary.json",
        "artifacts/dopey/options_engine/model_priced_path_simulator_v3_summary.json",
        "artifacts/dopey/tournament/public_walk_forward_tournament_v3_summary.json",
        "artifacts/dopey/champions/public_paper_champion_gate_summary.json",
        "artifacts/dopey/scoreboard/public_champion_scoreboard_v3.json",
        "artifacts/dopey/evolution/public_champion_evolution_summary.json",
        "artifacts/dopey/risk/public_champion_risk_summary_v3.json",
        "artifacts/dopey/live_gate/public_champion_live_gate_status.json",
        "artifacts/dopey/public_champion_evolution/public_market_paper_champion_evolution_summary.json",
        "artifacts/dopey/public_champion_evolution/public_market_paper_champion_validation_summary.json",
    ]
    lines = ["# DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_ARTIFACT_LEDGER", ""]
    for path in artifact_paths:
        lines.append(f"- `{path}`")
    return "\n".join(lines) + "\n"


def render_commands() -> str:
    commands = [
        ".\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_market_paper_champion_evolution",
        ".\\.venv\\Scripts\\python.exe -m dopey_market_intake.run_public_lake_freeze_guard",
        ".\\.venv\\Scripts\\python.exe -m dopey_market_intake.run_public_universe_expansion_v2",
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_engine.run_public_signal_mutation_factory_v3",
        ".\\.venv\\Scripts\\python.exe -m dopey_options_engine.run_model_priced_path_simulator_v3",
        ".\\.venv\\Scripts\\python.exe -m dopey_tournament.run_public_walk_forward_tournament_v3",
        ".\\.venv\\Scripts\\python.exe -m dopey_champion.run_public_paper_champion_gate",
        ".\\.venv\\Scripts\\python.exe -m dopey_scoreboard.run_public_champion_scoreboard_v3",
        ".\\.venv\\Scripts\\python.exe -m dopey_evolution.run_public_champion_evolution_loop",
        ".\\.venv\\Scripts\\python.exe -m dopey_risk_engine.run_public_champion_risk_engine_v3",
        ".\\.venv\\Scripts\\python.exe -m dopey_live_gate.run_public_champion_live_gate_status",
    ]
    lines = ["# DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_COMMANDS", ""]
    for command in commands:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_handoff_file_list(validation_summary: dict[str, object]) -> list[Path]:
    raw_paths = [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        PUBLIC_CHAMPION_ROOT / "public_lake_freeze_guard_summary.json",
        PUBLIC_CHAMPION_ROOT / "public_universe_expansion_v2_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "options_engine" / "model_priced_path_simulator_v3_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "signals" / "public_signal_mutation_factory_v3_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "tournament" / "public_walk_forward_tournament_v3_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "champions" / "public_paper_champion_gate_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_champion_scoreboard_v3.json",
        REPO_ROOT / "artifacts" / "dopey" / "scoreboard" / "public_champion_dashboard_v3.html",
        REPO_ROOT / "artifacts" / "dopey" / "evolution" / "public_champion_evolution_summary.json",
        REPO_ROOT / "artifacts" / "dopey" / "risk" / "public_champion_risk_summary_v3.json",
        REPO_ROOT / "artifacts" / "dopey" / "live_gate" / "public_champion_live_gate_status.json",
        SUMMARY_PATH,
        VALIDATION_SUMMARY_PATH,
        TIMEOUT_RECORDS_PATH,
    ]
    return [path for path in raw_paths if path.exists()]


def copy_shared_handoff(files: list[Path]) -> dict[str, object]:
    roots = [
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


def artifact_paths() -> dict[str, str]:
    return {
        "public_market_paper_champion_evolution_summary": str(SUMMARY_PATH),
        "public_market_paper_champion_evolution_steps": str(STEPS_PATH),
        "public_market_paper_champion_evolution_quality_flags": str(QUALITY_FLAGS_PATH),
        "public_market_paper_champion_evolution_proof": str(PROOF_PATH),
        "public_market_paper_champion_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "public_market_paper_champion_timeout_records": str(TIMEOUT_RECORDS_PATH),
    }


def main() -> int:
    summary = run_public_market_paper_champion_evolution(False, 5)
    print(json.dumps({
        "public_champion_evolution_status": summary["public_champion_evolution_status"],
        "active_public_symbol_count": summary["active_public_symbol_count"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "top_strategy": summary["top_strategy"],
        "next_recommended_target": summary["next_recommended_target"],
        "summary_path": summary["artifact_paths"]["public_market_paper_champion_evolution_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
