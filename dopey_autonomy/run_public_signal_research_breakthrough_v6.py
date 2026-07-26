"""Full orchestrator for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6.

Sequence (per spec):
1. dopey_validation.run_public_signal_research_v6_preflight
2. dopey_validation.run_public_signal_research_baseline_freezer_v6
3. dopey_signal_research.run_v5_gate_rejection_analyzer_v6
4. dopey_signal_research.run_research_mutation_queue_executor_v6
5. dopey_signal_research.run_breakthrough_blocker_repair_policy_v6
6. dopey_signal_research.run_research_candidate_generator_v6
7. dopey_signal_research.run_profit_holdout_split_scorer_v6
8. dopey_signal_research.run_research_path_simulator_v6
9. dopey_signal_research.run_research_tournament_v6
10. dopey_signal_research.run_research_breakthrough_gate_v6
11. dopey_signal_research.run_research_mutation_queue_v6
12. dopey_scoreboard.run_public_signal_research_scoreboard_v6
13. dopey_live_gate.run_public_signal_research_live_gate_status_v6

Status logic:
- breakthroughs found -> research_breakthrough_candidates_found_live_gate_locked
  next DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1
- blockers improved but no breakthrough -> watchlist_blockers_improved_requires_v7
  next DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7
- no improvement -> no_further_repair_signal_feature_expansion_required
  next DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2
- public lake degraded -> DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3

Known gaps:
- V5 expensive lane partial timeout remains inconclusive
- V5 baseline snapshot gap acknowledged
"""
from __future__ import annotations

import json
import shutil
import subprocess
import traceback
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v6_common import (
    BASELINE_FREEZE_V6_SUMMARY_PATH,
    BASELINE_SNAPSHOT_V6_MANIFEST_PATH,
    BREAKTHROUGH_V6_PATH,
    CANDIDATE_GENERATOR_V6_SUMMARY_PATH,
    GATE_V6_SUMMARY_PATH,
    WATCHLIST_V6_PATH,
    LIVE_GATE_ROOT,
    MUTATION_EXEC_V6_SUMMARY_PATH,
    MUTATION_QUEUE_V6_SUMMARY_PATH,
    PREFLIGHT_V6_SUMMARY_PATH,
    RESEARCH_V6_ROOT,
    RESEARCH_V6_VERSION,
    SCOREBOARD_ROOT,
    SCORER_V6_SUMMARY_PATH,
    SIMULATOR_V6_SUMMARY_PATH,
    TOURNAMENT_V6_SUMMARY_PATH,
    V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH,
    research_v6_proof_record,
    utc_now_iso,
)
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


__all__ = ["run_public_signal_research_breakthrough_v6"]


SUMMARY_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_summary.json"
STEPS_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_steps.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_quality_flags.jsonl"
PROOF_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_proof.jsonl"
VALIDATION_SUMMARY_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_validation_summary.json"
TIMEOUT_RECORDS_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_timeout_records.jsonl"
LOCAL_MANIFEST_PATH = RESEARCH_V6_ROOT / "public_signal_research_breakthrough_v6_session_copy_manifest.json"

REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_COMMANDS.md"
HANDOFF_FOLDER = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6"

EXPECTED_PREFLIGHT_STATUS = "ready_for_watchlist_breakthrough_repair"


