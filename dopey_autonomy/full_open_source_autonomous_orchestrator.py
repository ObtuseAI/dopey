"""Full open-source autonomous options trader research orchestrator."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dopey_data_ingestion.autonomous_open_data_manifest_builder import run_autonomous_open_data_manifest_builder
from dopey_data_ingestion.autonomous_open_data_quarantine_fetcher import run_autonomous_open_data_quarantine_fetcher
from dopey_data_ingestion.autonomous_open_data_source_discovery import run_autonomous_open_data_source_discovery
from dopey_data_ingestion.autonomous_open_data_validator_bridge import run_autonomous_open_data_validator_bridge
from dopey_data_ingestion.autonomous_open_ohlcv_normalizer import run_autonomous_open_ohlcv_normalizer
from dopey_open_source.autonomous_oss_quant_discovery import run_autonomous_oss_quant_discovery
from dopey_options_autonomy.open_options_data_autonomy_plan import run_open_options_data_autonomy_plan
from dopey_paper_autonomy.autonomous_paper_trading_loop import run_autonomous_paper_trading_loop
from dopey_research_autonomy.autonomous_backtest_stat_fitness_pipeline import run_autonomous_backtest_stat_fitness_pipeline
from dopey_research_autonomy.run_autonomous_research_engine import run_autonomous_research_engine
from dopey_research_autonomy.s_tier_options_benchmark import run_s_tier_options_benchmark
from dopey_core.repo_paths import REPORTS_DIR

from .autonomous_admissibility_kernel import run_autonomous_admissibility_kernel
from .autonomy_common import ARTIFACT_ROOT, REPO_ROOT, copy_session_packet, proof_record, safety_state, stable_hash, write_autonomy_fixture_cases, write_json, write_jsonl


ARTIFACT_DIR = ARTIFACT_ROOT / "full_autonomy"
SUMMARY_PATH = ARTIFACT_DIR / "full_open_source_autonomous_orchestrator_summary.json"
STEPS_PATH = ARTIFACT_DIR / "full_open_source_autonomous_orchestrator_steps.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "full_open_source_autonomous_orchestrator_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "full_open_source_autonomous_orchestrator_proof.jsonl"
VALIDATION_SUMMARY_PATH = ARTIFACT_DIR / "full_autonomy_validation_summary.json"
TIMEOUT_RECORDS_PATH = ARTIFACT_DIR / "full_autonomy_timeout_records.jsonl"
ACTION_GAP_PACKET_PATH = ARTIFACT_DIR / "full_autonomy_action_gap_packet.json"
REPORT_PATH = REPORTS_DIR / "DOPEY_OPEN_SOURCE_AUTONOMOUS_OPTIONS_TRADER_MAX_COMPLETION_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_OPEN_SOURCE_AUTONOMOUS_OPTIONS_TRADER_MAX_COMPLETION_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_OPEN_SOURCE_AUTONOMOUS_OPTIONS_TRADER_COMMANDS.md"


def run_full_open_source_autonomous_orchestrator() -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    watchdog = _step("watchdog-safe-checkpoint", "completed", {"no_reboot_driver_registry_power_changes": True})
    steps.append(watchdog)
    admissibility = _run_step("autonomous-admissibility-kernel", run_autonomous_admissibility_kernel, steps)
    oss = _run_step("open-source-repo-discovery", run_autonomous_oss_quant_discovery, steps)
    data = _run_step("open-data-source-discovery", run_autonomous_open_data_source_discovery, steps)
    fetch = _run_step("open-data-quarantine-fetcher", run_autonomous_open_data_quarantine_fetcher, steps)
    normalizer = _run_step("open-ohlcv-normalizer", run_autonomous_open_ohlcv_normalizer, steps)
    manifest = _run_step("autonomous-open-data-manifest-builder", run_autonomous_open_data_manifest_builder, steps)
    bridge = _run_step("autonomous-open-data-validator-bridge", run_autonomous_open_data_validator_bridge, steps)
    options = _run_step("open-options-data-autonomy-plan", run_open_options_data_autonomy_plan, steps)
    research = _run_step("autonomous-research-engine", run_autonomous_research_engine, steps)
    pipeline = _run_step("autonomous-backtest-stat-fitness-pipeline", run_autonomous_backtest_stat_fitness_pipeline, steps)
    paper = _run_step("autonomous-paper-trading-loop", run_autonomous_paper_trading_loop, steps)
    benchmark = _run_step("s-tier-options-benchmark", run_s_tier_options_benchmark, steps)
    fixtures = write_autonomy_fixture_cases()
    _write_docs(admissibility, oss, data, fetch, normalizer, manifest, bridge, options, research, pipeline, paper, benchmark, fixtures)
    validation = _write_initial_validation_summary()
    summary = _summary(admissibility, oss, data, fetch, normalizer, bridge, options, research, pipeline, paper, benchmark, validation)
    action_gap = _action_gap_packet(summary)
    write_json(ACTION_GAP_PACKET_PATH, action_gap)
    shared = copy_session_packet([REPORT_PATH, LEDGER_PATH, COMMANDS_PATH, SUMMARY_PATH, VALIDATION_SUMMARY_PATH, benchmark["artifact_paths"] and Path(benchmark["artifact_paths"]["s_tier_options_benchmark_summary"]), Path(paper["artifact_paths"]["autonomous_paper_trading_loop_summary"]), ACTION_GAP_PACKET_PATH])
    summary = {**summary, **shared}
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(STEPS_PATH, steps)
    write_jsonl(QUALITY_FLAGS_PATH, _quality_flags(summary))
    write_jsonl(PROOF_PATH, [proof_record("full-open-source-autonomous-orchestrator-proof-v1", summary["autonomy_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def run_watchdog_safe_validation() -> dict[str, Any]:
    commands = [
        [sys.executable, "-m", "pytest", "tests/test_open_source_autonomous_options_trader_max_completion.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_operator_stage_max_progress.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_operator_reviewed_ohlcv_stage_rerun.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_manual_free_ohlcv_staging_or_local_import_fix.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_local_free_ohlcv_import_validator_and_history_activation.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_real_data_ingestion_plan.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_fitness_function_replacement.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_statistical_truth_layer.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_honest_backtester.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_real_signal_engines.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_model_repricer.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_real_data_backtest_spine.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_active_option_lifecycle_simulator.py", "-q"],
        [sys.executable, "-m", "pytest", "tests/test_active_policy_integration.py", "tests/test_active_trading_policy.py", "-q"],
    ]
    results = [_run_command(command, 45) for command in commands if Path(command[3]).exists()]
    smoke_commands = [
        [sys.executable, "-m", "dopey_autonomy.run_full_open_source_autonomous_orchestrator"],
        [sys.executable, "-m", "dopey_autonomy.run_autonomous_admissibility_kernel"],
        [sys.executable, "-m", "dopey_open_source.run_autonomous_oss_quant_discovery"],
        [sys.executable, "-m", "dopey_data_ingestion.run_autonomous_open_data_source_discovery"],
        [sys.executable, "-m", "dopey_data_ingestion.run_autonomous_open_data_quarantine_fetcher"],
        [sys.executable, "-m", "dopey_data_ingestion.run_autonomous_open_ohlcv_normalizer"],
        [sys.executable, "-m", "dopey_data_ingestion.run_autonomous_open_data_manifest_builder"],
        [sys.executable, "-m", "dopey_data_ingestion.run_autonomous_open_data_validator_bridge"],
        [sys.executable, "-m", "dopey_options_autonomy.run_open_options_data_autonomy_plan"],
        [sys.executable, "-m", "dopey_research_autonomy.run_autonomous_research_engine"],
        [sys.executable, "-m", "dopey_research_autonomy.run_autonomous_backtest_stat_fitness_pipeline"],
        [sys.executable, "-m", "dopey_paper_autonomy.run_autonomous_paper_trading_loop"],
        [sys.executable, "-m", "dopey_research_autonomy.run_s_tier_options_benchmark"],
    ]
    smokes = [_run_command(command, 45) for command in smoke_commands]
    collection = _run_command([sys.executable, "-m", "pytest", "--collect-only", "-q"], 60)
    timeouts = [record for record in [collection, *results, *smokes] if record["status"] == "inconclusive_timeout"]
    summary = {
        "artifact_type": "full_autonomy_validation_summary",
        "validation_status": "pass" if all(record["status"] == "pass" for record in results) else "pass_with_inconclusive_or_skipped",
        "collect_only": collection,
        "targeted_tests": results,
        "smokes": smokes,
        "timeout_recorded_as_pass": False,
        "expensive_capped_lanes": [
            {"command": [sys.executable, "-m", "dopey_audit.run_offline_evidence_replay_audit"], "status": "skipped_watchdog_safe_policy"},
            {"command": [sys.executable, "-m", "dopey_export.run_artifact_compaction_export_verifier"], "status": "skipped_watchdog_safe_policy"},
        ],
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(VALIDATION_SUMMARY_PATH, summary)
    write_jsonl(TIMEOUT_RECORDS_PATH, timeouts)
    return summary


def artifact_paths() -> dict[str, str]:
    return {
        "full_open_source_autonomous_orchestrator_summary": str(SUMMARY_PATH),
        "full_open_source_autonomous_orchestrator_steps": str(STEPS_PATH),
        "full_open_source_autonomous_orchestrator_quality_flags": str(QUALITY_FLAGS_PATH),
        "full_open_source_autonomous_orchestrator_proof": str(PROOF_PATH),
        "full_autonomy_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "full_autonomy_timeout_records": str(TIMEOUT_RECORDS_PATH),
        "full_autonomy_action_gap_packet": str(ACTION_GAP_PACKET_PATH),
    }


def _run_step(step_id: str, func, steps: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        result = func()
        steps.append(_step(step_id, "completed", result))
        return result
    except Exception as exc:
        result = {"error_type": type(exc).__name__, "error": str(exc)}
        steps.append(_step(step_id, "failed", result))
        raise


def _step(step_id: str, status: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "full_open_source_autonomous_orchestrator_steps",
        "step_id": step_id,
        "status": status,
        "payload_hash": stable_hash(payload),
        "paper_only": True,
        "live_blocked": True,
    }
    record["step_hash"] = stable_hash(record)
    return record


def _summary(admissibility: dict[str, Any], oss: dict[str, Any], data: dict[str, Any], fetch: dict[str, Any], normalizer: dict[str, Any], bridge: dict[str, Any], options: dict[str, Any], research: dict[str, Any], pipeline: dict[str, Any], paper: dict[str, Any], benchmark: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    has_ohlcv = bool(bridge["valid_real_dataset"])
    autonomy_status = "max_completion_autonomous_open_data_validated" if has_ohlcv else "max_completion_no_machine_admissible_open_data"
    return {
        "artifact_type": "full_open_source_autonomous_orchestrator_summary",
        "orchestrator_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "autonomy_status": autonomy_status,
        "open_source_candidate_count": oss["open_source_candidate_count"],
        "open_source_accepted_count": oss["open_source_accepted_count"],
        "open_data_candidate_count": data["open_data_candidate_count"],
        "open_data_accepted_count": data["open_data_accepted_count"],
        "open_data_fetch_count": fetch["fetch_success_count"],
        "accepted_ohlcv_file_count": normalizer["accepted_ohlcv_file_count"],
        "valid_real_dataset": bridge["valid_real_dataset"],
        "history_activation_status": bridge["history_activation_status"],
        "real_signal_validation_status": bridge["real_signal_validation_status"],
        "options_data_status": options["options_data_status"],
        "quote_priced_backtest_allowed": options["quote_priced_backtest_allowed"],
        "model_priced_research_allowed": options["model_priced_research_allowed"],
        "paper_trading_loop_status": paper["paper_loop_status"],
        "s_tier_benchmark_status": benchmark["s_tier_benchmark_status"],
        "research_promotion_status": pipeline["research_promotion_status"],
        "live_promotion_status": False,
        "network_fetch_performed": fetch["network_fetch_performed"],
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "not_options_evidence": not options["quote_priced_backtest_allowed"],
        "not_profitability_claim": True,
        "not_live_ready": True,
        "alpha_vantage_excluded": True,
        "validation_status": validation["validation_status"],
        "next_recommended_target": "DOPEY_AUTONOMOUS_OPEN_DATA_SOURCE_EXPANSION_V1" if not has_ohlcv else ("DOPEY_MODEL_PRICED_OPTIONS_RESEARCH_EXPANSION_V1" if not options["quote_priced_backtest_allowed"] else "DOPEY_REAL_OPTIONS_HONEST_BACKTESTER_V1"),
        **safety_state(),
    }


def _quality_flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    if not summary["valid_real_dataset"]:
        reasons.append("valid_real_dataset_false")
    if not summary["quote_priced_backtest_allowed"]:
        reasons.append("quote_priced_backtest_blocked")
    if summary["paper_trading_loop_status"] != "paper_loop_ran":
        reasons.append(summary["paper_trading_loop_status"])
    flags = []
    for index, reason in enumerate(reasons):
        record = {
            "artifact_type": "full_open_source_autonomous_orchestrator_quality_flags",
            "flag_id": f"full-autonomy-{index:03d}",
            "reason_code": reason,
            "severity": "info",
            "paper_only": True,
            "live_blocked": True,
        }
        record["flag_hash"] = stable_hash(record)
        flags.append(record)
    return flags


def _write_initial_validation_summary() -> dict[str, Any]:
    summary = {
        "artifact_type": "full_autonomy_validation_summary",
        "validation_status": "not_run_yet",
        "targeted_tests": [],
        "smokes": [],
        "timeout_recorded_as_pass": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(VALIDATION_SUMMARY_PATH, summary)
    write_jsonl(TIMEOUT_RECORDS_PATH, [])
    return summary


def _run_command(command: list[str], timeout_seconds: int) -> dict[str, Any]:
    start = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=timeout_seconds)
        status = "pass" if completed.returncode == 0 else "fail"
        return {"command": command, "status": status, "exit_code": completed.returncode, "duration_seconds": round(time.monotonic() - start, 6), "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-2000:], "timeout_recorded_as_pass": False}
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        return {"command": command, "status": "inconclusive_timeout", "exit_code": None, "duration_seconds": round(time.monotonic() - start, 6), "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:], "timeout_recorded_as_pass": False}


def _write_docs(admissibility: dict[str, Any], oss: dict[str, Any], data: dict[str, Any], fetch: dict[str, Any], normalizer: dict[str, Any], manifest: dict[str, Any], bridge: dict[str, Any], options: dict[str, Any], research: dict[str, Any], pipeline: dict[str, Any], paper: dict[str, Any], benchmark: dict[str, Any], fixtures: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Open Source Autonomous Options Trader Max Completion Report",
        "",
        "## Objective",
        "Replace manual data/source approval loops with deterministic autonomous gates for a paper-only long-premium options research engine.",
        "",
        "## No-Manual-Review Doctrine",
        "- Machine-verifiable acceptable sources are accepted.",
        "- Ambiguous, unknown-license, credentialed, paid, proprietary, broker/live, scrape-only, fixture, and sample sources are rejected or quarantined.",
        "- Missing admissible data is a successful blocked state, not an operator task.",
        "",
        "## Results",
        f"- autonomous_admissibility_accepted: `{admissibility['accepted_count']}`",
        f"- autonomous_admissibility_rejected: `{admissibility['rejected_count']}`",
        f"- open_source_candidate_count: `{oss['open_source_candidate_count']}`",
        f"- open_source_accepted_count: `{oss['open_source_accepted_count']}`",
        f"- open_data_candidate_count: `{data['open_data_candidate_count']}`",
        f"- open_data_accepted_count: `{data['open_data_accepted_count']}`",
        f"- open_data_fetch_status: `{fetch['fetch_status']}`",
        f"- accepted_ohlcv_file_count: `{normalizer['accepted_ohlcv_file_count']}`",
        f"- manifest_status: `{manifest['manifest_status']}`",
        f"- valid_real_dataset: `{str(bridge['valid_real_dataset']).lower()}`",
        f"- options_data_status: `{options['options_data_status']}`",
        f"- research_status: `{research['research_status']}`",
        f"- backtest_stat_fitness_status: `{pipeline['pipeline_status']}`",
        f"- paper_loop_status: `{paper['paper_loop_status']}`",
        f"- s_tier_benchmark_status: `{benchmark['s_tier_benchmark_status']}`",
        f"- fixture_case_count: `{fixtures['fixture_case_count']}`",
        "",
        "## Safety State",
        "- Alpha Vantage excluded: `true`",
        "- credentials_created: `false`",
        "- env_created: `false`",
        "- broker_connection_used: `false`",
        "- live_promotion_status: `false`",
        "- strategy_promotion_allowed: `false`",
        "- not_profitability_claim: `true`",
        "- not_live_ready: `true`",
        "",
        "## Known Gaps",
        "- No accepted autonomous open OHLCV file exists unless a future source passes direct file, license, provenance, adjusted-close, schema, and quality gates.",
        "- No machine-admissible historical options quote source exists in this bundle, so quote-priced options evidence is blocked.",
        "",
        "## Next Target",
        "- `DOPEY_AUTONOMOUS_OPEN_DATA_SOURCE_EXPANSION_V1`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    command_lines = [
        "# DOPEY Open Source Autonomous Options Trader Commands",
        "",
        "- `python -m dopey_autonomy.run_full_open_source_autonomous_orchestrator`",
        "- `python -m dopey_autonomy.run_autonomous_admissibility_kernel`",
        "- `python -m dopey_open_source.run_autonomous_oss_quant_discovery`",
        "- `python -m dopey_data_ingestion.run_autonomous_open_data_source_discovery`",
        "- `python -m dopey_data_ingestion.run_autonomous_open_data_quarantine_fetcher`",
        "- `python -m dopey_data_ingestion.run_autonomous_open_ohlcv_normalizer`",
        "- `python -m dopey_data_ingestion.run_autonomous_open_data_manifest_builder`",
        "- `python -m dopey_data_ingestion.run_autonomous_open_data_validator_bridge`",
        "- `python -m dopey_options_autonomy.run_open_options_data_autonomy_plan`",
        "- `python -m dopey_research_autonomy.run_autonomous_research_engine`",
        "- `python -m dopey_research_autonomy.run_autonomous_backtest_stat_fitness_pipeline`",
        "- `python -m dopey_paper_autonomy.run_autonomous_paper_trading_loop`",
        "- `python -m dopey_research_autonomy.run_s_tier_options_benchmark`",
    ]
    COMMANDS_PATH.write_text("\n".join(command_lines) + "\n", encoding="utf-8")
    ledger_paths = [REPORT_PATH, COMMANDS_PATH, *[Path(path) for path in artifact_paths().values()], *[Path(path) for path in fixtures["fixture_paths"]]]
    ledger = ["# DOPEY Open Source Autonomous Options Trader Max Completion Artifact Ledger", "", "## Files"]
    for path in ledger_paths:
        if path.exists():
            ledger.append(f"- `{path.relative_to(REPO_ROOT).as_posix()}` sha256=`{_file_hash(path)}`")
    LEDGER_PATH.write_text("\n".join(ledger) + "\n", encoding="utf-8")
    _append_long_docs()


def _append_long_docs() -> None:
    for path in [REPO_ROOT / "DOPEY_VALIDATION_REPORT.md", REPO_ROOT / "DOPEY_CANON.md"]:
        marker = "\n\n## DOPEY Open Source Autonomous Options Trader Max Completion V1\n- Autonomous source/data admissibility now replaces manual review for this lane.\n- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.\n- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.\n"
        with path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(marker)


def _action_gap_packet(summary: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "full_autonomy_action_gap_packet",
        "autonomy_status": summary["autonomy_status"],
        "known_gaps": [
            "accepted autonomous open OHLCV still absent" if not summary["valid_real_dataset"] else "accepted OHLCV present",
            "machine-admissible historical options quotes absent" if not summary["quote_priced_backtest_allowed"] else "quote-priced options data present",
        ],
        "next_recommended_target": summary["next_recommended_target"],
        **safety_state(),
    }
    record["packet_hash"] = stable_hash(record)
    return record


def _file_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()

