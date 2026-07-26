"""Resilient research supervisor: the full real-data chain with no dead ends.

Runs every stage of the honest lane in dependency order. A stage failure is
absorbed, not fatal: the exception becomes a structured incident artifact and
a repair-queue entry, true dependents are marked skipped_dependency, and every
independent stage still runs. The loop never silently stops and never converts
a failure into a pass - "no dead ends" means every failure becomes a logged,
actionable work item, NOT that failures are hidden.

Paper-only, live-blocked. The supervisor can never promote a strategy; it only
produces artifacts for the truth-gated layers to judge.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dopey_research_pipeline.artifact_io import append_jsonl, write_json_atomic
from dopey_core.repo_paths import REPORTS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
SUPERVISOR_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "research_supervisor"
SUPERVISOR_SUMMARY_PATH = SUPERVISOR_ARTIFACT_DIR / "resilient_research_supervisor_summary.json"
SUPERVISOR_INCIDENTS_PATH = SUPERVISOR_ARTIFACT_DIR / "resilient_research_supervisor_incidents.jsonl"
SUPERVISOR_REPAIR_QUEUE_PATH = SUPERVISOR_ARTIFACT_DIR / "resilient_research_supervisor_repair_queue.jsonl"
SUPERVISOR_RUN_JOURNAL_PATH = SUPERVISOR_ARTIFACT_DIR / "supervisor_run_journal.jsonl"
SUPERVISOR_ACTIVE_RUN_PATH = SUPERVISOR_ARTIFACT_DIR / "supervisor_active_run.json"
SUPERVISOR_LOCK_RECOVERY_PATH = SUPERVISOR_ARTIFACT_DIR / "supervisor_lock_recovery.jsonl"
SUPERVISOR_REPORT_PATH = REPORTS_DIR / "DOPEY_RESILIENT_RESEARCH_SUPERVISOR_REPORT.md"
SUPERVISOR_LOCK_PATH = REPO_ROOT / "artifacts" / ".supervisor.lock"
CORRUPT_LOCK_STALE_SECONDS = 15 * 60
STAGE_SOFT_BUDGET_SECONDS = 3600.0
STAGE_HARD_TIMEOUT_SECONDS = 4 * 3600
SUPERVISOR_HARD_TIMEOUT_SECONDS = 10 * 3600
MIN_SUPERVISOR_FREE_BYTES = 20 * 1024**3

# These values mean the stage ran but could not produce its normal evidence.
# They are stage-health classifications, not market verdicts: honest negative
# verdicts such as ``not_action_ready`` and ``error_budget_breached`` remain
# completed because the stage evaluated its inputs successfully.
DEGRADED_EXACT_STATUSES = frozenset(
    {
        "degraded",
        "error",
        "exception",
        "failed",
        "failure",
        "future_timestamp",
        "inconclusive_epistemic_claims_present",
        "inconclusive_timeout",
        "invalid_real_dataset",
        "local_ohlcv_validation_fail",
        "no_spine_rows_available",
        "partial",
        "runtime_probe_contract_failed",
        "runtime_probe_launch_failed",
        "runtime_probe_process_failed",
        "runtime_probe_protocol_invalid",
        "runtime_probe_timeout",
        "runtime_unverified_missing_python",
        "stale",
        "timed_out",
    }
)
DEGRADED_STATUS_PREFIXES = ("blocked_", "insufficient_", "missing_")
DEGRADED_STATUS_SUFFIXES = ("_failed", "_failure", "_missing")


def _stage_history_validation() -> dict[str, Any]:
    from dopey_data.run_history_dataset_validation import run_history_dataset_validation

    return run_history_dataset_validation()


def _stage_real_signals() -> dict[str, Any]:
    from dopey_analysis.real_history_signal_engine import run_real_history_signal_engine

    return run_real_history_signal_engine()


def _stage_real_backtest() -> dict[str, Any]:
    from dopey_backtest.real_history_honest_backtester import run_real_history_honest_backtester

    return run_real_history_honest_backtester()


def _stage_market_structure() -> dict[str, Any]:
    from dopey_analysis.market_structure_engine import run_market_structure_engine

    return run_market_structure_engine()


def _stage_baseline_arbitration() -> dict[str, Any]:
    from dopey_backtest.baseline_arbitration import run_baseline_arbitration

    return run_baseline_arbitration()


def _stage_era_walk_forward() -> dict[str, Any]:
    from dopey_backtest.era_walk_forward import run_era_walk_forward

    return run_era_walk_forward()


def _stage_statistical_truth() -> dict[str, Any]:
    from dopey_stats.run_statistical_truth_layer import run_statistical_truth_layer

    return run_statistical_truth_layer()


def _stage_truth_gated_fitness() -> dict[str, Any]:
    from dopey_fitness.run_fitness_function_replacement import run_fitness_function_replacement

    return run_fitness_function_replacement()


def _stage_chain_analytics_gate() -> dict[str, Any]:
    from dopey_options.chain_analytics import run_chain_analytics_gate

    return run_chain_analytics_gate()


def _stage_chart_vision() -> dict[str, Any]:
    from dopey_chart_vision.real_structure_chart_renderer import run_real_structure_chart_renderer

    return run_real_structure_chart_renderer()


def _stage_model_iv_calibration() -> dict[str, Any]:
    from dopey_options.model_iv_calibration import run_model_iv_calibration

    return run_model_iv_calibration()


def _stage_forward_paper_walk() -> dict[str, Any]:
    from dopey_backtest.forward_paper_walk import run_forward_paper_walk

    return run_forward_paper_walk()


def _stage_straddle_vrp_probe() -> dict[str, Any]:
    from dopey_backtest.straddle_vrp_probe import run_straddle_vrp_probe

    return run_straddle_vrp_probe()


def _stage_pipeline_forecast_card() -> dict[str, Any]:
    from dopey_ops.pipeline_forecast_card import run_pipeline_forecast_card

    return run_pipeline_forecast_card()


def _stage_kaizen_ledger() -> dict[str, Any]:
    from dopey_ops.kaizen_ledger import run_kaizen_ledger

    return run_kaizen_ledger()


def _stage_reliability_slo() -> dict[str, Any]:
    from dopey_ops.reliability_slo import run_reliability_slo

    return run_reliability_slo()


def _stage_vol_surface_metrics() -> dict[str, Any]:
    from dopey_options.vol_surface_metrics import run_vol_surface_metrics

    return run_vol_surface_metrics()


def _stage_market_context_fusion() -> dict[str, Any]:
    from dopey_analysis.market_context_fusion import run_market_context_fusion

    return run_market_context_fusion()


def _stage_adversarial_stress() -> dict[str, Any]:
    from dopey_risk_engine.adversarial_stress_engine import run_adversarial_stress_engine

    return run_adversarial_stress_engine()


def _stage_exit_policy_search() -> dict[str, Any]:
    from dopey_evolution.exit_policy_walkforward_search import run_exit_policy_walkforward_search

    return run_exit_policy_walkforward_search()


def _stage_action_readiness_gate() -> dict[str, Any]:
    from dopey_broker_readiness.action_readiness_gate import run_action_readiness_gate
    from dopey.runtime.run_trade_readiness_frontier import run_trade_readiness_frontier

    action_readiness = run_action_readiness_gate()
    trade_readiness_frontier = run_trade_readiness_frontier(
        REPO_ROOT,
        REPO_ROOT / "artifacts" / "dopey" / "readiness" / "trade_readiness_frontier.json",
        REPORTS_DIR / "DOPEY_TRADE_READINESS_FRONTIER_REPORT.md",
    )
    return {
        **action_readiness,
        "trade_readiness_frontier": trade_readiness_frontier,
    }


def _stage_indicator_foundry() -> dict[str, Any]:
    from dopey_analysis.indicator_foundry import run_indicator_foundry

    return run_indicator_foundry()


def _stage_agentic_account_reconciliation() -> dict[str, Any]:
    from dopey_broker_readiness.agentic_account_reconciliation import run_agentic_account_reconciliation

    return run_agentic_account_reconciliation()


def _stage_data_freshness_sentinel() -> dict[str, Any]:
    from dopey_data_ingestion.data_freshness_sentinel import run_data_freshness_sentinel

    return run_data_freshness_sentinel()


def _stage_envelope_integrity_sentinel() -> dict[str, Any]:
    from dopey_audit.envelope_integrity_sentinel import run_envelope_integrity_sentinel

    return run_envelope_integrity_sentinel()


def _stage_forward_book_risk() -> dict[str, Any]:
    from dopey_risk_engine.forward_book_risk import run_forward_book_risk

    return run_forward_book_risk()


def _stage_forward_book_quality() -> dict[str, Any]:
    from dopey_analysis.forward_book_quality import run_forward_book_quality_audit

    return run_forward_book_quality_audit()


def _stage_macro_context_gate() -> dict[str, Any]:
    from dopey_market_intake.macro_context_gate import run_macro_context_gate

    return run_macro_context_gate()


def _stage_distributional_stress() -> dict[str, Any]:
    from dopey_risk_engine.market_simulation_engine import run_market_simulation_engine

    return run_market_simulation_engine()


def _stage_exit_playbook() -> dict[str, Any]:
    from dopey_risk_engine.exit_playbook import run_exit_playbook

    return run_exit_playbook()


def _stage_adversarial_signal_panel() -> dict[str, Any]:
    from dopey_risk_engine.adversarial_signal_panel import run_adversarial_signal_panel

    return run_adversarial_signal_panel()


def _stage_trade_loss_coach() -> dict[str, Any]:
    from dopey_analysis.trade_loss_coach import run_trade_loss_coach

    return run_trade_loss_coach()


def _stage_target_screener() -> dict[str, Any]:
    from dopey_screener.run_target_screener import run_target_screener

    return run_target_screener()


def _stage_universe_governor() -> dict[str, Any]:
    from dopey_universe.run_universe_governor import run_universe_governor

    return run_universe_governor()


def _stage_signal_calibration() -> dict[str, Any]:
    from dopey_calibration.signal_settlement import run_signal_calibration

    return run_signal_calibration()


def _stage_playbook_research() -> dict[str, Any]:
    from dopey.strategy_engineering.run_playbook_research_stage import run_playbook_research_stage

    return run_playbook_research_stage()


def _stage_symbol_targeting() -> dict[str, Any]:
    from dopey_targeting.models import default_targeting_policy
    from dopey_targeting.runtime import default_paths, run_symbol_targeting

    return run_symbol_targeting(
        default_paths(),
        default_targeting_policy(),
        datetime.now(timezone.utc),
    )


def _stage_squeeze_bubble_intelligence() -> dict[str, Any]:
    from dopey_squeeze_bubble.intake import default_paths
    from dopey_squeeze_bubble.models import default_policy
    from dopey_squeeze_bubble.runtime import (
        ARTIFACT_ROOT,
        run_squeeze_bubble_intelligence,
    )

    return run_squeeze_bubble_intelligence(
        default_paths(REPO_ROOT),
        default_policy(),
        datetime.now(timezone.utc),
        ARTIFACT_ROOT,
    )


def _stage_epistemic_supervision() -> dict[str, Any]:
    from dopey_squeeze_bubble.runtime import (
        ASSESSMENTS_PATH,
        RANKINGS_PATH,
        SUMMARY_PATH as SQUEEZE_SUMMARY_PATH,
    )
    from dopey_targeting.runtime import (
        CANDIDATE_REGISTRY_PATH,
        FORECAST_SKILL_PATH,
        SUMMARY_PATH as TARGETING_SUMMARY_PATH,
    )
    from dopey_validation.epistemic_adversary import default_epistemic_policy
    from dopey_validation.epistemic_runtime import (
        EpistemicRuntimePaths,
        run_epistemic_supervision,
    )

    repository_root = ASSESSMENTS_PATH.resolve().parents[3]
    paths = EpistemicRuntimePaths(
        repository_root=repository_root,
        squeeze_assessments_path=ASSESSMENTS_PATH,
        squeeze_rankings_path=RANKINGS_PATH,
        squeeze_summary_path=SQUEEZE_SUMMARY_PATH,
        targeting_registry_path=CANDIDATE_REGISTRY_PATH,
        targeting_forecast_path=FORECAST_SKILL_PATH,
        targeting_summary_path=TARGETING_SUMMARY_PATH,
        output_path=(
            repository_root
            / "artifacts"
            / "dopey"
            / "epistemic_supervision"
            / "epistemic_supervision_summary.json"
        ),
    )
    return run_epistemic_supervision(
        paths,
        default_epistemic_policy(),
        datetime.now(timezone.utc),
    )


# (name, callable, hard dependencies that must have run non-failed)
# Dependency edges mirror actual artifact data flow (producer before consumer),
# so a failed producer skips its consumers instead of letting them run on stale
# prior-run artifacts.
STAGES: tuple[tuple[str, Callable[[], dict[str, Any]], tuple[str, ...]], ...] = (
    ("data_freshness_sentinel", _stage_data_freshness_sentinel, ()),
    ("envelope_integrity_sentinel", _stage_envelope_integrity_sentinel, ()),
    ("macro_context_gate", _stage_macro_context_gate, ()),
    ("history_validation", _stage_history_validation, ()),
    ("real_signals", _stage_real_signals, ("history_validation",)),
    ("market_structure", _stage_market_structure, ("history_validation",)),
    ("model_iv_calibration", _stage_model_iv_calibration, ("history_validation",)),
    ("real_backtest", _stage_real_backtest, ("real_signals", "model_iv_calibration")),
    ("baseline_arbitration", _stage_baseline_arbitration, ("real_backtest",)),
    ("era_walk_forward", _stage_era_walk_forward, ("real_backtest",)),
    ("statistical_truth", _stage_statistical_truth, ("real_backtest",)),
    ("truth_gated_fitness", _stage_truth_gated_fitness, ("statistical_truth",)),
    ("chain_analytics_gate", _stage_chain_analytics_gate, ()),
    ("vol_surface_metrics", _stage_vol_surface_metrics, ()),
    ("market_context_fusion", _stage_market_context_fusion, ("market_structure", "chain_analytics_gate", "vol_surface_metrics")),
    ("forward_paper_walk", _stage_forward_paper_walk, ("real_signals", "market_context_fusion")),
    # Baseline VRP probe: direction-neutral long straddles, SEPARATE ledger,
    # gate-isolated (never counts toward the 100-close promotion gate). Depends
    # only on a validated chain snapshot; independent of the directional walk.
    ("straddle_vrp_probe", _stage_straddle_vrp_probe, ("chain_analytics_gate",)),
    # Ops-excellence lanes (measure-only, never gate inputs): Feynman forecast
    # card scores + re-predicts right after the walk marks; kaizen aggregates
    # defects once stress has refreshed; the SLO reads pure artifact freshness.
    ("pipeline_forecast_card", _stage_pipeline_forecast_card, ("forward_paper_walk",)),
    ("reliability_slo", _stage_reliability_slo, ()),
    ("forward_book_quality", _stage_forward_book_quality, ("forward_paper_walk",)),
    ("forward_book_risk", _stage_forward_book_risk, ("forward_paper_walk",)),
    ("adversarial_stress", _stage_adversarial_stress, ("forward_paper_walk",)),
    ("kaizen_ledger", _stage_kaizen_ledger, ("adversarial_stress",)),
    ("distributional_stress", _stage_distributional_stress, ("forward_paper_walk",)),
    ("exit_playbook", _stage_exit_playbook, ("forward_paper_walk",)),
    # signal_calibration runs BEFORE the panel: the panel reads its contested-truth
    # base rate as an advisory lens, so it must be fresh in the same pass. It is a
    # soft input (the panel degrades to 'unrated' if absent), so it is NOT a hard
    # dependency here - a calibration failure must never skip the panel.
    ("signal_calibration", _stage_signal_calibration, ("real_signals", "history_validation")),
    # playbook_research: autonomous canon scan + detection settlement + earned
    # per-family trust. Advisory research telemetry; depends only on a valid
    # spine. Lane context (macro/GEX) is soft input — absences are typed gaps.
    ("playbook_research", _stage_playbook_research, ("history_validation",)),
    # Gate-blind per-symbol skill and phantom targeting. Fresh playbook
    # settlements and IV calibration are hard inputs; no gate or live-book
    # artifact is read by this stage.
    (
        "symbol_targeting",
        _stage_symbol_targeting,
        ("playbook_research", "model_iv_calibration"),
    ),
    (
        "squeeze_bubble_intelligence",
        _stage_squeeze_bubble_intelligence,
        ("history_validation", "macro_context_gate", "chain_analytics_gate"),
    ),
    (
        "epistemic_supervision",
        _stage_epistemic_supervision,
        ("symbol_targeting", "squeeze_bubble_intelligence"),
    ),
    ("adversarial_signal_panel", _stage_adversarial_signal_panel, ("forward_paper_walk", "forward_book_risk", "market_context_fusion")),
    ("trade_loss_coach", _stage_trade_loss_coach, ("forward_paper_walk",)),
    ("target_screener", _stage_target_screener, ("history_validation", "macro_context_gate", "market_context_fusion")),
    ("universe_governor", _stage_universe_governor, ("history_validation", "macro_context_gate", "target_screener")),
    ("exit_policy_search", _stage_exit_policy_search, ("real_signals",)),
    ("chart_vision", _stage_chart_vision, ("market_structure",)),
    ("indicator_foundry", _stage_indicator_foundry, ("history_validation",)),
    ("agentic_account_reconciliation", _stage_agentic_account_reconciliation, ()),
    ("action_readiness_gate", _stage_action_readiness_gate, ()),
)

STATUS_KEYS = (
    "freshness_status",
    "integrity_status",
    "macro_status",
    "simulation_status",
    "book_risk_status",
    "dataset_status",
    "local_ohlcv_status",
    "signal_engine_status",
    "backtest_status",
    "structure_status",
    "baseline_status",
    "era_status",
    "truth_status",
    "fitness_decision",
    "chain_analytics_status",
    "surface_status",
    "context_status",
    "calibration_status",
    "forward_walk_status",
    "forecast_card_status",
    "kaizen_status",
    "slo_status",
    "book_quality_status",
    "stress_status",
    "probe_status",
    "playbook_status",
    "playbook_stage_status",
    "targeting_status",
    "squeeze_bubble_status",
    "epistemic_status",
    "panel_status",
    "coach_status",
    "screener_status",
    "universe_status",
    "signal_calibration_status",
    "exit_search_status",
    "chart_status",
    "foundry_status",
    "reconciliation_status",
    "readiness_status",
)


def _journal_early_return(summary: dict[str, Any]) -> dict[str, Any]:
    recorded_at_utc = datetime.now(timezone.utc).isoformat()
    run_id = (
        "supervisor-early-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-"
        f"{os.getpid()}-{uuid.uuid4()}"
    )
    journal_entry = {
        "artifact_type": "supervisor_run_journal_entry",
        "journal_entry_kind": "early_return",
        "run_id": run_id,
        "run_utc": recorded_at_utc,
        "supervisor_status": str(summary["supervisor_status"]),
        "stages_green": 0,
        "stages_completed_degraded": 0,
        "stages_failed_absorbed": 0,
        "stages_skipped_dependency": 0,
        "stages_skipped_run_budget": 0,
        "stage_states": {},
        "reported_statuses": {},
        "regressions_vs_previous_run": [],
        "recoveries_vs_previous_run": [],
        "early_return": True,
        "participates_in_stage_regression_baseline": False,
        "detail": str(summary.get("detail", "")),
        "paper_only": True,
        "live_blocked": True,
    }
    append_jsonl(SUPERVISOR_RUN_JOURNAL_PATH, journal_entry)
    return {
        **summary,
        "run_id": run_id,
        "run_utc": recorded_at_utc,
        "journal_visible": True,
    }


def run_resilient_research_supervisor(
    stages: tuple[tuple[str, Callable[[], dict[str, Any]], tuple[str, ...]], ...] = STAGES,
) -> dict[str, Any]:
    if stages is not STAGES:
        # injected-stage runs (tests, experiments) are same-process and sequential;
        # they neither contend for nor should be blocked by the production lock
        return _run_stages(stages)
    disk_usage = shutil.disk_usage(REPO_ROOT)
    if disk_usage.free < MIN_SUPERVISOR_FREE_BYTES:
        return _journal_early_return(
            {
                "artifact_type": "resilient_research_supervisor_summary",
                "supervisor_status": "blocked_insufficient_disk_headroom",
                "stages_total": len(stages),
                "stages_completed": 0,
                "incident_count": 0,
                "repair_queue_count": 1,
                "free_bytes": disk_usage.free,
                "required_free_bytes": MIN_SUPERVISOR_FREE_BYTES,
                "detail": "write-heavy production research did not start; free disk is below the sealed safety floor",
                "paper_only": True,
                "live_blocked": True,
            }
        )
    lock_id = _acquire_lock()
    if lock_id is None:
        return _journal_early_return(
            {
                "artifact_type": "resilient_research_supervisor_summary",
                "supervisor_status": "locked_concurrent_run",
                "stages_total": len(stages),
                "stages_completed": 0,
                "incident_count": 0,
                "repair_queue_count": 0,
                "detail": "another supervisor run holds artifacts/.supervisor.lock; no stage artifacts were touched",
                "paper_only": True,
                "live_blocked": True,
            }
        )
    try:
        return _run_stages(stages)
    finally:
        _release_lock(lock_id)


def _run_stages(
    stages: tuple[tuple[str, Callable[[], dict[str, Any]], tuple[str, ...]], ...],
) -> dict[str, Any]:
    production_run = stages is STAGES
    run_started_utc = datetime.now(timezone.utc).isoformat()
    run_started_monotonic = time.monotonic()
    run_id = f"supervisor-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}"
    progress: dict[str, Any] = {
        "artifact_type": "resilient_research_supervisor_active_run",
        "run_id": run_id,
        "pid": os.getpid(),
        "run_status": "running",
        "started_at_utc": run_started_utc,
        "heartbeat_at_utc": run_started_utc,
        "current_stage": "initializing",
        "current_stage_index": 0,
        "stages_total": len(stages),
        "completed_stage_count": 0,
        "stage_progress": {},
        "paper_only": True,
        "live_blocked": True,
    }
    if production_run:
        _write_supervisor_progress(progress)
    results: dict[str, dict[str, Any]] = {}
    incidents: list[dict[str, Any]] = []
    repair_queue: list[dict[str, Any]] = []
    succeeded: set[str] = set()
    for stage_index, (name, runner, dependencies) in enumerate(stages, start=1):
        run_elapsed_seconds = time.monotonic() - run_started_monotonic
        run_remaining_seconds = SUPERVISOR_HARD_TIMEOUT_SECONDS - run_elapsed_seconds
        if production_run and run_remaining_seconds <= 0:
            results[name] = {
                "stage_status": "skipped_run_budget",
                "stage_duration_seconds": 0.0,
                "stage_soft_budget_exceeded": False,
                "run_elapsed_seconds": round(run_elapsed_seconds, 3),
                "run_hard_timeout_seconds": SUPERVISOR_HARD_TIMEOUT_SECONDS,
            }
            repair_queue.append(
                _repair_item(
                    name,
                    "supervisor_run_budget_exhausted",
                    f"whole-run hard timeout reached after {run_elapsed_seconds:.3f} seconds",
                )
            )
            _complete_progress_stage(progress, name, stage_index, results[name])
            continue
        missing = [dependency for dependency in dependencies if dependency not in succeeded]
        if missing:
            results[name] = {
                "stage_status": "skipped_dependency",
                "missing_dependencies": missing,
                "stage_duration_seconds": 0.0,
                "stage_soft_budget_exceeded": False,
            }
            repair_queue.append(_repair_item(name, "skipped_dependency", f"blocked by failed stage(s): {missing}"))
            if production_run:
                _complete_progress_stage(progress, name, stage_index, results[name])
            continue
        stage_started_utc = datetime.now(timezone.utc).isoformat()
        stage_started_monotonic = time.monotonic()
        if production_run:
            progress.update(
                {
                    "heartbeat_at_utc": stage_started_utc,
                    "current_stage": name,
                    "current_stage_index": stage_index,
                    "current_stage_started_at_utc": stage_started_utc,
                    "elapsed_seconds": round(time.monotonic() - run_started_monotonic, 3),
                }
            )
            _write_supervisor_progress(progress)
        try:
            outcome = (
                _run_stage_isolated(
                    name,
                    run_id,
                    stage_index,
                    SUPERVISOR_ACTIVE_RUN_PATH,
                    min(
                        STAGE_HARD_TIMEOUT_SECONDS,
                        max(1, int(run_remaining_seconds)),
                    ),
                )
                if production_run
                else runner()
            )
            status = _extract_status(outcome)
            stage_status = "completed_degraded" if _is_degraded(status) else "completed"
            stage_duration = round(time.monotonic() - stage_started_monotonic, 3)
            results[name] = {
                "stage_status": stage_status,
                "reported_status": status,
                "stage_started_at_utc": stage_started_utc,
                "stage_finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "stage_duration_seconds": stage_duration,
                "stage_soft_budget_exceeded": stage_duration > STAGE_SOFT_BUDGET_SECONDS,
            }
            # Degraded stages still satisfy dependencies: consumers are written to
            # handle blocked inputs and must keep producing their own honest
            # blocked statuses rather than being skipped into silence.
            succeeded.add(name)
        except Exception as error:  # noqa: BLE001 - absorb, record, continue
            incident = {
                "artifact_type": "research_supervisor_incident",
                "stage": name,
                "error_type": type(error).__name__,
                "error_message": str(error)[:500],
                "traceback_tail": traceback.format_exc(limit=5)[-1500:],
                "recorded_as_pass": False,
                "paper_only": True,
                "live_blocked": True,
            }
            incidents.append(incident)
            repair_queue.append(_repair_item(name, type(error).__name__, str(error)[:200]))
            stage_duration = round(time.monotonic() - stage_started_monotonic, 3)
            results[name] = {
                "stage_status": "failed_absorbed",
                "error_type": type(error).__name__,
                "stage_started_at_utc": stage_started_utc,
                "stage_finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "stage_duration_seconds": stage_duration,
                "stage_soft_budget_exceeded": stage_duration > STAGE_SOFT_BUDGET_SECONDS,
            }
        if production_run:
            _complete_progress_stage(progress, name, stage_index, results[name])
    completed = sum(1 for record in results.values() if record["stage_status"] in {"completed", "completed_degraded"})
    green = sum(1 for record in results.values() if record["stage_status"] == "completed")
    degraded = sum(1 for record in results.values() if record["stage_status"] == "completed_degraded")
    if completed == len(stages):
        overall = "all_stages_completed" if degraded == 0 else "completed_with_degraded_statuses"
    else:
        overall = "degraded_with_incidents" if completed > 0 else "all_stages_failed"
    regressions, recoveries = _diff_against_previous_run(results)
    summary = {
        "artifact_type": "resilient_research_supervisor_summary",
        "supervisor_status": overall,
        "stages_total": len(stages),
        "stages_completed": completed,
        "stages_green": green,
        "stages_completed_degraded": degraded,
        "stages_failed_absorbed": sum(1 for record in results.values() if record["stage_status"] == "failed_absorbed"),
        "stages_skipped_dependency": sum(
            1 for record in results.values() if record["stage_status"] == "skipped_dependency"
        ),
        "stages_skipped_run_budget": sum(
            1 for record in results.values() if record["stage_status"] == "skipped_run_budget"
        ),
        "stage_results": results,
        "regressions_vs_previous_run": regressions,
        "recoveries_vs_previous_run": recoveries,
        "incident_count": len(incidents),
        "repair_queue_count": len(repair_queue),
        "run_id": run_id,
        "run_started_at_utc": run_started_utc,
        "run_finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_duration_seconds": round(time.monotonic() - run_started_monotonic, 3),
        "stages_exceeding_soft_budget": sorted(
            name for name, record in results.items() if record.get("stage_soft_budget_exceeded") is True
        ),
        "stage_soft_budget_seconds": STAGE_SOFT_BUDGET_SECONDS,
        "stage_hard_timeout_seconds": STAGE_HARD_TIMEOUT_SECONDS,
        "run_hard_timeout_seconds": SUPERVISOR_HARD_TIMEOUT_SECONDS,
        "failure_policy": "absorb_record_continue_never_pass",
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    SUPERVISOR_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(SUPERVISOR_SUMMARY_PATH, summary)
    for incident in incidents:
        append_jsonl(
            SUPERVISOR_INCIDENTS_PATH,
            {
                **incident,
                "run_id": run_id,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
    for repair_item in repair_queue:
        append_jsonl(
            SUPERVISOR_REPAIR_QUEUE_PATH,
            {
                **repair_item,
                "run_id": run_id,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
    if production_run:
        progress.update(
            {
                "run_status": "completed",
                "supervisor_status": overall,
                "heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
                "finished_at_utc": summary["run_finished_at_utc"],
                "elapsed_seconds": summary["run_duration_seconds"],
                "current_stage": "",
                "current_stage_index": len(stages),
                "completed_stage_count": len(results),
            }
        )
        _write_supervisor_progress(progress)
    if stages is not STAGES:
        # injected-stage runs (tests, experiments) must not pollute the live
        # run journal or its regression baseline
        _write_report(summary)
        return summary
    append_jsonl(
        SUPERVISOR_RUN_JOURNAL_PATH,
        {
            "artifact_type": "supervisor_run_journal_entry",
            "journal_entry_kind": "completed_run",
            "run_id": run_id,
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "supervisor_status": overall,
            "stages_green": green,
            "stages_completed_degraded": degraded,
            "stages_failed_absorbed": summary["stages_failed_absorbed"],
            "stages_skipped_dependency": summary["stages_skipped_dependency"],
            "stages_skipped_run_budget": summary["stages_skipped_run_budget"],
            "stage_states": {name: record["stage_status"] for name, record in results.items()},
            "reported_statuses": {name: record.get("reported_status", "") for name, record in results.items()},
            "regressions_vs_previous_run": regressions,
            "recoveries_vs_previous_run": recoveries,
            "early_return": False,
            "participates_in_stage_regression_baseline": True,
        },
    )
    _write_report(summary)
    return summary


def _run_stage_isolated(
    stage_name: str,
    run_id: str,
    stage_index: int,
    heartbeat_path: Path | None,
    hard_timeout_seconds: int,
) -> dict[str, Any]:
    if hard_timeout_seconds <= 0:
        raise ValueError(
            "isolated supervisor stage hard timeout must be positive: "
            f"stage={stage_name}, hard_timeout_seconds={hard_timeout_seconds}"
        )
    output_path = (
        SUPERVISOR_ARTIFACT_DIR
        / "stage_results"
        / f"{run_id}.{stage_index:02d}.{stage_name}.json"
    )
    command = [
        sys.executable,
        "-X",
        "faulthandler",
        "-m",
        "dopey_autonomy.run_resilient_research_supervisor",
        "--stage",
        stage_name,
        "--output",
        str(output_path),
    ]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creation_flags,
    )
    stage_started = time.monotonic()
    while True:
        elapsed = time.monotonic() - stage_started
        remaining = hard_timeout_seconds - elapsed
        if remaining <= 0:
            _terminate_stage_process_tree(process)
            stdout, stderr = process.communicate()
            raise RuntimeError(
                "supervisor stage exceeded its hard process boundary: "
                f"stage={stage_name}, timeout_seconds={hard_timeout_seconds}, "
                f"stdout_tail={stdout[-2_000:]}, stderr_tail={stderr[-4_000:]}"
            )
        try:
            stdout, stderr = process.communicate(timeout=min(15.0, remaining))
            break
        except subprocess.TimeoutExpired:
            if heartbeat_path is not None:
                try:
                    _refresh_stage_heartbeat(
                        heartbeat_path,
                        stage_name,
                        process.pid,
                        round(time.monotonic() - stage_started, 3),
                    )
                except Exception:
                    _terminate_stage_process_tree(process)
                    process.communicate()
                    raise
    if process.returncode != 0:
        raise RuntimeError(
            "isolated supervisor stage exited nonzero: "
            f"stage={stage_name}, return_code={process.returncode}, "
            f"stdout_tail={stdout[-2_000:]}, stderr_tail={stderr[-4_000:]}"
        )
    if not output_path.exists():
        raise FileNotFoundError(
            f"isolated supervisor stage did not publish its result: stage={stage_name}, path={output_path}"
        )
    try:
        result = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"isolated supervisor stage result is unreadable: stage={stage_name}, path={output_path}"
        ) from error
    if not isinstance(result, dict):
        raise TypeError(
            f"isolated supervisor stage result must be a JSON object: stage={stage_name}, path={output_path}"
        )
    return result


def _refresh_stage_heartbeat(
    heartbeat_path: Path,
    stage_name: str,
    child_process_id: int,
    stage_elapsed_seconds: float,
) -> None:
    try:
        record = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"stage heartbeat artifact is unreadable: stage={stage_name}, path={heartbeat_path}"
        ) from error
    if not isinstance(record, dict):
        raise TypeError(f"stage heartbeat artifact must be a JSON object: path={heartbeat_path}")
    record.update(
        {
            "heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
            "current_stage": stage_name,
            "current_stage_child_pid": child_process_id,
            "current_stage_elapsed_seconds": stage_elapsed_seconds,
        }
    )
    write_json_atomic(heartbeat_path, record)


def _terminate_stage_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise RuntimeError(
                f"SystemRoot is required to terminate timed-out stage tree: pid={process.pid}"
            )
        taskkill = Path(system_root) / "System32" / "taskkill.exe"
        terminated = subprocess.run(
            [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
            text=True,
            capture_output=True,
            check=False,
        )
        if terminated.returncode != 0 and process.poll() is None:
            raise RuntimeError(
                "failed to terminate timed-out stage process tree: "
                f"pid={process.pid}, return_code={terminated.returncode}, stderr={terminated.stderr[-2_000:]}"
            )
        return
    process.kill()


def _run_named_stage(stage_name: str, output_path: Path) -> dict[str, Any]:
    runners = {name: runner for name, runner, _dependencies in STAGES}
    if stage_name not in runners:
        raise ValueError(f"unknown supervisor stage: stage={stage_name}")
    result = runners[stage_name]()
    if not isinstance(result, dict):
        raise TypeError(
            f"supervisor stage must return a JSON object: stage={stage_name}, actual={type(result).__name__}"
        )
    write_json_atomic(output_path, result)
    return result


def _complete_progress_stage(
    progress: dict[str, Any],
    stage_name: str,
    stage_index: int,
    result: dict[str, Any],
) -> None:
    stage_progress = progress.get("stage_progress")
    if not isinstance(stage_progress, dict):
        raise TypeError("supervisor stage_progress must be an object")
    stage_progress[stage_name] = dict(result)
    progress.update(
        {
            "heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
            "current_stage": "between_stages",
            "current_stage_index": stage_index,
            "completed_stage_count": len(stage_progress),
        }
    )
    _write_supervisor_progress(progress)


def _write_supervisor_progress(progress: dict[str, Any]) -> bool:
    try:
        write_json_atomic(SUPERVISOR_ACTIVE_RUN_PATH, progress)
    except OSError as error:
        print(
            json.dumps(
                {
                    "event": "supervisor_progress_publish_failed_best_effort",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "run_id": str(progress.get("run_id", "")),
                    "current_stage": str(progress.get("current_stage", "")),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return False
    return True


def read_supervisor_progress() -> dict[str, Any]:
    if not SUPERVISOR_ACTIVE_RUN_PATH.exists():
        return {}
    try:
        value = json.loads(SUPERVISOR_ACTIVE_RUN_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"supervisor active-run artifact is unreadable: path={SUPERVISOR_ACTIVE_RUN_PATH}, error={error}"
        ) from error
    if not isinstance(value, dict):
        raise TypeError(f"supervisor active-run artifact must be an object: path={SUPERVISOR_ACTIVE_RUN_PATH}")
    return value


def _read_lock_payload() -> dict[str, Any] | None:
    try:
        payload = json.loads(SUPERVISOR_LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _lock_age_seconds() -> float:
    return max(0.0, time.time() - SUPERVISOR_LOCK_PATH.stat().st_mtime)


def _process_started_at_utc(process_id: int) -> str | None:
    if process_id <= 0:
        return None
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise RuntimeError(
                "SystemRoot is required to verify Windows process identity"
            )
        powershell = (
            Path(system_root)
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        completed = subprocess.run(
            [
                str(powershell),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    f"$p = Get-Process -Id {process_id} -ErrorAction Stop; "
                    "$p.StartTime.ToUniversalTime().ToString('o')"
                ),
            ],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            return None
        raw_timestamp = completed.stdout.strip()
    else:
        completed = subprocess.run(
            ["ps", "-p", str(process_id), "-o", "lstart="],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        parsed = datetime.strptime(
            completed.stdout.strip(),
            "%a %b %d %H:%M:%S %Y",
        ).astimezone(timezone.utc)
        return parsed.isoformat()
    try:
        parsed = datetime.fromisoformat(raw_timestamp)
    except ValueError as error:
        raise RuntimeError(
            "Windows process identity returned an invalid start timestamp: "
            f"pid={process_id}, timestamp={raw_timestamp!r}"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _process_identity_matches(
    process_id: int,
    expected_started_at_utc: object,
) -> bool:
    if not isinstance(expected_started_at_utc, str) or not expected_started_at_utc:
        return False
    observed_started_at_utc = _process_started_at_utc(process_id)
    if observed_started_at_utc is None:
        return False
    try:
        expected = datetime.fromisoformat(expected_started_at_utc)
        observed = datetime.fromisoformat(observed_started_at_utc)
    except ValueError:
        return False
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return abs((expected - observed).total_seconds()) <= 1.0


def _record_lock_recovery(
    reason: str,
    prior_payload: dict[str, Any] | None,
    prior_age_seconds: float,
) -> None:
    append_jsonl(
        SUPERVISOR_LOCK_RECOVERY_PATH,
        {
            "artifact_type": "research_supervisor_lock_recovery",
            "recovered_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "prior_age_seconds": round(prior_age_seconds, 3),
            "prior_payload": prior_payload,
            "paper_only": True,
            "live_blocked": True,
        },
    )


def _acquire_lock() -> str | None:
    SUPERVISOR_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SUPERVISOR_LOCK_PATH.exists():
        prior_age_seconds = _lock_age_seconds()
        prior_payload = _read_lock_payload()
        owner_pid = _lock_owner_pid()
        recovery_reason = "dead_owner"
        if owner_pid is not None and _pid_running(owner_pid):
            expected_start = (
                prior_payload.get("process_started_at_utc")
                if prior_payload is not None
                else None
            )
            if _process_identity_matches(owner_pid, expected_start):
                return None
            if expected_start is None and prior_age_seconds < CORRUPT_LOCK_STALE_SECONDS:
                return None
            recovery_reason = (
                "legacy_live_pid_lock_expired"
                if expected_start is None
                else "pid_reused"
            )
        else:
            if prior_payload is None and prior_age_seconds < CORRUPT_LOCK_STALE_SECONDS:
                return None
            recovery_reason = (
                "corrupt_lock_expired"
                if prior_payload is None
                else "dead_owner"
            )
        SUPERVISOR_LOCK_PATH.unlink(missing_ok=True)
        _record_lock_recovery(recovery_reason, prior_payload, prior_age_seconds)
    process_started_at_utc = _process_started_at_utc(os.getpid())
    if process_started_at_utc is None:
        raise RuntimeError(
            "cannot acquire supervisor lock without a verifiable process start time: "
            f"pid={os.getpid()}"
        )
    lock_id = str(uuid.uuid4())
    try:
        handle = os.open(SUPERVISOR_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    with os.fdopen(handle, "w", encoding="utf-8") as lock_file:
        lock_file.write(
            json.dumps(
                {
                    "lock_id": lock_id,
                    "pid": os.getpid(),
                    "process_started_at_utc": process_started_at_utc,
                    "acquired_utc": datetime.now(timezone.utc).isoformat(),
                },
                sort_keys=True,
            )
            + "\n"
        )
        lock_file.flush()
        os.fsync(lock_file.fileno())
    return lock_id


def _release_lock(lock_id: str) -> None:
    payload = _read_lock_payload()
    if payload is None or payload.get("lock_id") != lock_id:
        return
    SUPERVISOR_LOCK_PATH.unlink(missing_ok=True)


def _lock_owner_pid() -> int | None:
    payload = _read_lock_payload()
    if payload is None:
        return None
    value = payload.get("pid")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def supervisor_run_active() -> bool:
    if not SUPERVISOR_LOCK_PATH.exists():
        return False
    owner_pid = _lock_owner_pid()
    if owner_pid is None or not _pid_running(owner_pid):
        return False
    payload = _read_lock_payload()
    if payload is None:
        return False
    expected_start = payload.get("process_started_at_utc")
    if expected_start is None:
        return _lock_age_seconds() < CORRUPT_LOCK_STALE_SECONDS
    return _process_identity_matches(owner_pid, expected_start)


def _pid_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise RuntimeError("SystemRoot is required to verify a Windows supervisor lock owner")
        tasklist = os.path.join(system_root, "System32", "tasklist.exe")
        completed = subprocess.run(
            [tasklist, "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Windows supervisor process-liveness check failed: "
                f"pid={process_id}, return_code={completed.returncode}, stderr={completed.stderr[-2_000:]}"
            )
        rows = list(csv.reader(completed.stdout.splitlines()))
        return any(len(row) >= 2 and row[1].strip() == str(process_id) for row in rows)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_degraded(status: str) -> bool:
    lowered = status.lower()
    return (
        lowered in DEGRADED_EXACT_STATUSES
        or lowered.startswith(DEGRADED_STATUS_PREFIXES)
        or lowered.endswith(DEGRADED_STATUS_SUFFIXES)
    )


def diff_stage_states(
    previous: dict[str, str], current: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Stages that got worse / better vs the previous run (order: worse, better)."""
    rank = {"completed": 0, "completed_degraded": 1, "skipped_dependency": 2, "failed_absorbed": 3}
    regressions = sorted(
        name for name, state in current.items()
        if name in previous and rank.get(state, 3) > rank.get(previous[name], 3)
    )
    recoveries = sorted(
        name for name, state in current.items()
        if name in previous and rank.get(state, 3) < rank.get(previous[name], 3)
    )
    return regressions, recoveries