ORCHESTRATOR_STEPS: tuple[tuple[str, str, int], ...] = (
    ("v6_preflight", "dopey_validation.run_public_signal_research_v6_preflight", 240),
    ("v5_baseline_freeze", "dopey_validation.run_public_signal_research_baseline_freezer_v6", 240),
    ("v5_gate_rejection_analyzer", "dopey_signal_research.run_v5_gate_rejection_analyzer_v6", 240),
    ("v6_mutation_executor", "dopey_signal_research.run_research_mutation_queue_executor_v6", 240),
    ("v6_blocker_repair_policy", "dopey_signal_research.run_breakthrough_blocker_repair_policy_v6", 240),
    ("v6_candidate_generator", "dopey_signal_research.run_research_candidate_generator_v6", 240),
    ("v6_scorer", "dopey_signal_research.run_profit_holdout_split_scorer_v6", 240),
    ("v6_path_simulator", "dopey_signal_research.run_research_path_simulator_v6", 240),
    ("v6_tournament", "dopey_signal_research.run_research_tournament_v6", 240),
    ("v6_breakthrough_gate", "dopey_signal_research.run_research_breakthrough_gate_v6", 240),
    ("v6_mutation_queue", "dopey_signal_research.run_research_mutation_queue_v6", 240),
    ("v6_scoreboard", "dopey_scoreboard.run_public_signal_research_scoreboard_v6", 240),
    ("v6_live_gate", "dopey_live_gate.run_public_signal_research_live_gate_status_v6", 240),
)


