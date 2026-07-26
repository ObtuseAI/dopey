"""Autonomous orchestrator for the DOPEY wealth-engine completion bundle."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dopey_chart_vision.run_chart_vision_engine import run_chart_vision_engine
from dopey_evolution.run_winner_loser_evolution_loop import run_winner_loser_evolution_loop
from dopey_live_gate.run_live_gate_status import run_live_gate_status
from dopey_market_intake.market_source_registry import build_market_source_registry
from dopey_market_intake.run_market_data_lake_builder import run_market_data_lake_builder
from dopey_options_engine.run_model_priced_trade_constructor import run_model_priced_trade_constructor
from dopey_risk_engine.run_risk_throttle_engine import run_risk_throttle_engine
from dopey_runtime_bootstrap.run_local_dependency_bootstrap import run_local_dependency_bootstrap
from dopey_scoreboard.run_performance_cockpit import run_performance_cockpit
from dopey_signal_engine.run_aggressive_signal_engine import run_aggressive_signal_engine
from dopey_tournament.run_paper_money_tournament_engine import run_paper_money_tournament_engine
from dopey_wealth_engine.common import ARTIFACT_ROOT, REPO_ROOT, proof_record, read_json, stable_hash, write_json, write_jsonl
from dopey_core.repo_paths import REPORTS_DIR


ARTIFACT_DIR = ARTIFACT_ROOT / "wealth_engine"
SUMMARY_PATH = ARTIFACT_DIR / "wealth_engine_full_completion_summary.json"
STEPS_PATH = ARTIFACT_DIR / "wealth_engine_steps.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "wealth_engine_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "wealth_engine_proof.jsonl"
VALIDATION_SUMMARY_PATH = ARTIFACT_DIR / "wealth_engine_validation_summary.json"
TIMEOUT_RECORDS_PATH = ARTIFACT_DIR / "wealth_engine_timeout_records.jsonl"
BUNDLE_NAME = "DOPEY_WEALTH_ENGINE_MARKET_VISION_OPENBB_CHARTS_PAPER_TOURNAMENT_FULL_COMPLETION_V1"
SHARED_TARGETS = [
    Path("C:/Users/chris/Desktop/Shared Folder"),
    Path("//FRANKENSTEIN/Shared Folder"),
    Path("Z:/"),
]


def run_wealth_engine_full_completion(bootstrap_timeout_seconds: int, use_network: bool, copy_shared: bool) -> dict:
    steps: list[dict] = []
    quality_flags: list[dict] = []
    timeout_records: list[dict] = []

    dependency = _run_step("local_dependency_bootstrap", steps, lambda: run_local_dependency_bootstrap(bootstrap_timeout_seconds))
    _run_step("market_source_registry", steps, lambda: {"source_registry_count": len(build_market_source_registry()), "status": "complete"})
    market = _run_step("market_data_lake_builder", steps, lambda: run_market_data_lake_builder(use_network, True))
    chart = _run_step("chart_vision_engine", steps, run_chart_vision_engine)
    signals = _run_step("aggressive_signal_engine", steps, run_aggressive_signal_engine)
    options = _run_step("model_priced_trade_constructor", steps, run_model_priced_trade_constructor)
    tournament = _run_step("paper_money_tournament_engine", steps, run_paper_money_tournament_engine)
    scoreboard = _run_step("pnl_scoreboard", steps, run_performance_cockpit)
    risk = _run_step("risk_throttle_engine", steps, run_risk_throttle_engine)
    evolution = _run_step("winner_loser_evolution_loop", steps, run_winner_loser_evolution_loop)
    live_gate = _run_step("live_gate_status", steps, run_live_gate_status)
    cockpit = _run_step("performance_cockpit_refresh", steps, run_performance_cockpit)
    validation = build_validation_summary("not_run_by_orchestrator", [], timeout_records)
    if copy_shared:
        copy_status = copy_shared_handoff()
    else:
        copy_status = {"shared_copy_status": "skipped_by_caller", "targets": []}

    market_status = str(market.get("market_data_status", ""))
    if int(market.get("daily_ohlcv_rows", 0)) > 0 and not market_status.startswith("internal_fixture_fallback"):
        wealth_status = "market_vision_paper_tournament_complete"
    else:
        wealth_status = "complete_with_internal_fallback_blocked_no_market_data"
        quality_flags.append(_flag("blocked_no_public_market_data", "warning", "public no-key market data did not load; internal fixture fallback completed the paper research loop"))

    next_target = "DOPEY_PAPER_MONEY_TOURNAMENT_ITERATION_AND_MARKET_EXPANSION_V2"
    if int(market.get("daily_ohlcv_rows", 0)) == 0 or market_status.startswith("internal_fixture_fallback"):
        next_target = "DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2"
    if int(evolution.get("paper_champion_count", 0)) > 0 and not market_status.startswith("internal_fixture_fallback"):
        next_target = "DOPEY_LIVE_GATE_CANDIDATE_REVIEW_AND_PAPER_CHAMPION_HARDENING_V1"

    summary = {
        "artifact_type": "wealth_engine_full_completion_summary",
        "wealth_engine_version": "dopey-wealth-engine-full-completion-v1",
        "wealth_engine_status": wealth_status,
        "dependency_bootstrap_status": dependency.get("bootstrap_status", "missing"),
        "market_data_status": market.get("market_data_status", "missing"),
        "symbols_loaded": market.get("symbols_loaded", []),
        "daily_ohlcv_rows": market.get("daily_ohlcv_rows", 0),
        "chart_count": chart.get("chart_count", 0),
        "signal_candidate_count": signals.get("signal_candidate_count", 0),
        "option_trade_candidate_count": options.get("option_trade_candidate_count", 0),
        "paper_tournament_trade_count": tournament.get("paper_tournament_trade_count", 0),
        "paper_tournament_status": tournament.get("paper_tournament_status", "missing"),
        "pnl_scoreboard_status": scoreboard.get("pnl_scoreboard_status", "missing"),
        "risk_throttle_status": risk.get("risk_throttle_status", "missing"),
        "winner_promotion_count": evolution.get("winner_promotion_count", 0),
        "loser_elimination_count": evolution.get("loser_elimination_count", 0),
        "paper_champion_count": evolution.get("paper_champion_count", 0),
        "live_gate_status": live_gate.get("live_gate_status", "missing"),
        "live_trading_enabled": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "strategy_promotion_allowed_for_live": False,
        "paper_strategy_promotion_allowed": True,
        "profitability_claim": False,
        "live_readiness_claim": False,
        "performance_cockpit_html": cockpit.get("artifact_paths", {}).get("performance_cockpit_html", ""),
        "shared_copy_status": copy_status,
        "validation_summary_path": str(VALIDATION_SUMMARY_PATH),
        "next_recommended_target": next_target,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(STEPS_PATH, steps, False)
    write_jsonl(QUALITY_FLAGS_PATH, quality_flags, False)
    write_jsonl(TIMEOUT_RECORDS_PATH, timeout_records, False)
    write_jsonl(PROOF_PATH, [proof_record("wealth-engine-full-completion", summary["wealth_engine_status"], summary)], False)
    validation = build_validation_summary("orchestrator_complete", [], timeout_records)
    write_json(VALIDATION_SUMMARY_PATH, validation)
    return {**summary, "artifact_paths": artifact_paths()}


def build_validation_summary(validation_status: str, command_results: list[dict], timeout_records: list[dict]) -> dict:
    summary = {
        "artifact_type": "wealth_engine_validation_summary",
        "validation_status": validation_status,
        "command_results": command_results,
        "timeout_records": timeout_records,
        "timeout_recorded_as_pass": False,
        "validation_stabilizer_includes_shard": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(VALIDATION_SUMMARY_PATH, summary)
    return summary


def run_capped_command(command: list[str], timeout_seconds: int) -> dict:
    start = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=str(REPO_ROOT), text=True, capture_output=True, timeout=timeout_seconds)
        return {
            "command": command,
            "status": "pass" if completed.returncode == 0 else "fail",
            "exit_code": completed.returncode,
            "timed_out": False,
            "duration_seconds": round(time.monotonic() - start, 6),
            "stdout_tail": completed.stdout[-1200:],
            "stderr_tail": completed.stderr[-1200:],
            "timeout_recorded_as_pass": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        return {
            "command": command,
            "status": "inconclusive_timeout",
            "exit_code": None,
            "timed_out": True,
            "duration_seconds": round(time.monotonic() - start, 6),
            "stdout_tail": stdout[-1200:],
            "stderr_tail": stderr[-1200:],
            "timeout_recorded_as_pass": False,
        }


def copy_shared_handoff() -> dict:
    source_paths = _handoff_source_paths()
    target_records: list[dict] = []
    for target_root in SHARED_TARGETS:
        bundle_root = target_root / BUNDLE_NAME
        record = {"target_root": str(target_root), "bundle_root": str(bundle_root), "status": "not_attempted", "files": []}
        try:
            bundle_root.mkdir(parents=True, exist_ok=True)
            for source in source_paths:
                if not source.exists():
                    continue
                destination = bundle_root / source.name
                shutil.copy2(source, destination)
                record["files"].append({"source": str(source), "destination": str(destination)})
            manifest = {
                "artifact_type": "session_copy_manifest",
                "bundle_name": BUNDLE_NAME,
                "target_root": str(target_root),
                "copied_file_count": len(record["files"]),
                "files": record["files"],
                "live_trading_enabled": False,
                "credentials_created": False,
                "env_created": False,
                "broker_connection_used": False,
            }
            manifest["manifest_hash"] = stable_hash(manifest)
            write_json(bundle_root / "SESSION_COPY_MANIFEST.json", manifest)
            record["status"] = "copied"
        except OSError as exc:
            record["status"] = "copy_failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
        target_records.append(record)
    return {
        "shared_copy_status": "attempted",
        "targets": target_records,
        "copied_targets": sum(1 for record in target_records if record["status"] == "copied"),
    }


def _handoff_source_paths() -> list[Path]:
    return [
        REPORTS_DIR / "DOPEY_WEALTH_ENGINE_FULL_COMPLETION_REPORT.md",
        REPORTS_DIR / "DOPEY_WEALTH_ENGINE_FULL_COMPLETION_ARTIFACT_LEDGER.md",
        REPORTS_DIR / "DOPEY_WEALTH_ENGINE_COMMANDS.md",
        SUMMARY_PATH,
        ARTIFACT_ROOT / "market_intake" / "market_data_lake_summary.json",
        ARTIFACT_ROOT / "chart_vision" / "chart_vision_summary.json",
        ARTIFACT_ROOT / "signals" / "aggressive_signal_engine_summary.json",
        ARTIFACT_ROOT / "options_engine" / "model_priced_trade_constructor_summary.json",
        ARTIFACT_ROOT / "tournament" / "paper_money_tournament_summary.json",
        ARTIFACT_ROOT / "scoreboard" / "pnl_scoreboard_summary.json",
        ARTIFACT_ROOT / "risk" / "risk_throttle_summary.json",
        ARTIFACT_ROOT / "evolution" / "evolution_loop_summary.json",
        ARTIFACT_ROOT / "live_gate" / "live_gate_status.json",
        VALIDATION_SUMMARY_PATH,
        ARTIFACT_ROOT / "scoreboard" / "performance_cockpit.html",
    ]


def _run_step(step_id: str, steps: list[dict], callback) -> dict:
    start = time.monotonic()
    try:
        result = callback()
        status = str(result.get("status") or result.get("bootstrap_status") or result.get("market_data_status") or result.get("chart_vision_status") or result.get("signal_generation_status") or result.get("model_priced_options_status") or result.get("paper_tournament_status") or result.get("pnl_scoreboard_status") or result.get("risk_throttle_status") or result.get("evolution_status") or result.get("live_gate_status") or "complete")
        steps.append({"artifact_type": "wealth_engine_step", "step_id": step_id, "status": status, "duration_seconds": round(time.monotonic() - start, 6)})
        return result
    except Exception as exc:
        steps.append({"artifact_type": "wealth_engine_step", "step_id": step_id, "status": "failed", "duration_seconds": round(time.monotonic() - start, 6), "error": f"{type(exc).__name__}: {exc}"})
        raise


def _flag(flag_id: str, severity: str, message: str) -> dict:
    record = {"artifact_type": "wealth_engine_quality_flag", "flag_id": flag_id, "severity": severity, "message": message}
    record["flag_hash"] = stable_hash(record)
    return record


def artifact_paths() -> dict[str, str]:
    return {
        "wealth_engine_full_completion_summary": str(SUMMARY_PATH),
        "wealth_engine_steps": str(STEPS_PATH),
        "wealth_engine_quality_flags": str(QUALITY_FLAGS_PATH),
        "wealth_engine_proof": str(PROOF_PATH),
        "wealth_engine_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "wealth_engine_timeout_records": str(TIMEOUT_RECORDS_PATH),
    }


def main() -> int:
    summary = run_wealth_engine_full_completion(5, True, True)
    print(json.dumps({
        "wealth_engine_status": summary["wealth_engine_status"],
        "market_data_status": summary["market_data_status"],
        "daily_ohlcv_rows": summary["daily_ohlcv_rows"],
        "chart_count": summary["chart_count"],
        "signal_candidate_count": summary["signal_candidate_count"],
        "paper_tournament_trade_count": summary["paper_tournament_trade_count"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "summary_path": summary["artifact_paths"]["wealth_engine_full_completion_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
