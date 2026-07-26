"""Full orchestrator for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7.

Sequence (per spec):
1. dopey_validation.run_public_signal_research_v7_preflight
2. dopey_validation.run_public_signal_research_baseline_freezer_v7
3. dopey_signal_research.run_no_trade_contribution_audit_v7
4. dopey_signal_research.run_v6_watchlist_diagnosis_v7
5. dopey_signal_research.run_research_mutation_queue_executor_v7
6. dopey_signal_research.run_trade_active_repair_policy_v7
7. dopey_signal_research.run_research_candidate_generator_v7
8. dopey_signal_research.run_profit_holdout_split_scorer_v7
9. dopey_signal_research.run_research_path_simulator_v7
10. dopey_signal_research.run_research_tournament_v7
11. dopey_signal_research.run_research_breakthrough_gate_v7
12. dopey_signal_research.run_research_mutation_queue_v7
13. dopey_scoreboard.run_public_signal_research_scoreboard_v7
14. dopey_live_gate.run_public_signal_research_live_gate_status_v7

Status logic:
- honest trade-active breakthroughs found -> research_breakthrough_candidates_found_live_gate_locked
  next DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1
- blockers improved but no breakthrough -> watchlist_blockers_improved_requires_v8
  next DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V8
- no improvement -> no_further_repair_signal_feature_expansion_required
  next DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2
- public lake degraded -> DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3

Safety invariants:
- MIN_BREAKTHROUGH_PF is never lowered (hard floor 1.10).
- Live trading remains disabled; every record carries Robinhood policy fields
  and live_safety_fields.
- No-trade-only breakthroughs are blocked at the gate stage.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    BASELINE_FREEZE_V7_SUMMARY_PATH,
    BASELINE_SNAPSHOT_V7_MANIFEST_PATH,
    BREAKTHROUGH_V7_PATH,
    CANDIDATE_GENERATOR_V7_SUMMARY_PATH,
    GATE_V7_SUMMARY_PATH,
    LIVE_GATE_ROOT,
    MIN_BREAKTHROUGH_PF,
    MUTATION_EXEC_V7_SUMMARY_PATH,
    MUTATION_QUEUE_V7_SUMMARY_PATH,
    NO_TRADE_AUDIT_V7_SUMMARY_PATH,
    PREFLIGHT_V7_SUMMARY_PATH,
    RESEARCH_V7_ROOT,
    RESEARCH_V7_VERSION,
    SCOREBOARD_ROOT,
    SCORER_V7_SUMMARY_PATH,
    SIMULATOR_V7_SUMMARY_PATH,
    TOURNAMENT_V7_SUMMARY_PATH,
    TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH,
    V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH,
    WATCHLIST_V7_PATH,
    research_v7_proof_record,
    utc_now_iso,
)
from dopey_wealth_engine.common import REPO_ROOT
from dopey_core.repo_paths import REPORTS_DIR


__all__ = ["run_public_signal_research_breakthrough_v7"]


SUMMARY_PATH = RESEARCH_V7_ROOT / "public_signal_research_breakthrough_v7_summary.json"
STEPS_PATH = RESEARCH_V7_ROOT / "public_signal_research_breakthrough_v7_steps.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_V7_ROOT / "public_signal_research_breakthrough_v7_quality_flags.jsonl"
PROOF_PATH = RESEARCH_V7_ROOT / "public_signal_research_breakthrough_v7_proof.jsonl"
VALIDATION_SUMMARY_PATH = RESEARCH_V7_ROOT / "public_signal_research_breakthrough_v7_validation_summary.json"
TIMEOUT_RECORDS_PATH = RESEARCH_V7_ROOT / "public_signal_research_breakthrough_v7_timeout_records.jsonl"
LOCAL_MANIFEST_PATH = RESEARCH_V7_ROOT / "public_signal_research_breakthrough_v7_session_copy_manifest.json"

REPORT_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_COMMANDS.md"
HANDOFF_FOLDER = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7"

EXPECTED_PREFLIGHT_STATUS = "ready_for_trade_active_breakthrough_repair"


ORCHESTRATOR_STEPS: tuple[tuple[str, str, int], ...] = (
    ("v7_preflight", "dopey_validation.run_public_signal_research_v7_preflight", 240),
    ("v6_baseline_freeze", "dopey_validation.run_public_signal_research_baseline_freezer_v7", 240),
    ("v7_no_trade_contribution_audit", "dopey_signal_research.run_no_trade_contribution_audit_v7", 240),
    ("v7_v6_watchlist_diagnosis", "dopey_signal_research.run_v6_watchlist_diagnosis_v7", 240),
    ("v7_mutation_executor", "dopey_signal_research.run_research_mutation_queue_executor_v7", 240),
    ("v7_trade_active_repair_policy", "dopey_signal_research.run_trade_active_repair_policy_v7", 240),
    ("v7_candidate_generator", "dopey_signal_research.run_research_candidate_generator_v7", 300),
    ("v7_scorer", "dopey_signal_research.run_profit_holdout_split_scorer_v7", 240),
    ("v7_path_simulator", "dopey_signal_research.run_research_path_simulator_v7", 300),
    ("v7_tournament", "dopey_signal_research.run_research_tournament_v7", 240),
    ("v7_breakthrough_gate", "dopey_signal_research.run_research_breakthrough_gate_v7", 240),
    ("v7_mutation_queue", "dopey_signal_research.run_research_mutation_queue_v7", 240),
    ("v7_scoreboard", "dopey_scoreboard.run_public_signal_research_scoreboard_v7", 240),
    ("v7_live_gate", "dopey_live_gate.run_public_signal_research_live_gate_status_v7", 240),
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
    base_record: dict[str, object] = {
        "artifact_type": "public_signal_research_breakthrough_v7_step",
        "step_id": step_id,
        "module": module,
        "started_at": started,
        "live_trading_enabled": False,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        rec = {
            **base_record,
            "finished_at": utc_now_iso(),
            "exit_code": proc.returncode,
            "timed_out": False,
            "status": "ok" if proc.returncode == 0 else "nonzero_exit",
            "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
            "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
        }
    except subprocess.TimeoutExpired as exc:
        rec = {
            **base_record,
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
        }
    except Exception as exc:  # noqa: BLE001
        rec = {
            **base_record,
            "finished_at": utc_now_iso(),
            "exit_code": None,
            "timed_out": False,
            "status": "runner_error",
            "error": str(exc),
            "traceback": traceback.format_exc()[-500:],
        }
    return record_with_hash(rec, "record_hash")


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
    trade_active_pf_above = int(gate.get("trade_active_pf_above_threshold_count", 0) or 0)
    improved_vs_v6 = int(tournament.get("improved_vs_v6_count", 0) or 0)
    watchlist_count = len(watchlist)

    # Only honest trade-active breakthroughs count; no-trade-only are blocked upstream.
    honest_breakthroughs = [
        b for b in breakthroughs
        if bool(b.get("trade_active_breakthrough", True))
        and not bool(b.get("no_trade_only", False))
    ]

    if honest_breakthroughs:
        return (
            "research_breakthrough_candidates_found_live_gate_locked",
            "DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1",
        )

    if pf_above > 0 or trade_active_pf_above > 0 or improved_vs_v6 > 0 or watchlist_count > 0:
        return (
            "watchlist_blockers_improved_requires_v8",
            "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V8",
        )

    return (
        "no_further_repair_signal_feature_expansion_required",
        "DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2",
    )


def _known_gaps() -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    gaps.append(
        {
            "gap_id": "v7_no_trade_dominance_partial_conversion",
            "status": "acknowledged",
            "timeout_recorded_as_pass": False,
            "note": "V7 converts no-trade-dominant watchlist candidates into trade-active candidates; residual low trade-active sample counts may still block promotion.",
        }
    )
    gaps.append(
        {
            "gap_id": "v7_expensive_lane_timeout_risk",
            "status": "acknowledged",
            "timeout_recorded_as_pass": False,
            "note": "V7 candidate generator and path simulator have larger targets; partial timeouts are recorded honestly and do not count as pass.",
        }
    )
    gaps.append(
        {
            "gap_id": "v6_baseline_snapshot_gap_acknowledged",
            "status": "acknowledged",
            "timeout_recorded_as_pass": False,
            "note": "V6 baseline snapshot covers immutable summary/dashboard/doc sources; supporting JSONL records remain in live V6 directory.",
        }
    )
    return gaps


def run_public_signal_research_breakthrough_v7() -> dict[str, object]:
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
    preflight_step = next((s for s in steps if s.get("step_id") == "v7_preflight"), {})
    preflight_summary = _read_json_safe(PREFLIGHT_V7_SUMMARY_PATH)
    preflight_status = str(preflight_summary.get("public_signal_research_v7_preflight_status", ""))
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
            record_with_hash(
                {
                    "artifact_type": "public_signal_research_breakthrough_v7_quality_flag",
                    "flag": "timeout_present",
                    "timeout_step_count": timeout_step_count,
                    "timeout_recorded_as_pass": False,
                    "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
                    "thresholds_lowered": False,
                    "live_trading_enabled": False,
                    **live_safety_fields(),
                    **robinhood_policy_fields(),
                },
                "record_hash",
            )
        )
    if nonzero_step_count > 0:
        quality_flags.append(
            record_with_hash(
                {
                    "artifact_type": "public_signal_research_breakthrough_v7_quality_flag",
                    "flag": "nonzero_exit_present",
                    "nonzero_step_count": nonzero_step_count,
                    "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
                    "thresholds_lowered": False,
                    "live_trading_enabled": False,
                    **live_safety_fields(),
                    **robinhood_policy_fields(),
                },
                "record_hash",
            )
        )
    if not quality_flags:
        quality_flags.append(
            record_with_hash(
                {
                    "artifact_type": "public_signal_research_breakthrough_v7_quality_flag",
                    "flag": "no_quality_flags",
                    "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
                    "thresholds_lowered": False,
                    "live_trading_enabled": False,
                    **live_safety_fields(),
                    **robinhood_policy_fields(),
                },
                "record_hash",
            )
        )
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)

    # Load stage results
    breakthroughs_records = _read_jsonl_safe(BREAKTHROUGH_V7_PATH)
    watchlist_records = _read_jsonl_safe(WATCHLIST_V7_PATH)

    gate = _read_json_safe(GATE_V7_SUMMARY_PATH)
    tournament = _read_json_safe(TOURNAMENT_V7_SUMMARY_PATH)
    no_trade_audit = _read_json_safe(NO_TRADE_AUDIT_V7_SUMMARY_PATH)
    v6_watchlist_diagnosis = _read_json_safe(V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH)
    v7_mutation_exec = _read_json_safe(MUTATION_EXEC_V7_SUMMARY_PATH)
    v7_trade_active_repair = _read_json_safe(TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH)
    baseline_freeze = _read_json_safe(BASELINE_FREEZE_V7_SUMMARY_PATH)
    live_gate = _read_json_safe(LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v7.json")
    scoreboard = _read_json_safe(SCOREBOARD_ROOT / "public_signal_research_scoreboard_v7.json")

    status, next_target = _orchestrator_status(
        breakthroughs_records,
        watchlist_records,
        tournament,
        gate,
        steps,
    )

    known_gaps = _known_gaps()

    # Docs (Workstream N)
    docs = _write_bundle_docs(
        preflight_summary,
        baseline_freeze,
        no_trade_audit,
        v6_watchlist_diagnosis,
        v7_mutation_exec,
        v7_trade_active_repair,
        _read_json_safe(CANDIDATE_GENERATOR_V7_SUMMARY_PATH),
        _read_json_safe(SCORER_V7_SUMMARY_PATH),
        _read_json_safe(SIMULATOR_V7_SUMMARY_PATH),
        tournament,
        gate,
        _read_json_safe(MUTATION_QUEUE_V7_SUMMARY_PATH),
        scoreboard,
        live_gate,
        known_gaps,
        status,
        next_target,
    )
    steps.append(
        record_with_hash(
            {
                "artifact_type": "public_signal_research_breakthrough_v7_step",
                "step_id": "docs",
                "status": "ok",
                "docs_written": docs.get("docs_written", False),
                "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
                "thresholds_lowered": False,
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            },
            "record_hash",
        )
    )
    # Rewrite steps now that docs step was appended.
    write_jsonl_file(STEPS_PATH, steps)

    # Validation summary
    validation_summary = {
        "artifact_type": "public_signal_research_breakthrough_v7_validation_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "validation_status": "validation_summary_pre_orchestrator",
        "step_count": len(steps),
        "timeout_count": len(timeout_records),
        "nonzero_exit_count": nonzero_step_count,
        "breakthrough_candidate_count": len(breakthroughs_records),
        "honest_trade_active_breakthrough_count": sum(
            1 for b in breakthroughs_records
            if bool(b.get("trade_active_breakthrough", True)) and not bool(b.get("no_trade_only", False))
        ),
        "watchlist_count": len(watchlist_records),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
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
        no_trade_audit,
        v6_watchlist_diagnosis,
        v7_mutation_exec,
        v7_trade_active_repair,
        _read_json_safe(CANDIDATE_GENERATOR_V7_SUMMARY_PATH),
        _read_json_safe(SCORER_V7_SUMMARY_PATH),
        _read_json_safe(SIMULATOR_V7_SUMMARY_PATH),
        tournament,
        gate,
        _read_json_safe(MUTATION_QUEUE_V7_SUMMARY_PATH),
        scoreboard,
        live_gate,
        handoff,
    )
    write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(
        PROOF_PATH,
        [research_v7_proof_record("public-signal-research-breakthrough-v7", status, summary)],
    )
    return {**summary, "artifact_paths": _orchestrator_artifact_paths()}


def _read_jsonl_safe(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                records.append(parsed)
        except Exception:  # noqa: BLE001
            continue
    return records


def _build_orchestrator_summary(
    status: str,
    next_target: str,
    steps: list[dict[str, object]],
    timeout_records: list[dict[str, object]],
    known_gaps: list[dict[str, object]],
    preflight: dict[str, object],
    baseline_freeze: dict[str, object],
    no_trade_audit: dict[str, object],
    v6_watchlist_diagnosis: dict[str, object],
    mutation_exec: dict[str, object],
    trade_active_repair: dict[str, object],
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
        "artifact_type": "public_signal_research_breakthrough_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "public_signal_research_v7_status": status,
        "next_recommended_target": next_target,
        "step_count": len(steps),
        "step_timeout_count": len(timeout_records),
        "step_nonzero_exit_count": sum(
            1 for s in steps if s.get("status") not in ("ok", "inconclusive_timeout")
        ),
        "preflight_status": str(preflight.get("public_signal_research_v7_preflight_status", "")),
        "v6_baseline_freeze_status": str(baseline_freeze.get("baseline_freeze_status", "")),
        "no_trade_contribution_audit_status": str(no_trade_audit.get("no_trade_contribution_audit_status", "")),
        "v6_watchlist_diagnosis_status": str(v6_watchlist_diagnosis.get("v6_watchlist_diagnosis_v7_status", "")),
        "v7_mutation_executed_count": int(mutation_exec.get("executed_mutation_count", 0) or 0),
        "trade_active_repair_policy_status": str(trade_active_repair.get("trade_active_repair_policy_status", "")),
        "v7_mutation_queue_count": int(mutation_queue.get("mutation_queue_count", 0) or 0),
        "v7_candidate_count": int(candidates.get("candidate_count", 0) or 0),
        "trade_active_candidate_count": int(candidates.get("trade_active_count", 0) or 0),
        "no_trade_ratio": float(candidates.get("no_trade_ratio", 0.0) or 0.0),
        "v7_scored_count": int(scorer.get("scored_count", candidates.get("candidate_count", 0)) or 0),
        "v7_simulated_trade_count": int(simulator.get("simulated_trade_count", 0) or 0),
        "tournament_family_count": int(tournament.get("family_count", 0) or 0),
        "tournament_subfamily_count": int(tournament.get("subfamily_count", 0) or 0),
        "tournament_cohort_count": int(tournament.get("cohort_count", 0) or 0),
        "improved_vs_v6_count": int(tournament.get("improved_vs_v6_count", 0) or 0),
        "pf_above_110_count": int(gate.get("pf_above_threshold_count", 0) or 0),
        "trade_active_pf_above_110_count": int(tournament.get("trade_active_pf_above_110_count", 0) or 0),
        "breakthrough_candidate_count": int(gate.get("breakthrough_candidate_count", 0) or 0),
        "honest_trade_active_breakthrough_count": sum(
            1 for b in _read_jsonl_safe(BREAKTHROUGH_V7_PATH)
            if bool(b.get("trade_active_breakthrough", True)) and not bool(b.get("no_trade_only", False))
        ),
        "watchlist_count": int(gate.get("watchlist_count", 0) or 0),
        "improved_watchlist_count": int(gate.get("improved_watchlist_count", 0) or 0),
        "top_research_family": str(tournament.get("top_family", "")),
        "top_research_subfamily": str(tournament.get("top_subfamily", "")),
        "top_research_cohort": str(tournament.get("top_cohort", "")),
        "top_net_pnl": float(tournament.get("top_net_pnl", 0.0) or 0.0),
        "top_profit_factor": float(tournament.get("top_profit_factor", 0.0) or 0.0),
        "top_max_drawdown": float(tournament.get("top_max_drawdown", 0.0) or 0.0),
        "top_sample_count": int(tournament.get("top_sample_count", 0) or 0),
        "top_trade_active_profit_factor": float(tournament.get("top_trade_active_profit_factor", 0.0) or 0.0),
        "v6_top_pf": float(tournament.get("v6_top_pf", 0.0) or 0.0),
        "live_gate_status": str(live_gate.get("live_gate_status", "")),
        "scoreboard_status": str(scoreboard.get("scoreboard_v7_status", scoreboard.get("scoreboard_status", ""))),
        "shared_copy_status": str(handoff.get("shared_copy_status", "not_attempted")),
        "shared_copy_target_root": str(handoff.get("target_root", "")),
        "shared_copy_copied_count": int(handoff.get("copied_count", 0) or 0),
        "known_gaps": known_gaps,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
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
        status = "public_signal_research_v7_preflight_blocked"

    next_target = {
        "public_lake_degraded": "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3",
        "public_signal_research_v7_preflight_blocked": "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3",
    }.get(status, "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V8")

    nonzero_step_count = sum(
        1 for s in steps if s.get("status") not in ("ok", "inconclusive_timeout")
    )
    summary = {
        "artifact_type": "public_signal_research_breakthrough_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "public_signal_research_v7_status": status,
        "next_recommended_target": next_target,
        "preflight_status": preflight_status,
        "step_count": len(steps),
        "step_timeout_count": len(timeout_records),
        "step_nonzero_exit_count": nonzero_step_count,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
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
    write_jsonl_file(
        PROOF_PATH,
        [research_v7_proof_record("public-signal-research-breakthrough-v7", status, summary)],
    )

    # Write minimal docs even when blocked so downstream handoff has something.
    REPORT_PATH.write_text(
        f"# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_REPORT\n\n"
        f"- repo path: `C:\\Users\\CH\\dopey`\n"
        f"- orchestrator status: `{status}`\n"
        f"- next recommended target: `{next_target}`\n\n"
        f"Preflight was blocked (`{preflight_status}`). No V7 research stage was executed.\n",
        encoding="utf-8",
    )
    LEDGER_PATH.write_text(_build_ledger(), encoding="utf-8")
    COMMANDS_PATH.write_text(_build_commands_doc(), encoding="utf-8")

    return {**summary, "artifact_paths": _orchestrator_artifact_paths()}


def _write_bundle_docs(
    preflight: dict[str, object],
    baseline_freeze: dict[str, object],
    no_trade_audit: dict[str, object],
    v6_watchlist_diagnosis: dict[str, object],
    mutation_exec: dict[str, object],
    trade_active_repair: dict[str, object],
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
            no_trade_audit,
            v6_watchlist_diagnosis,
            mutation_exec,
            trade_active_repair,
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
    no_trade_audit: dict[str, object],
    v6_watchlist_diagnosis: dict[str, object],
    mutation_exec: dict[str, object],
    trade_active_repair: dict[str, object],
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
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_REPORT\n\n"
        f"- repo path: `C:\\Users\\CH\\dopey`\n"
        f"- orchestrator status: `{status}`\n"
        f"- next recommended target: `{next_target}`\n\n"
        "## Pipeline Steps\n\n"
        f"1. V7 preflight: {preflight.get('public_signal_research_v7_preflight_status', '')}\n"
        f"2. V6 baseline freeze: {baseline_freeze.get('baseline_freeze_status', '')}\n"
        f"3. No-trade contribution audit V7: {no_trade_audit.get('no_trade_contribution_audit_status', '')}\n"
        f"4. V6 watchlist diagnosis V7: {v6_watchlist_diagnosis.get('v6_watchlist_diagnosis_status', '')}\n"
        f"5. V6/V7 mutation executor: {mutation_exec.get('executed_mutation_count', 0)}/{mutation_exec.get('input_v6_mutation_count', 0)} executed\n"
        f"6. Trade-active repair policy V7: {trade_active_repair.get('trade_active_repair_policy_status', '')}\n"
        f"7. Candidate generator V7: {candidates.get('candidate_count', 0)} candidates\n"
        f"8. PF/holdout/split scorer V7: {scorer.get('scored_count', candidates.get('candidate_count', 0))} scored\n"
        f"9. Path simulator V7: {simulator.get('simulated_trade_count', 0)} trades\n"
        f"10. Tournament V7: {tournament.get('family_count', 0)} families / {tournament.get('subfamily_count', 0)} subfamilies / {tournament.get('cohort_count', 0)} cohorts\n"
        f"11. Breakthrough gate V7: {gate.get('breakthrough_candidate_count', 0)} breakthroughs / {gate.get('watchlist_count', 0)} watchlist\n"
        f"12. Mutation queue V7: {mutation_queue.get('mutation_queue_count', 0)} entries\n"
        f"13. Scoreboard V7: {scoreboard.get('scoreboard_v7_status', scoreboard.get('scoreboard_status', ''))}\n"
        f"14. Live gate V7: {live_gate.get('live_gate_status', '')}\n\n"
        "## Results\n\n"
        f"- improved vs V6 count: {tournament.get('improved_vs_v6_count', 0)}\n"
        f"- PF above 1.10 count: {gate.get('pf_above_threshold_count', 0)}\n"
        f"- trade-active PF above 1.10 count: {gate.get('trade_active_pf_above_threshold_count', 0)}\n"
        f"- no-trade-only blocked: {gate.get('no_trade_only_blocked_count', 0)}\n"
        f"- top family: `{tournament.get('top_family', '')}`\n"
        f"- top subfamily: `{tournament.get('top_subfamily', '')}`\n"
        f"- top cohort: `{tournament.get('top_cohort', '')}`\n"
        f"- top net P&L: {tournament.get('top_net_pnl', 0.0)}\n"
        f"- top PF: {tournament.get('top_profit_factor', 0.0)}\n"
        f"- top trade-active PF: {tournament.get('top_trade_active_profit_factor', 0.0)}\n"
        f"- top sample count: {tournament.get('top_sample_count', 0)}\n\n"
        "## Known Gaps\n\n"
        + "\n".join(f"- `{g.get('gap_id')}`: {g.get('note')}" for g in known_gaps)
        + "\n\n## Validation\n\nValidation summary: pending_watchdog_validation\n"
    )


def _build_ledger() -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_ARTIFACT_LEDGER\n\n"
        "All artifacts under `C:\\Users\\CH\\dopey\\artifacts\\dopey\\signal_research_v7\\`\n"
        "and `C:\\Users\\CH\\dopey\\artifacts\\dopey\\scoreboard\\` (scoreboard / dashboard)\n"
        "and `C:\\Users\\CH\\dopey\\artifacts\\dopey\\live_gate\\` (live gate)\n\n"
        "Key files:\n"
        "- public_signal_research_breakthrough_v7_summary.json\n"
        "- public_signal_research_breakthrough_v7_steps.jsonl\n"
        "- public_signal_research_breakthrough_v7_quality_flags.jsonl\n"
        "- public_signal_research_breakthrough_v7_proof.jsonl\n"
        "- public_signal_research_breakthrough_v7_validation_summary.json\n"
        "- public_signal_research_breakthrough_v7_timeout_records.jsonl\n"
        "- public_signal_research_v7_preflight_summary.json\n"
        "- public_signal_research_v7_baseline_freeze_summary.json\n"
        "- public_signal_research_v7_baseline_snapshot_manifest.jsonl\n"
        "- no_trade_contribution_audit_v7_summary.json\n"
        "- v6_watchlist_diagnosis_v7_summary.json\n"
        "- research_mutation_queue_executor_v7_summary.json\n"
        "- trade_active_repair_policy_v7_summary.json\n"
        "- research_candidate_generator_v7_summary.json\n"
        "- profit_holdout_split_scorer_v7_summary.json\n"
        "- research_path_simulator_v7_summary.json\n"
        "- research_tournament_v7_summary.json\n"
        "- research_breakthrough_gate_v7_summary.json\n"
        "- research_mutation_queue_v7_summary.json\n"
        "- public_signal_research_scoreboard_v7.json\n"
        "- public_signal_research_live_gate_status_v7.json\n"
    )


def _build_commands_doc() -> str:
    return (
        "# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_COMMANDS\n\n"
        "Use explicit venv; no live broker / order commands anywhere.\n\n"
        "```\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_autonomy.run_public_signal_research_breakthrough_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_validation.run_public_signal_research_v7_preflight\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_validation.run_public_signal_research_baseline_freezer_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_no_trade_contribution_audit_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_v6_watchlist_diagnosis_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_mutation_queue_executor_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_trade_active_repair_policy_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_candidate_generator_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_profit_holdout_split_scorer_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_path_simulator_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_tournament_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_breakthrough_gate_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_signal_research.run_research_mutation_queue_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_scoreboard.run_public_signal_research_scoreboard_v7\n"
        "C:\\Users\\CH\\dopey\\.venv\\Scripts\\python.exe -m dopey_live_gate.run_public_signal_research_live_gate_status_v7\n"
        "```\n"
    )


def _build_handoff_file_list() -> list[Path]:
    return [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        PREFLIGHT_V7_SUMMARY_PATH,
        BASELINE_FREEZE_V7_SUMMARY_PATH,
        BASELINE_SNAPSHOT_V7_MANIFEST_PATH,
        NO_TRADE_AUDIT_V7_SUMMARY_PATH,
        RESEARCH_V7_ROOT / "no_trade_contribution_records_v7.jsonl",
        RESEARCH_V7_ROOT / "trade_active_edge_records_v7.jsonl",
        RESEARCH_V7_ROOT / "no_trade_dominance_flags_v7.jsonl",
        V6_WATCHLIST_DIAGNOSIS_V7_SUMMARY_PATH,
        RESEARCH_V7_ROOT / "v6_watchlist_diagnosis_v7.jsonl",
        RESEARCH_V7_ROOT / "v6_gate_blocker_analysis_v7.jsonl",
        RESEARCH_V7_ROOT / "v6_trade_active_blocker_matrix_v7.jsonl",
        MUTATION_EXEC_V7_SUMMARY_PATH,
        RESEARCH_V7_ROOT / "research_mutation_execution_records_v7.jsonl",
        RESEARCH_V7_ROOT / "research_mutation_execution_failures_v7.jsonl",
        RESEARCH_V7_ROOT / "research_mutation_expansion_records_v7.jsonl",
        TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH,
        RESEARCH_V7_ROOT / "trade_active_repair_policy_v7.json",
        RESEARCH_V7_ROOT / "trade_active_repair_rules_v7.jsonl",
        RESEARCH_V7_ROOT / "future_leakage_guard_records_v7.jsonl",
        CANDIDATE_GENERATOR_V7_SUMMARY_PATH,
        RESEARCH_V7_ROOT / "research_signal_candidates_v7.jsonl",
        RESEARCH_V7_ROOT / "research_candidate_density_schedule_v7.jsonl",
        SCORER_V7_SUMMARY_PATH,
        SIMULATOR_V7_SUMMARY_PATH,
        RESEARCH_V7_ROOT / "research_path_trades_v7.jsonl",
        RESEARCH_V7_ROOT / "research_path_exit_events_v7.jsonl",
        TOURNAMENT_V7_SUMMARY_PATH,
        GATE_V7_SUMMARY_PATH,
        MUTATION_QUEUE_V7_SUMMARY_PATH,
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v7.json",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v7.html",
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v7.md",
        LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v7.json",
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
        "public_signal_research_breakthrough_v7_summary": str(SUMMARY_PATH),
        "public_signal_research_breakthrough_v7_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "public_signal_research_breakthrough_v7_session_copy_manifest": str(LOCAL_MANIFEST_PATH),
    }


orchestrator_artifact_paths = _orchestrator_artifact_paths


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_breakthrough_v7(), indent=2, sort_keys=True, default=str))
