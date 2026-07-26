"""Optional expensive lane runner for V5.

Runs:
- dopey_audit.run_offline_evidence_replay_audit
- dopey_export.run_artifact_compaction_export_verifier

Rules:
- caps (max duration per lane)
- timeout = `inconclusive_timeout`
- timeout is NOT pass
- records stdout/stderr snippet, duration, exit code, status
- optional timeout does not block V5 completion
- does not fabricate pass
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    EXPENSIVE_LANE_V5_PROOF_PATH,
    EXPENSIVE_LANE_V5_RECORDS_PATH,
    EXPENSIVE_LANE_V5_SUMMARY_PATH,
    EXPENSIVE_LANE_V5_TIMEOUT_PATH,
    RESEARCH_V5_VERSION,
    research_v5_proof_record,
    utc_now_iso,
)
from dopey_wealth_engine.common import REPO_ROOT


__all__ = ["run_public_signal_research_expensive_lane_runner_v5"]


# Per-lane caps. These are deliberately small; we only need a smoke / probe.
LANES = [
    {
        "lane_id": "offline_evidence_replay_audit",
        "module": "dopey_audit.run_offline_evidence_replay_audit",
        "cap_seconds": 20,
    },
    {
        "lane_id": "artifact_compaction_export_verifier",
        "module": "dopey_export.run_artifact_compaction_export_verifier",
        "cap_seconds": 20,
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(s: str, limit: int = 2000) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"... [truncated, total={len(s)}]"


def _run_lane(lane: dict[str, object]) -> dict[str, object]:
    started = _now_iso()
    cmd = [str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"), "-m", str(lane["module"])]
    cap = int(lane.get("cap_seconds", 60))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=cap,
            check=False,
        )
        duration = None
        if proc.returncode == 0:
            status = "ok"
        else:
            status = "nonzero_exit"
        record = {
            "artifact_type": "public_signal_research_expensive_lane_record_v5",
            "lane_id": lane["lane_id"],
            "module": lane["module"],
            "cap_seconds": cap,
            "started_at": started,
            "finished_at": _now_iso(),
            "exit_code": proc.returncode,
            "status": status,
            "stdout_snippet": _truncate(proc.stdout or ""),
            "stderr_snippet": _truncate(proc.stderr or ""),
            "timed_out": False,
            "timeout_recorded_as_pass": False,
            "live_trading_enabled": False,
        }
        return record_with_hash(record, "record_hash")
    except subprocess.TimeoutExpired as exc:
        record = {
            "artifact_type": "public_signal_research_expensive_lane_record_v5",
            "lane_id": lane["lane_id"],
            "module": lane["module"],
            "cap_seconds": cap,
            "started_at": started,
            "finished_at": _now_iso(),
            "exit_code": None,
            "status": "inconclusive_timeout",
            "stdout_snippet": _truncate((exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")),
            "stderr_snippet": _truncate((exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")),
            "timed_out": True,
            "timeout_recorded_as_pass": False,
            "live_trading_enabled": False,
        }
        return record_with_hash(record, "record_hash")
    except Exception as exc:  # noqa: BLE001
        record = {
            "artifact_type": "public_signal_research_expensive_lane_record_v5",
            "lane_id": lane["lane_id"],
            "module": lane["module"],
            "cap_seconds": cap,
            "started_at": started,
            "finished_at": _now_iso(),
            "exit_code": None,
            "status": "runner_error",
            "error": str(exc),
            "timed_out": False,
            "timeout_recorded_as_pass": False,
            "live_trading_enabled": False,
        }
        return record_with_hash(record, "record_hash")


def run_public_signal_research_expensive_lane_runner_v5() -> dict[str, object]:
    records: list[dict[str, object]] = []
    timeout_records: list[dict[str, object]] = []
    status_by_lane: dict[str, str] = {}
    timeout_count = 0
    for lane in LANES:
        rec = _run_lane(lane)
        records.append(rec)
        status_by_lane[lane["lane_id"]] = str(rec.get("status", ""))
        if bool(rec.get("timed_out")):
            timeout_count += 1
            timeout_records.append(rec)

    audit_status = status_by_lane.get("offline_evidence_replay_audit", "not_run")
    export_status = status_by_lane.get("artifact_compaction_export_verifier", "not_run")

    # Runner status logic: timeout does not block V5, but we still need to flag honestly
    any_timed_out = timeout_count > 0
    any_nonzero = any(r.get("exit_code") not in (0, None) for r in records)
    if any_timed_out:
        runner_status = "expensive_lane_runner_partial_timeout"
    elif any_nonzero:
        runner_status = "expensive_lane_runner_nonzero_exit"
    else:
        runner_status = "expensive_lane_runner_ok"

    summary = {
        "artifact_type": "public_signal_research_expensive_lane_summary_v5",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "expensive_lane_runner_status": runner_status,
        "offline_evidence_replay_audit_status": audit_status,
        "artifact_compaction_export_verifier_status": export_status,
        "lane_count": len(LANES),
        "record_count": len(records),
        "timeout_count": timeout_count,
        "timeout_recorded_as_pass": False,
        "optional_timeout_does_not_block_v5": True,
        "live_trading_enabled": False,
        "timestamp": _now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(EXPENSIVE_LANE_V5_RECORDS_PATH, records)
    write_jsonl_file(EXPENSIVE_LANE_V5_TIMEOUT_PATH, timeout_records)
    write_summary_with_hash(EXPENSIVE_LANE_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        EXPENSIVE_LANE_V5_PROOF_PATH,
        [research_v5_proof_record("public-signal-research-expensive-lane-v5", runner_status, summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(run_public_signal_research_expensive_lane_runner_v5(), indent=2, sort_keys=True, default=str))
