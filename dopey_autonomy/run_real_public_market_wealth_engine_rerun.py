"""Rerun DOPEY's wealth engine on real public no-key market data."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from dopey_chart_vision.run_chart_vision_engine import run_chart_vision_engine
from dopey_evolution.run_winner_loser_evolution_loop import run_winner_loser_evolution_loop
from dopey_live_gate.run_live_gate_status import run_live_gate_status
from dopey_market_intake.market_data_cache_manager import run_market_data_cache_manager
from dopey_market_intake.market_lake_public_promotion import run_market_lake_public_promotion
from dopey_market_intake.market_universe_expander import run_market_universe_expander
from dopey_market_intake.provider_health_diagnostics import run_provider_health_diagnostics
from dopey_market_intake.provider_ladder_v2 import run_public_ohlcv_provider_ladder_v2
from dopey_market_intake.public_ohlcv_provider_models import PRIMARY_UNIVERSE
from dopey_market_intake.run_market_data_lake_builder import run_market_data_lake_builder
from dopey_options_engine.run_model_priced_trade_constructor import run_model_priced_trade_constructor
from dopey_risk_engine.run_risk_throttle_engine import run_risk_throttle_engine
from dopey_runtime_bootstrap.provider_install_repair import run_provider_install_repair
from dopey_scoreboard.run_performance_cockpit import run_performance_cockpit
from dopey_scoreboard.public_vs_fixture_scoreboard_split import run_public_vs_fixture_scoreboard_split
from dopey_signal_engine.run_aggressive_signal_engine import run_aggressive_signal_engine
from dopey_tournament.run_paper_money_tournament_engine import run_paper_money_tournament_engine
from dopey_wealth_engine.common import ARTIFACT_ROOT, REPO_ROOT, proof_record, stable_hash, write_json, write_jsonl
from dopey_core.repo_paths import REPORTS_DIR


ARTIFACT_DIR = ARTIFACT_ROOT / "real_public_wealth"
SUMMARY_PATH = ARTIFACT_DIR / "real_public_market_wealth_rerun_summary.json"
STEPS_PATH = ARTIFACT_DIR / "real_public_market_wealth_rerun_steps.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "real_public_market_wealth_rerun_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "real_public_market_wealth_rerun_proof.jsonl"
VALIDATION_PATH = ARTIFACT_DIR / "real_public_market_wealth_validation_summary.json"
TIMEOUT_RECORDS_PATH = ARTIFACT_DIR / "real_public_market_wealth_timeout_records.jsonl"
BUNDLE_NAME = "DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2"
SHARED_TARGETS = [
    Path("C:/Users/chris/Desktop/Shared Folder"),
    Path("//FRANKENSTEIN/Shared Folder"),
    Path("Z:/"),
]


def run_real_public_market_wealth_engine_rerun(copy_shared: bool, install_openbb: bool) -> dict:
    steps: list[dict] = []
    quality_flags: list[dict] = []
    timeout_records: list[dict] = []
    provider_install = _run_step("provider_install_repair", steps, lambda: run_provider_install_repair(90, 180, install_openbb))
    diagnostics = _run_step("provider_health_diagnostics", steps, lambda: run_provider_health_diagnostics(list(PRIMARY_UNIVERSE), 12))
    provider_ladder = _run_step("public_ohlcv_provider_ladder_v2", steps, lambda: run_public_ohlcv_provider_ladder_v2(list(PRIMARY_UNIVERSE), False, 20))
    if int(provider_ladder.get("symbol_success_count", 0)) >= len(PRIMARY_UNIVERSE):
        _run_step("market_universe_expander", steps, lambda: run_market_universe_expander(15))
    cache = _run_step("market_data_cache_manager", steps, lambda: run_market_data_cache_manager(14))
    promotion = _run_step("market_lake_public_promotion", steps, lambda: run_market_lake_public_promotion(True))
    market = _run_step("market_data_lake_builder_public_first", steps, lambda: run_market_data_lake_builder(True, True))
    chart = _run_step("chart_vision_engine", steps, run_chart_vision_engine)
    signals = _run_step("aggressive_signal_engine", steps, run_aggressive_signal_engine)
    options = _run_step("model_priced_trade_constructor", steps, run_model_priced_trade_constructor)
    tournament = _run_step("paper_money_tournament_engine", steps, run_paper_money_tournament_engine)
    scoreboard = _run_step("pnl_scoreboard", steps, run_performance_cockpit)
    split = _run_step("public_vs_fixture_scoreboard_split", steps, run_public_vs_fixture_scoreboard_split)
    risk = _run_step("risk_throttle_engine", steps, run_risk_throttle_engine)
    evolution = _run_step("winner_loser_evolution_loop", steps, run_winner_loser_evolution_loop)
    live_gate = _run_step("live_gate_status", steps, run_live_gate_status)
    validation = build_validation_summary("orchestrator_complete", [], timeout_records)
    copy_status = copy_shared_handoff() if copy_shared else {"shared_copy_status": "skipped_by_caller", "targets": []}
    active_public = int(promotion.get("active_symbols_public", 0))
    public_symbols = int(provider_ladder.get("symbol_success_count", 0))
    row_count = int(promotion.get("public_rows_active", provider_ladder.get("public_ohlcv_rows_loaded", 0)))
    active_symbols = market.get("symbols_loaded", provider_ladder.get("symbols_loaded", []))
    if public_symbols >= 5:
        rerun_status = "real_public_market_vision_paper_tournament_complete"
    elif public_symbols > 0:
        rerun_status = "partial_public_market_data_rerun_complete"
    else:
        rerun_status = "blocked_all_public_providers_fixture_fallback_only"
        quality_flags.append(_flag("blocked-all-public-providers", "warning", "all public providers failed; fixture fallback remains labeled"))
    next_target = "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3"
    if public_symbols >= len(PRIMARY_UNIVERSE):
        next_target = "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1"
    elif public_symbols >= 5:
        next_target = "DOPEY_PAPER_MONEY_TOURNAMENT_ITERATION_AND_MARKET_EXPANSION_V2"
    if int(evolution.get("public_data_paper_champion_count", 0)) > 0:
        next_target = "DOPEY_LIVE_GATE_CANDIDATE_REVIEW_AND_PAPER_CHAMPION_HARDENING_V1"
    summary = {
        "artifact_type": "real_public_market_wealth_rerun_summary",
        "real_public_market_wealth_rerun_version": "dopey-real-public-market-wealth-rerun-v2",
        "real_public_rerun_status": rerun_status,
        "provider_ladder_status": provider_ladder.get("provider_ladder_status", "missing"),
        "public_symbols_loaded": active_symbols,
        "public_rows_loaded": row_count,
        "active_public_symbol_count": active_public,
        "active_fixture_symbol_count": promotion.get("active_symbols_fixture", 0),
        "chart_count": chart.get("chart_count", 0),
        "signal_candidate_count": signals.get("signal_candidate_count", 0),
        "long_call_candidate_count": signals.get("long_call_candidate_count", 0),
        "long_put_candidate_count": signals.get("long_put_candidate_count", 0),
        "no_trade_count": signals.get("no_trade_count", 0),
        "option_trade_candidate_count": options.get("option_trade_candidate_count", 0),
        "paper_tournament_trade_count": tournament.get("paper_tournament_trade_count", 0),
        "paper_tournament_status": tournament.get("paper_tournament_status", "missing"),
        "pnl_scoreboard_status": scoreboard.get("pnl_scoreboard_status", "missing"),
        "top_paper_strategies": scoreboard.get("top_strategies_by_net_pnl", [])[:5],
        "promoted_paper_strategies": scoreboard.get("strategies_promoted", []),
        "killed_strategies": scoreboard.get("strategies_killed", []),
        "paper_champion_count": evolution.get("paper_champion_count", 0),
        "public_data_paper_champion_count": evolution.get("public_data_paper_champion_count", 0),
        "fixture_only_champion_count": evolution.get("fixture_only_champion_count", 0),
        "risk_throttle_count": risk.get("risk_throttle_count", 0),
        "live_gate_status": live_gate.get("live_gate_status", "missing"),
        "live_trading_enabled": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "real_orders_placed": False,
        "fixture_fallback_used": int(promotion.get("active_symbols_fixture", 0)) > 0,
        "fixture_fallback_symbol_count": promotion.get("active_symbols_fixture", 0),
        "provider_install_status": provider_install.get("active_python_status", "missing"),
        "provider_health_status": diagnostics.get("yahoo_direct_diagnosis", "missing"),
        "public_vs_fixture_scoreboard_split": split,
        "market_data_cache_status": cache.get("market_data_cache_status", "missing"),
        "validation_summary_path": str(VALIDATION_PATH),
        "shared_copy_status": copy_status,
        "next_recommended_target": next_target,
        "profitability_claim": False,
        "live_readiness_claim": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(STEPS_PATH, steps, False)
    write_jsonl(QUALITY_FLAGS_PATH, quality_flags, False)
    write_jsonl(TIMEOUT_RECORDS_PATH, timeout_records, False)
    write_jsonl(PROOF_PATH, [proof_record("real-public-market-wealth-rerun", rerun_status, summary)], False)
    write_json(VALIDATION_PATH, validation)
    if copy_shared:
        copy_shared_handoff()
    return {**summary, "artifact_paths": artifact_paths()}


def build_validation_summary(validation_status: str, command_results: list[dict], timeout_records: list[dict]) -> dict:
    summary = {
        "artifact_type": "real_public_market_wealth_validation_summary",
        "validation_status": validation_status,
        "command_results": command_results,
        "timeout_records": timeout_records,
        "timeout_recorded_as_pass": False,
        "validation_stabilizer_includes_shard": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(VALIDATION_PATH, summary)
    return summary


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
                "copied_file_count": len(record["files"]),
                "files": record["files"],
                "live_trading_enabled": False,
                "credentials_created": False,
                "env_created": False,
                "broker_connection_used": False,
                "real_orders_placed": False,
            }
            manifest["manifest_hash"] = stable_hash(manifest)
            write_json(bundle_root / "SESSION_COPY_MANIFEST.json", manifest)
            record["status"] = "copied"
        except OSError as exc:
            record["status"] = "copy_failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
        target_records.append(record)
    return {"shared_copy_status": "attempted", "targets": target_records, "copied_targets": sum(1 for record in target_records if record["status"] == "copied")}


def _handoff_source_paths() -> list[Path]:
    return [
        REPORTS_DIR / "DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2_REPORT.md",
        REPORTS_DIR / "DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2_ARTIFACT_LEDGER.md",
        REPORTS_DIR / "DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2_COMMANDS.md",
        ARTIFACT_ROOT / "provider_install" / "provider_install_repair_summary.json",
        ARTIFACT_ROOT / "market_intake" / "provider_health_diagnostics_summary.json",
        ARTIFACT_ROOT / "market_intake" / "public_ohlcv_provider_ladder_v2_summary.json",
        ARTIFACT_ROOT / "market_intake" / "public_ohlcv_fetch_successes_v2.jsonl",
        ARTIFACT_ROOT / "market_intake" / "public_ohlcv_fetch_failures_v2.jsonl",
        ARTIFACT_ROOT / "market_intake" / "market_data_cache_summary.json",
        ARTIFACT_ROOT / "market_intake" / "market_lake_public_promotion_summary.json",
        SUMMARY_PATH,
        ARTIFACT_ROOT / "market_intake" / "market_data_lake_summary.json",
        ARTIFACT_ROOT / "chart_vision" / "chart_vision_summary.json",
        ARTIFACT_ROOT / "signals" / "aggressive_signal_engine_summary.json",
        ARTIFACT_ROOT / "options_engine" / "model_priced_trade_constructor_summary.json",
        ARTIFACT_ROOT / "tournament" / "paper_money_tournament_summary.json",
        ARTIFACT_ROOT / "scoreboard" / "pnl_scoreboard_summary.json",
        ARTIFACT_ROOT / "scoreboard" / "public_vs_fixture_scoreboard_split.json",
        ARTIFACT_ROOT / "risk" / "risk_throttle_summary.json",
        ARTIFACT_ROOT / "evolution" / "evolution_loop_summary.json",
        ARTIFACT_ROOT / "live_gate" / "live_gate_status.json",
        ARTIFACT_ROOT / "market_provider_expansion" / "market_provider_expansion_validation_summary.json",
        ARTIFACT_ROOT / "scoreboard" / "performance_cockpit.html",
    ]


def _run_step(step_id: str, steps: list[dict], callback) -> dict:
    start = time.monotonic()
    try:
        result = callback()
        status = str(result.get("real_public_rerun_status") or result.get("provider_ladder_status") or result.get("active_lake_status") or result.get("market_data_status") or result.get("chart_vision_status") or result.get("signal_generation_status") or result.get("model_priced_options_status") or result.get("paper_tournament_status") or result.get("pnl_scoreboard_status") or result.get("scoreboard_split_status") or result.get("risk_throttle_status") or result.get("evolution_status") or result.get("live_gate_status") or "complete")
        steps.append({"artifact_type": "real_public_market_wealth_rerun_step", "step_id": step_id, "status": status, "duration_seconds": round(time.monotonic() - start, 6)})
        return result
    except Exception as exc:
        steps.append({"artifact_type": "real_public_market_wealth_rerun_step", "step_id": step_id, "status": "failed", "duration_seconds": round(time.monotonic() - start, 6), "error": f"{type(exc).__name__}: {exc}"})
        raise


def _flag(flag_id: str, severity: str, message: str) -> dict:
    record = {"artifact_type": "real_public_market_wealth_rerun_quality_flag", "flag_id": flag_id, "severity": severity, "message": message}
    record["flag_hash"] = stable_hash(record)
    return record


def artifact_paths() -> dict[str, str]:
    return {
        "real_public_market_wealth_rerun_summary": str(SUMMARY_PATH),
        "real_public_market_wealth_rerun_steps": str(STEPS_PATH),
        "real_public_market_wealth_rerun_quality_flags": str(QUALITY_FLAGS_PATH),
        "real_public_market_wealth_rerun_proof": str(PROOF_PATH),
        "real_public_market_wealth_validation_summary": str(VALIDATION_PATH),
        "real_public_market_wealth_timeout_records": str(TIMEOUT_RECORDS_PATH),
    }


def main() -> int:
    summary = run_real_public_market_wealth_engine_rerun(True, False)
    print(json.dumps({
        "real_public_rerun_status": summary["real_public_rerun_status"],
        "provider_ladder_status": summary["provider_ladder_status"],
        "public_rows_loaded": summary["public_rows_loaded"],
        "active_public_symbol_count": summary["active_public_symbol_count"],
        "paper_tournament_status": summary["paper_tournament_status"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "summary_path": summary["artifact_paths"]["real_public_market_wealth_rerun_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