def _diff_against_previous_run(results: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    if not SUPERVISOR_RUN_JOURNAL_PATH.exists():
        return [], []
    previous: dict[str, str] = {}
    try:
        lines = SUPERVISOR_RUN_JOURNAL_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if line.strip():
                entry = json.loads(line)
                if entry.get("early_return") is True:
                    continue
                stage_states = entry.get("stage_states")
                if not isinstance(stage_states, dict):
                    continue
                previous = {
                    str(name): str(status)
                    for name, status in stage_states.items()
                }
                break
    except (json.JSONDecodeError, OSError):
        return [], []
    current = {name: str(record["stage_status"]) for name, record in results.items()}
    return diff_stage_states(previous, current)


def _extract_status(outcome: dict[str, Any]) -> str:
    for key in STATUS_KEYS:
        if key in outcome:
            return str(outcome[key])
    # No recognizable status field: the stage finished but reported nothing
    # verifiable. The "missing_" marker classifies it as degraded so a silent
    # stage is never counted green.
    return "missing_status_field"


def _repair_item(stage: str, reason: str, detail: str) -> dict[str, Any]:
    return {
        "artifact_type": "research_supervisor_repair_item",
        "stage": stage,
        "reason": reason,
        "detail": detail,
        "suggested_action": f"rerun stage `{stage}` after fixing `{reason}`",
        "paper_only": True,
        "live_blocked": True,
    }


def _write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Resilient Research Supervisor Report",
        "",
        "## Policy",
        "Every stage runs; failures are absorbed into incident + repair artifacts and true",
        "dependents are skipped with reasons. A failure is never recorded as a pass, and the",
        "supervisor can never promote a strategy.",
        "",
        f"- supervisor_status: `{summary['supervisor_status']}`",
        f"- stages: `{summary['stages_completed']}`/`{summary['stages_total']}` completed "
        f"(`{summary.get('stages_green', summary['stages_completed'])}` green, "
        f"`{summary.get('stages_completed_degraded', 0)}` degraded/blocked-input), "
        f"`{summary['stages_failed_absorbed']}` failed (absorbed), "
        f"`{summary['stages_skipped_dependency']}` skipped on dependencies, "
        f"`{summary.get('stages_skipped_run_budget', 0)}` skipped on whole-run budget",
        f"- regressions vs previous run: `{summary.get('regressions_vs_previous_run', [])}` | "
        f"recoveries: `{summary.get('recoveries_vs_previous_run', [])}`",
        f"- incidents: `{summary['incident_count']}` | repair queue: `{summary['repair_queue_count']}`",
        "",
        "## Stage Results",
    ]
    for name, record in summary["stage_results"].items():
        reported = record.get("reported_status", record.get("error_type", record.get("missing_dependencies", "")))
        lines.append(f"- `{name}`: `{record['stage_status']}` ({reported})")
    lines.extend(
        [
            "",
            "## Safety",
            "- paper_only: `true`; live_blocked: `true`; strategy_promotion_allowed: `false`.",
        ]
    )
    SUPERVISOR_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _record_unhandled_supervisor_crash(error: Exception) -> None:
    recorded_at_utc = datetime.now(timezone.utc).isoformat()
    crash_id = (
        f"supervisor-crash-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        f"-{os.getpid()}"
    )
    incident = {
        "artifact_type": "research_supervisor_incident",
        "run_id": crash_id,
        "stage": "supervisor_top_level",
        "error_type": type(error).__name__,
        "error_message": str(error)[:500],
        "traceback_tail": traceback.format_exc(limit=8)[-2_000:],
        "recorded_at_utc": recorded_at_utc,
        "recorded_as_pass": False,
        "paper_only": True,
        "live_blocked": True,
    }
    repair_item = {
        **_repair_item(
            "supervisor_top_level",
            type(error).__name__,
            str(error)[:200],
        ),
        "run_id": crash_id,
        "recorded_at_utc": recorded_at_utc,
    }
    tombstone = {
        "artifact_type": "resilient_research_supervisor_active_run",
        "run_id": crash_id,
        "pid": os.getpid(),
        "run_status": "crashed_unhandled",
        "heartbeat_at_utc": recorded_at_utc,
        "finished_at_utc": recorded_at_utc,
        "error_type": type(error).__name__,
        "error_message": str(error)[:500],
        "paper_only": True,
        "live_blocked": True,
    }
    failures: list[str] = []
    try:
        append_jsonl(SUPERVISOR_INCIDENTS_PATH, incident)
    except OSError as write_error:
        failures.append(
            f"incident:{type(write_error).__name__}:{write_error}"
        )
    try:
        append_jsonl(SUPERVISOR_REPAIR_QUEUE_PATH, repair_item)
    except OSError as write_error:
        failures.append(
            f"repair_queue:{type(write_error).__name__}:{write_error}"
        )
    try:
        write_json_atomic(SUPERVISOR_ACTIVE_RUN_PATH, tombstone)
    except OSError as write_error:
        failures.append(
            f"active_run:{type(write_error).__name__}:{write_error}"
        )
    if failures:
        print(
            json.dumps(
                {
                    "event": "supervisor_crash_evidence_publish_incomplete",
                    "crash_id": crash_id,
                    "failures": failures,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=tuple(name for name, _runner, _dependencies in STAGES))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.stage is not None or arguments.output is not None:
        if arguments.stage is None or arguments.output is None:
            parser.error("--stage and --output must be provided together")
        result = _run_named_stage(arguments.stage, arguments.output)
        print(json.dumps({"stage": arguments.stage, "reported_status": _extract_status(result)}, sort_keys=True))
        return 0
    try:
        summary = run_resilient_research_supervisor()
    except Exception as error:
        _record_unhandled_supervisor_crash(error)
        raise
    print(
        json.dumps(
            {
                "supervisor_status": summary["supervisor_status"],
                "stages_completed": summary["stages_completed"],
                "stages_total": summary["stages_total"],
                "incident_count": summary["incident_count"],
                "repair_queue_count": summary["repair_queue_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return (
        2
        if summary["supervisor_status"]
        in {
            "blocked_insufficient_disk_headroom",
            "locked_concurrent_run",
        }
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
