"""Run the bounded daily forward-evidence and risk refresh in dependency order."""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dopey_autonomy.run_resilient_research_supervisor import (
    STAGE_HARD_TIMEOUT_SECONDS,
    _run_stage_isolated,
)
from dopey_research_pipeline.artifact_io import write_json_atomic


REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "daily_forward_evidence_cycle.json"


STAGE_NAMES: tuple[str, ...] = (
    "real_signals",
    "market_structure",
    "chain_analytics_gate",
    "vol_surface_metrics",
    "market_context_fusion",
    "forward_paper_walk",
    "pipeline_forecast_card",
    "straddle_vrp_probe",
    "forward_book_quality",
    "forward_book_risk",
    "adversarial_stress",
    "distributional_stress",
    "exit_playbook",
    "signal_calibration",
    "adversarial_signal_panel",
    "action_readiness_gate",
    "kaizen_ledger",
    "reliability_slo",
)


def _reported_status(result: dict[str, Any]) -> str:
    status_keys = [
        key
        for key in result
        if (key.endswith("_status") or key in {"verdict", "status"})
        and not key.startswith("cached_")
    ]
    for key in status_keys:
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    return "completed_no_top_level_status"


def run_forward_evidence_cycle() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    run_id = f"daily-forward-{started.strftime('%Y%m%dT%H%M%S%fZ')}"
    results: list[dict[str, Any]] = []
    write_json_atomic(
        SUMMARY_PATH,
        _running_summary(run_id, started, "initializing", results),
    )
    for stage_index, stage_name in enumerate(STAGE_NAMES, start=1):
        stage_started = datetime.now(timezone.utc)
        write_json_atomic(
            SUMMARY_PATH,
            _running_summary(run_id, started, stage_name, results),
        )
        try:
            result = _run_stage_isolated(
                stage_name,
                run_id,
                stage_index,
                SUMMARY_PATH,
                STAGE_HARD_TIMEOUT_SECONDS,
            )
        except Exception as error:
            failed = {
                "artifact_type": "daily_forward_evidence_cycle",
                "cycle_status": "failed",
                "run_id": run_id,
                "started_at_utc": started.isoformat(),
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "failed_stage": stage_name,
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
                "completed_stages": results,
                "broker_commands_executed": False,
                "orders_submitted": 0,
            }
            write_json_atomic(SUMMARY_PATH, failed)
            raise
        finished = datetime.now(timezone.utc)
        results.append(
            {
                "stage": stage_name,
                "reported_status": _reported_status(result),
                "duration_seconds": round((finished - stage_started).total_seconds(), 3),
            }
        )
        write_json_atomic(
            SUMMARY_PATH,
            _running_summary(run_id, started, "between_stages", results),
        )
    finished = datetime.now(timezone.utc)
    summary = {
        "artifact_type": "daily_forward_evidence_cycle",
        "cycle_status": "complete",
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "stage_count": len(results),
        "stages": results,
        "policy": "refresh and mark forward paper evidence once per daily chain snapshot; negative gate verdicts remain explicit",
        "broker_commands_executed": False,
        "orders_submitted": 0,
    }
    write_json_atomic(SUMMARY_PATH, summary)
    return summary


def _running_summary(
    run_id: str,
    started: datetime,
    current_stage: str,
    completed_stages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "artifact_type": "daily_forward_evidence_cycle",
        "cycle_status": "running",
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
        "current_stage": current_stage,
        "completed_stage_count": len(completed_stages),
        "stage_count": len(STAGE_NAMES),
        "completed_stages": list(completed_stages),
        "broker_commands_executed": False,
        "orders_submitted": 0,
    }


def main() -> int:
    summary = run_forward_evidence_cycle()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