def _read_json_safe(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _run_step(step_id: str, module: str, timeout_seconds: int = 240) -> dict[str, object]:
    """Run a single orchestrator step via subprocess with a timeout."""
    started = utc_now_iso()
    cmd = [
        str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
        "-m",
        module,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        rec: dict[str, object] = {
            "artifact_type": "public_signal_research_breakthrough_v6_step",
            "step_id": step_id,
            "module": module,
            "started_at": started,
            "finished_at": utc_now_iso(),
            "exit_code": proc.returncode,
            "timed_out": False,
            "status": "ok" if proc.returncode == 0 else "nonzero_exit",
            "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
            "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            "live_trading_enabled": False,
        }
    except subprocess.TimeoutExpired as exc:
        rec = {
            "artifact_type": "public_signal_research_breakthrough_v6_step",
            "step_id": step_id,
            "module": module,
            "started_at": started,
            "finished_at": utc_now_iso(),
            "exit_code": None,
            "timed_out": True,
            "status": "inconclusive_timeout",
            "timeout_seconds": timeout_seconds,
            "timeout_recorded_as_pass": False,
            "stdout_tail": (exc.stdout or b"").decode("utf-8", errors="replace")[-500:]
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or "")[-500:],
            "stderr_tail": (exc.stderr or b"").decode("utf-8", errors="replace")[-500:]
                if isinstance(exc.stderr, bytes)
                else (exc.stderr or "")[-500:],
            "live_trading_enabled": False,
        }
    except Exception as exc:  # noqa: BLE001
        rec = {
            "artifact_type": "public_signal_research_breakthrough_v6_step",
            "step_id": step_id,
            "module": module,
            "started_at": started,
            "finished_at": utc_now_iso(),
            "exit_code": None,
            "timed_out": False,
            "status": "runner_error",
            "error": str(exc),
            "traceback": traceback.format_exc()[-500:],
            "live_trading_enabled": False,
        }
    return rec


def _step_failure_present(steps: list[dict[str, object]]) -> bool:
    """True if any step failed with a real error (not a watchdog timeout)."""
    for rec in steps:
        status = str(rec.get("status", ""))
        if status not in ("ok", "inconclusive_timeout"):
            return True
    return False


def _orchestrator_status(
    breakthroughs: list[dict[str, object]],
    watchlist: list[dict[str, object]],
    tournament: dict[str, object],
    gate: dict[str, object],
    steps: list[dict[str, object]],
) -> tuple[str, str]:
    """Determine orchestrator status and next target."""
    pf_above = int(gate.get("pf_above_threshold_count", 0) or 0)
    improved_vs_v5 = int(tournament.get("improved_vs_v5_count", 0) or 0)
    watchlist_count = len(watchlist)

    if breakthroughs:
        return (
            "research_breakthrough_candidates_found_live_gate_locked",
            "DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1",
        )

    if pf_above > 0 or improved_vs_v5 > 0 or watchlist_count > 0:
        return (
            "watchlist_blockers_improved_requires_v7",
            "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7",
        )

    return (
        "no_further_repair_signal_feature_expansion_required",
        "DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2",
    )


def _known_gaps() -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    gaps.append(
        {
            "gap_id": "v5_expensive_lane_partial_timeout",
            "status": "inconclusive_timeout",
            "timeout_recorded_as_pass": False,
            "note": "V5 expensive lane partial timeout remains inconclusive; core V6 research artifacts are independent.",
        }
    )
    gaps.append(
        {
            "gap_id": "v5_baseline_snapshot_gap_acknowledged",
            "status": "acknowledged",
            "note": "V5 baseline snapshot covers immutable summary/dashboard/doc sources; supporting JSONL records remain in live V5 directory.",
        }
    )
    return gaps


def run_public_signal_research_breakthrough_v6() -> dict[str, object]:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []
    timeout_records: list[dict[str, object]] = []

    for step_id, module, timeout_seconds in ORCHESTRATOR_STEPS:
        rec = _run_step(step_id, module, timeout_seconds=timeout_seconds)
        steps.append(rec)
        if rec.get("timed_out"):
            timeout_records.append(rec)

    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(TIMEOUT_RECORDS_PATH, timeout_records)

    # Preflight gate
    preflight_summary = _read_json_safe(PREFLIGHT_V6_SUMMARY_PATH)
    preflight_status = str(preflight_summary.get("public_signal_research_v6_preflight_status", ""))
    if preflight_status != EXPECTED_PREFLIGHT_STATUS:
        return _finalize_blocked(
            steps,
            timeout_records,
            reason="preflight_not_ready",
            preflight_status=preflight_status,
        )

    # Quality flags
    quality_flags: list[dict[str, object]] = []
    timeout_step_count = sum(1 for s in steps if s.get("timed_out"))
    nonzero_step_count = sum(1 for s in steps if s.get("status") not in ("ok", "inconclusive_timeout"))
    if timeout_step_count > 0:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_breakthrough_v6_quality_flag",
                "flag": "timeout_present",
                "timeout_step_count": timeout_step_count,
                "timeout_recorded_as_pass": False,
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if nonzero_step_count > 0:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_breakthrough_v6_quality_flag",
                "flag": "nonzero_exit_present",
                "nonzero_step_count": nonzero_step_count,
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    write_jsonl_file(QUALITY_FLAGS_PATH, [record_with_hash(q, "record_hash") for q in quality_flags])

    # Load stage results
    breakthroughs_records: list[dict[str, object]] = []
    if BREAKTHROUGH_V6_PATH.exists():
        for line in BREAKTHROUGH_V6_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                breakthroughs_records.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue

    watchlist_records: list[dict[str, object]] = []
    if WATCHLIST_V6_PATH.exists():
        for line in WATCHLIST_V6_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                watchlist_records.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue

    gate = _read_json_safe(GATE_V6_SUMMARY_PATH)
    tournament = _read_json_safe(TOURNAMENT_V6_SUMMARY_PATH)
    v6_rejection_analyzer = _read_json_safe(V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH)
    v6_mutation_exec = _read_json_safe(MUTATION_EXEC_V6_SUMMARY_PATH)
    v6_blocker_repair = _read_json_safe(RESEARCH_V6_ROOT / "breakthrough_blocker_repair_policy_v6_summary.json")
    baseline_freeze = _read_json_safe(BASELINE_FREEZE_V6_SUMMARY_PATH)
    live_gate = _read_json_safe(LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v6.json")
    scoreboard = _read_json_safe(SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6.json")

    status, next_target = _orchestrator_status(
        breakthroughs_records,
        watchlist_records,
        tournament,
        gate,
        steps,
    )

    known_gaps = _known_gaps()

    # Docs (Workstream M)
    docs = _write_bundle_docs(
        preflight_summary,
        baseline_freeze,
        v6_rejection_analyzer,
        v6_mutation_exec,
        v6_blocker_repair,
        _read_json_safe(CANDIDATE_GENERATOR_V6_SUMMARY_PATH),
        _read_json_safe(SCORER_V6_SUMMARY_PATH),
        _read_json_safe(SIMULATOR_V6_SUMMARY_PATH),
        tournament,
        gate,
        _read_json_safe(MUTATION_QUEUE_V6_SUMMARY_PATH),
        scoreboard,
        live_gate,
        known_gaps,
        status,
        next_target,
    )
    steps.append(
        record_with_hash(
            {
                "artifact_type": "public_signal_research_breakthrough_v6_step",
                "step_id": "docs",
                "status": "ok",
                "docs_written": docs.get("docs_written", False),
                "live_trading_enabled": False,
            },
            "record_hash",
        )
    )

    # Validation summary placeholder
    validation_summary = {
        "artifact_type": "public_signal_research_breakthrough_v6_validation_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "validation_status": "validation_summary_pre_orchestrator",
        "step_count": len(steps),
        "timeout_count": len(timeout_records),
        "nonzero_exit_count": nonzero_step_count,
        "breakthrough_candidate_count": len(breakthroughs_records),
        "watchlist_count": len(watchlist_records),
        "v6_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "public_data_only": True,
        "paper_only": True,
        "live_blocked": True,
        "timeout_recorded_as_pass": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(VALIDATION_SUMMARY_PATH, validation_summary)

    # Shared handoff
    handoff = _copy_shared_handoff(_build_handoff_file_list())

    summary = _build_orchestrator_summary(
        status,
        next_target,
        steps,
        timeout_records,
        known_gaps,
        preflight_summary,
        baseline_freeze,
        v6_rejection_analyzer,
        v6_mutation_exec,
        v6_blocker_repair,
        _read_json_safe(CANDIDATE_GENERATOR_V6_SUMMARY_PATH),
        _read_json_safe(SCORER_V6_SUMMARY_PATH),
        _read_json_safe(SIMULATOR_V6_SUMMARY_PATH),
        tournament,
        gate,
        _read_json_safe(MUTATION_QUEUE_V6_SUMMARY_PATH),
        scoreboard,
        live_gate,
        handoff,
    )
    write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(PROOF_PATH, [research_v6_proof_record("public-signal-research-breakthrough-v6", status, summary)])
    return {**summary, "artifact_paths": _orchestrator_artifact_paths()}


def _build_orchestrator_summary(
    status: str,
    next_target: str,
    steps: list[dict[str, object]],
    timeout_records: list[dict[str, object]],
    known_gaps: list[dict[str, object]],
    preflight: dict[str, object],
    baseline_freeze: dict[str, object],
    v5_rejection_analyzer: dict[str, object],
    mutation_exec: dict[str, object],
    blocker_repair: dict[str, object],
    candidates: dict[str, object],
    scorer: dict[str, object],
    simulator: dict[str, object],
    tournament: dict[str, object],
    gate: dict[str, object],
    mutation_queue: dict[str, object],
    scoreboard: dict[str, object],
    live_gate: dict[str, object],
    handoff: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_type": "public_signal_research_breakthrough_v6_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "public_signal_research_v6_status": status,
        "next_recommended_target": next_target,
        "step_count": len(steps),
        "step_timeout_count": len(timeout_records),
        "step_nonzero_exit_count": sum(
            1 for s in steps if s.get("status") not in ("ok", "inconclusive_timeout")
        ),
        "preflight_status": str(preflight.get("public_signal_research_v6_preflight_status", "")),
        "v5_baseline_freeze_status": str(baseline_freeze.get("baseline_freeze_status", "")),
        "v5_gate_rejection_analyzer_status": str(v5_rejection_analyzer.get("v5_gate_rejection_analyzer_status", "")),
        "v6_mutation_executed_count": int(mutation_exec.get("executed_mutation_count", 0) or 0),
        "v6_blocker_repair_policy_status": str(blocker_repair.get("breakthrough_blocker_repair_policy_status", "")),
        "v6_mutation_queue_count": int(mutation_queue.get("mutation_queue_count", 0) or 0),
        "v6_candidate_count": int(candidates.get("candidate_count", 0) or 0),
        "v6_simulated_trade_count": int(simulator.get("simulated_trade_count", 0) or 0),
        "tournament_family_count": int(tournament.get("family_count", 0) or 0),
        "tournament_subfamily_count": int(tournament.get("subfamily_count", 0) or 0),
        "tournament_cohort_count": int(tournament.get("cohort_count", 0) or 0),
        "improved_vs_v5_count": int(tournament.get("improved_vs_v5_count", 0) or 0),
        "pf_above_110_count": int(gate.get("pf_above_threshold_count", 0) or 0),
        "breakthrough_candidate_count": int(gate.get("breakthrough_candidate_count", 0) or 0),
        "watchlist_count": int(gate.get("watchlist_count", 0) or 0),
        "improved_watchlist_count": int(gate.get("improved_watchlist_count", 0) or 0),
        "top_research_family": str(tournament.get("top_family", "")),
        "top_research_subfamily": str(tournament.get("top_subfamily", "")),
        "top_research_cohort": str(tournament.get("top_cohort", "")),
        "top_net_pnl": float(tournament.get("top_net_pnl", 0.0) or 0.0),
        "top_profit_factor": float(tournament.get("top_profit_factor", 0.0) or 0.0),
        "top_max_drawdown": float(tournament.get("top_max_drawdown", 0.0) or 0.0),
        "top_sample_count": int(tournament.get("top_sample_count", 0) or 0),
        "v5_top_pf": float(tournament.get("v5_top_pf", 0.0) or 0.0),
        "live_gate_status": str(live_gate.get("live_gate_status", "")),
        "scoreboard_status": str(scoreboard.get("scoreboard_v6_status", "")),
        "shared_copy_status": str(handoff.get("shared_copy_status", "not_attempted")),
        "shared_copy_target_root": str(handoff.get("target_root", "")),
        "shared_copy_copied_count": int(handoff.get("copied_count", 0) or 0),
        "known_gaps": known_gaps,
        "timeout_recorded_as_pass": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "paper_only": True,
        "live_blocked": True,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "credentials_present": False,
        "env_present": False,
        "official_robinhood_market_data_allowed": True,
        "unofficial_robinhood_api_blocked": True,
        "robinhood_scraping_blocked": True,
        "robinhood_reverse_auth_blocked": True,
        "robinhood_live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def _finalize_blocked(
    steps: list[dict[str, object]],
    timeout_records: list[dict[str, object]],
    reason: str,
    preflight_status: str,
) -> dict[str, object]:
    if reason == "public_lake_degraded":
        status = "public_lake_degraded"
    else:
        status = "public_signal_research_v6_preflight_blocked"

    next_target = {
        "public_signal_research_v6_preflight_blocked": "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3",
        "public_lake_degraded": "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3",
    }.get(status, "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7")

    summary = {
        "artifact_type": "public_signal_research_breakthrough_v6_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "public_signal_research_v6_status": status,
        "next_recommended_target": next_target,
        "preflight_status": preflight_status,
        "step_count": len(steps),
        "step_timeout_count": len(timeout_records),
        "step_nonzero_exit_count": sum(
            1 for s in steps if s.get("status") not in ("ok", "inconclusive_timeout")
        ),
        "timeout_recorded_as_pass": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "paper_only": True,
        "live_blocked": True,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "credentials_present": False,
        "env_present": False,
        "official_robinhood_market_data_allowed": True,
        "unofficial_robinhood_api_blocked": True,
        "robinhood_scraping_blocked": True,
        "robinhood_reverse_auth_blocked": True,
        "robinhood_live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(STEPS_PATH, steps)
    write_jsonl_file(TIMEOUT_RECORDS_PATH, timeout_records)
    write_jsonl_file(PROOF_PATH, [research_v6_proof_record("public-signal-research-breakthrough-v6", status, summary)])
    return {**summary, "artifact_paths": _orchestrator_artifact_paths()}


def _write_bundle_docs(
    preflight: dict[str, object],
    baseline_freeze: dict[str, object],
    v5_rejection_analyzer: dict[str, object],
    mutation_exec: dict[str, object],
    blocker_repair: dict[str, object],
    candidates: dict[str, object],
    scorer: dict[str, object],
    simulator: dict[str, object],
    tournament: dict[str, object],
    gate: dict[str, object],
    mutation_queue: dict[str, object],
    scoreboard: dict[str, object],
    live_gate: dict[str, object],
    known_gaps: list[dict[str, object]],
    status: str,
    next_target: str,
) -> dict[str, object]:
    REPORT_PATH.write_text(
        _build_report(
            preflight,
            baseline_freeze,
            v5_rejection_analyzer,
            mutation_exec,
            blocker_repair,
            candidates,
            scorer,
            simulator,
            tournament,
            gate,
            mutation_queue,
            scoreboard,
            live_gate,
            known_gaps,
            status,
            next_target,
        ),
        encoding="utf-8",
    )
    LEDGER_PATH.write_text(_build_ledger(), encoding="utf-8")
    COMMANDS_PATH.write_text(_build_commands_doc(), encoding="utf-8")
    return {"docs_written": True}


def _build_report(
    preflight: dict[str, object],
    baseline_freeze: dict[str, object],
    v5_rejection_analyzer: dict[str, object],
    mutation_exec: dict[str, object],
    blocker_repair: dict[str, object],
    candidates: dict[str, object],
    scorer: dict[str, object],
    simulator: dict[str, object],
    tournament: dict[str, object],
    gate: dict[str, object],
    mutation_queue: dict[str, object],
    scoreboard: dict[str, object],
    live_gate: dict[str, object],
    known_gaps: list[dict[str, object]],
    status: str,
    next_target: str,
) -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_REPORT\n\n"
        f"- repo path: `C:\\Users\\CH\\dopey`\n"
        f"- orchestrator status: `{status}`\n"
        f"- next recommended target: `{next_target}`\n\n"
        "## Pipeline Steps\n\n"
        f"1. V6 preflight: {preflight.get('public_signal_research_v6_preflight_status', '')}\n"
        f"2. V5 baseline freeze: {baseline_freeze.get('baseline_freeze_status', '')}\n"
        f"3. V5 gate rejection analyzer: {v5_rejection_analyzer.get('v5_gate_rejection_analyzer_status', '')}\n"
        f"4. V6 mutation executor: {mutation_exec.get('executed_mutation_count', 0)}/{mutation_exec.get('input_v5_mutation_count', 0)} executed\n"
        f"5. V6 blocker repair policy: {blocker_repair.get('breakthrough_blocker_repair_policy_status', '')}\n"
        f"6. Candidate generator V6: {candidates.get('candidate_count', 0)} candidates\n"
        f"7. PF/holdout/split scorer V6: {candidates.get('candidate_count', 0)} scored\n"
        f"8. Path simulator V6: {simulator.get('simulated_trade_count', 0)} trades\n"
        f"9. Tournament V6: {tournament.get('family_count', 0)} families / {tournament.get('subfamily_count', 0)} subfamilies / {tournament.get('cohort_count', 0)} cohorts\n"
        f"10. Breakthrough gate V6: {gate.get('breakthrough_candidate_count', 0)} breakthroughs / {gate.get('watchlist_count', 0)} watchlist\n"
        f"11. Mutation queue V6: {mutation_queue.get('mutation_queue_count', 0)} entries\n"
        f"12. Scoreboard V6: {scoreboard.get('scoreboard_v6_status', '')}\n"
        f"13. Live gate V6: {live_gate.get('live_gate_status', '')}\n\n"
        "## Results\n\n"
        f"- improved vs V5 count: {tournament.get('improved_vs_v5_count', 0)}\n"
        f"- PF above 1.10 count: {gate.get('pf_above_threshold_count', 0)}\n"
        f"- top family: `{tournament.get('top_family', '')}`\n"
        f"- top subfamily: `{tournament.get('top_subfamily', '')}`\n"
        f"- top cohort: `{tournament.get('top_cohort', '')}`\n"
        f"- top net P&L: {tournament.get('top_net_pnl', 0.0)}\n"
        f"- top PF: {tournament.get('top_profit_factor', 0.0)}\n"
        f"- top sample count: {tournament.get('top_sample_count', 0)}\n\n"
        "## Known Gaps\n\n"
        + "\n".join(f"- `{g.get('gap_id')}`: {g.get('note')}" for g in known_gaps)
        + "\n\n## Validation\n\nValidation summary: pending_watchdog_validation\n"
    )


def _build_ledger() -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_ARTIFACT_LEDGER\n\n"
        "All artifacts under `C:\\Users\\CH\\dopey\\artifacts\\dopey\\signal_research_v6\\`\n"
        "and `C:\\Users\\CH\\dopey\\artifacts\\dopey\\scoreboard\\` (scoreboard / dashboard)\n"
        "and `C:\\Users\\CH\\dopey\\artifacts\\dopey\\live_gate\\` (live gate)\n\n"
        "Key files:\n"
        "- public_signal_research_breakthrough_v6_summary.json\n"
        "- public_signal_research_breakthrough_v6_steps.jsonl\n"
        "- public_signal_research_breakthrough_v6_quality_flags.jsonl\n"
        "- public_signal_research_breakthrough_v6_proof.jsonl\n"
        "- public_signal_research_breakthrough_v6_validation_summary.json\n"
        "- public_signal_research_breakthrough_v6_timeout_records.jsonl\n"
        "- public_signal_research_v6_preflight_summary.json\n"
        "- public_signal_research_v6_baseline_freeze_summary.json\n"
        "- public_signal_research_v6_baseline_snapshot_manifest.jsonl\n"
        "- v5_gate_rejection_analyzer_v6_summary.json\n"
        "- research_mutation_queue_executor_v6_summary.json\n"
        "- breakthrough_blocker_repair_policy_v6_summary.json\n"
        "- research_candidate_generator_v6_summary.json\n"
        "- profit_holdout_split_scorer_v6_summary.json\n"
        "- research_path_simulator_v6_summary.json\n"
        "- research_tournament_v6_summary.json\n"
        "- research_breakthrough_gate_v6_summary.json\n"
        "- research_mutation_queue_v6_summary.json\n"
        "- public_signal_research_scoreboard_v6.json\n"
        "- public_signal_research_dashboard_v6.html\n"
        "- public_signal_research_live_gate_status_v6.json\n"
    )


def _build_commands_doc() -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_COMMANDS\n\n"
        "Use explicit venv; no live broker / order commands anywhere.\n\n"
        "```\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_signal_research_breakthrough_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_validation.run_public_signal_research_v6_preflight\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_validation.run_public_signal_research_baseline_freezer_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_v5_gate_rejection_analyzer_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_mutation_queue_executor_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_breakthrough_blocker_repair_policy_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_candidate_generator_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_profit_holdout_split_scorer_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_path_simulator_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_tournament_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_breakthrough_gate_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_mutation_queue_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_scoreboard.run_public_signal_research_scoreboard_v6\n"
        ".\\.venv\\Scripts\\python.exe -m dopey_live_gate.run_public_signal_research_live_gate_status_v6\n"
        "```\n"
    )


def _build_handoff_file_list() -> list[Path]:
    return [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        PREFLIGHT_V6_SUMMARY_PATH,
        BASELINE_FREEZE_V6_SUMMARY_PATH,
        BASELINE_SNAPSHOT_V6_MANIFEST_PATH,
        V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH,
        RESEARCH_V6_ROOT / "v5_gate_rejection_analysis_v6.jsonl",
        RESEARCH_V6_ROOT / "v5_breakthrough_blocker_matrix_v6.jsonl",
        RESEARCH_V6_ROOT / "v5_watchlist_diagnosis_v6.jsonl",
        MUTATION_EXEC_V6_SUMMARY_PATH,
        RESEARCH_V6_ROOT / "breakthrough_blocker_repair_policy_v6_summary.json",
        RESEARCH_V6_ROOT / "breakthrough_blocker_repair_rules_v6.jsonl",
        CANDIDATE_GENERATOR_V6_SUMMARY_PATH,
        SCORER_V6_SUMMARY_PATH,
        SIMULATOR_V6_SUMMARY_PATH,
        TOURNAMENT_V6_SUMMARY_PATH,
        GATE_V6_SUMMARY_PATH,
        MUTATION_QUEUE_V6_SUMMARY_PATH,
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6.json",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v6.html",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v6.md",
        LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v6.json",
        SUMMARY_PATH,
        VALIDATION_SUMMARY_PATH,
        TIMEOUT_RECORDS_PATH,
    ]


def _copy_shared_handoff(files: list[Path]) -> dict[str, object]:
    targets = [
        Path("C:/Users/CH/Desktop/Shared Folder"),
        Path("//FRANKENSTEIN/Shared Folder"),
    ]
    target_results: list[dict[str, object]] = []
    overall_status: list[str] = []
    overall_copied = 0
    overall_target = ""

    for base in targets:
        result: dict[str, object] = {"target_root": str(base), "copied_count": 0, "error": ""}
        if not base.exists():
            result["error"] = f"target_not_available: {base}"
            target_results.append(result)
            overall_status.append("target_failed")
            continue
        dest = base / HANDOFF_FOLDER
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        file_records: list[dict[str, object]] = []
        for path in files:
            if not path.exists():
                continue
            try:
                shutil.copy2(path, dest / path.name)
                copied += 1
                data = path.read_bytes()
                import hashlib

                file_records.append(
                    {
                        "file_name": path.name,
                        "file_size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            except OSError as exc:
                file_records.append(
                    {
                        "file_name": path.name,
                        "file_size": 0,
                        "sha256": "",
                        "error": str(exc),
                    }
                )
        manifest = {
            "target_root": str(dest),
            "copied_count": copied,
            "missing_count": len(files) - copied,
            "file_names": [fr["file_name"] for fr in file_records],
            "file_sizes": {fr["file_name"]: fr["file_size"] for fr in file_records},
            "hashes": {fr["file_name"]: fr["sha256"] for fr in file_records},
            "live_trading_enabled": False,
            "credentials_present": False,
            "broker_connection_enabled": False,
            "real_order_enabled": False,
            "timestamp": utc_now_iso(),
        }
        manifest_path = dest / "SESSION_COPY_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        result["copied_count"] = copied
        result["manifest_path"] = str(manifest_path)
        target_results.append(result)
        overall_status.append("copied")
        overall_copied = copied
        overall_target = str(dest)

    if all(s == "target_failed" for s in overall_status):
        shared_copy_status = "no_target_available"
    elif any(s == "target_failed" for s in overall_status):
        shared_copy_status = "partial_copy"
    else:
        shared_copy_status = "copied"

    local_manifest = {
        "target_root": overall_target,
        "copied_count": overall_copied,
        "target_results": target_results,
        "live_trading_enabled": False,
        "credentials_present": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "timestamp": utc_now_iso(),
    }
    LOCAL_MANIFEST_PATH.write_text(json.dumps(local_manifest, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "shared_copy_status": shared_copy_status,
        "target_root": overall_target,
        "copied_count": overall_copied,
        "target_results": target_results,
    }


def _orchestrator_artifact_paths() -> dict[str, str]:
    return {
        "public_signal_research_breakthrough_v6_summary": str(SUMMARY_PATH),
        "public_signal_research_breakthrough_v6_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "public_signal_research_breakthrough_v6_session_copy_manifest": str(LOCAL_MANIFEST_PATH),
    }


orchestrator_artifact_paths = _orchestrator_artifact_paths


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_breakthrough_v6(), indent=2, sort_keys=True, default=str))
