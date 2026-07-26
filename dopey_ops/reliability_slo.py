"""Reliability SLO: an error budget for the evidence pipeline (Google SRE).

The forward-evidence gate needs ~100 validated closes; every missed ritual
day pushes that horizon out. SRE's insight is that reliability must be a
MEASURED product with an explicit budget - "we allow N misses per window" -
so that when the budget is burned, reliability work visibly outranks feature
work. The first two weeks of the forward walk lost ~40% of sessions to
outages that nothing was measuring; this lane makes that loss impossible to
miss again.

SLIs:
  - chain-fetch adherence: trading days in the window with a chain snapshot
    directory (the head of the funnel; a missed fetch loses the whole day),
  - marking freshness: sessions since the forward walk last marked,
  - supervisor freshness: hours since the last supervisor journal entry,
  - nightly freshness: hours since the last nightly summary.
  - research-lane liveness: time since each lane's last attempt and verified
    success, measured against that lane's configured cadence.

Reliability is never edge, readiness, or trading evidence. Burn-rate breaches
may only fail closed the bounded autonomous cadence accelerator; they never
authorize an action, promotion, order, or relaxation of a safety rule.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dopey_acceleration.common import stable_hash
from dopey_acceleration.schedule import LANES
from dopey_core.market_calendar import is_trading_day
from dopey_research_pipeline.artifact_io import write_json_atomic

REPO_ROOT = Path(__file__).resolve().parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"
CHAIN_RAW_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chains"
SLO_PATH = ART / "ops" / "reliability_slo.json"

SLO_VERSION = "dopey-reliability-slo-v3"
WINDOW_TRADING_DAYS = 14
FETCH_ADHERENCE_SLO = 0.95
SUPERVISOR_FRESH_HOURS = 26.0
SUPERVISOR_ACTIVE_HEARTBEAT_FRESH_HOURS = 1.0
NIGHTLY_FRESH_HOURS = 30.0
LANE_STALL_INTERVAL_MULTIPLIER = 2.0
REPAIR_QUEUE_MAX_AGE_HOURS = 72.0
# The streaming atomic writer needs headroom for a full .tmp copy of the
# largest ledger (~1.5GB) while the original still exists; 20GB keeps several
# such rewrites plus daily data growth from ever hitting ENOSPC mid-run
# (observed transiently 2026-07-23).
DISK_FREE_FLOOR_GB = 20.0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _last_jsonl_entry(path: Path) -> dict[str, Any]:
    try:
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        parsed = json.loads(lines[-1]) if lines else {}
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def trailing_trading_days(as_of: date, count: int) -> list[str]:
    days: list[str] = []
    cursor = as_of
    while len(days) < count:
        if is_trading_day(cursor):
            days.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return list(reversed(days))


def fetch_adherence(as_of: date) -> dict[str, Any]:
    window = trailing_trading_days(as_of, WINDOW_TRADING_DAYS)
    have = (
        {p.name for p in CHAIN_RAW_DIR.iterdir() if p.is_dir()}
        if CHAIN_RAW_DIR.exists()
        else set()
    )
    missed = [day for day in window if day not in have]
    adherence = (len(window) - len(missed)) / len(window)
    budget_allowed = int((1.0 - FETCH_ADHERENCE_SLO) * len(window))
    return {
        "window_trading_days": len(window),
        "window_start": window[0],
        "window_end": window[-1],
        "missed_days": missed,
        "missed_count": len(missed),
        "adherence": round(adherence, 4),
        "slo": FETCH_ADHERENCE_SLO,
        "error_budget_misses_allowed": budget_allowed,
        "error_budget_remaining": budget_allowed - len(missed),
        "budget_exhausted": adherence < FETCH_ADHERENCE_SLO,
    }


def _hours_since(timestamp_text: str, now: datetime) -> float | None:
    try:
        stamp = datetime.fromisoformat(timestamp_text)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return round((now - stamp).total_seconds() / 3600.0, 2)
    except ValueError:
        return None


def _disk_free_gb() -> float | None:
    import shutil

    try:
        return round(shutil.disk_usage(REPO_ROOT).free / 1e9, 2)
    except OSError:
        return None


def classify_supervisor_active_run(now: datetime) -> dict[str, Any]:
    """Classify the active-run artifact without mutating supervisor state."""
    path = ART / "research_supervisor" / "supervisor_active_run.json"
    if not path.exists():
        return {
            "status": "not_present",
            "reported_run_status": "",
            "heartbeat_age_hours": None,
            "breach": False,
        }

    active_run = _load_json(path)
    if not active_run:
        return {
            "status": "unreadable_active_run_artifact",
            "reported_run_status": "",
            "heartbeat_age_hours": None,
            "breach": True,
        }

    reported_run_status = str(active_run.get("run_status", "") or "")
    heartbeat_age = _hours_since(str(active_run.get("heartbeat_at_utc", "") or ""), now)
    if reported_run_status == "completed":
        return {
            "status": "terminal_active_run_artifact",
            "reported_run_status": reported_run_status,
            "heartbeat_age_hours": heartbeat_age,
            "breach": False,
        }
    if reported_run_status != "running":
        return {
            "status": "unverified_active_run_status",
            "reported_run_status": reported_run_status,
            "heartbeat_age_hours": heartbeat_age,
            "breach": True,
        }
    if heartbeat_age is None:
        return {
            "status": "unverified_running_artifact",
            "reported_run_status": reported_run_status,
            "heartbeat_age_hours": None,
            "breach": True,
        }
    if heartbeat_age < 0:
        return {
            "status": "future_heartbeat_artifact",
            "reported_run_status": reported_run_status,
            "heartbeat_age_hours": heartbeat_age,
            "breach": True,
        }
    if heartbeat_age > SUPERVISOR_ACTIVE_HEARTBEAT_FRESH_HOURS:
        return {
            "status": "stale_running_artifact",
            "reported_run_status": reported_run_status,
            "heartbeat_age_hours": heartbeat_age,
            "breach": True,
        }
    return {
        "status": "fresh_running_artifact",
        "reported_run_status": reported_run_status,
        "heartbeat_age_hours": heartbeat_age,
        "breach": False,
    }


def classify_lane_reliability(now: datetime) -> dict[str, Any]:
    """Classify schedule progress against each lane's declared cadence."""
    state_path = ART / "acceleration" / "schedule_state.json"
    state = _load_json(state_path)
    if not state:
        return {
            "status": "missing_or_unreadable_schedule_state",
            "lane_count": len(LANES),
            "breached_lane_count": len(LANES),
            "lanes": [],
            "breach": True,
        }
    raw_attempts = state.get("last_attempt_utc")
    raw_successes = state.get("last_success_utc")
    raw_statuses = state.get("lane_statuses")
    attempts = raw_attempts if isinstance(raw_attempts, dict) else {}
    successes = raw_successes if isinstance(raw_successes, dict) else {}
    statuses = raw_statuses if isinstance(raw_statuses, dict) else {}
    lane_records: list[dict[str, Any]] = []
    for lane in LANES:
        lane_id = lane["lane_id"]
        interval_minutes = int(lane["interval_minutes"])
        stall_limit_minutes = round(
            interval_minutes * LANE_STALL_INTERVAL_MULTIPLIER,
            2,
        )
        attempt_age_hours = _hours_since(str(attempts.get(lane_id, "")), now)
        success_age_hours = _hours_since(str(successes.get(lane_id, "")), now)
        attempt_age_minutes = (
            None
            if attempt_age_hours is None
            else round(attempt_age_hours * 60.0, 2)
        )
        success_age_minutes = (
            None
            if success_age_hours is None
            else round(success_age_hours * 60.0, 2)
        )
        status_record = statuses.get(lane_id)
        last_run_status = (
            str(status_record.get("status", "unknown"))
            if isinstance(status_record, dict)
            else "unknown"
        )
        reasons: list[str] = []
        if attempt_age_minutes is None:
            reasons.append("missing_last_attempt")
        elif attempt_age_minutes < 0:
            reasons.append("future_last_attempt")
        elif attempt_age_minutes > stall_limit_minutes:
            reasons.append("attempt_stalled")
        if success_age_minutes is None:
            reasons.append("never_verified_success")
        elif success_age_minutes < 0:
            reasons.append("future_last_success")
        elif success_age_minutes > stall_limit_minutes:
            reasons.append("verified_success_stalled")
        if last_run_status in {
            "degraded_evidence",
            "failed",
            "inconclusive_timeout",
            "skipped_run_budget",
        }:
            reasons.append(f"chronic_status:{last_run_status}")
        lane_records.append(
            {
                "lane_id": lane_id,
                "interval_minutes": interval_minutes,
                "stall_limit_minutes": stall_limit_minutes,
                "minutes_since_attempt": attempt_age_minutes,
                "minutes_since_verified_success": success_age_minutes,
                "last_run_status": last_run_status,
                "breach_reasons": reasons,
                "breach": bool(reasons),
            }
        )
    breached_count = sum(1 for record in lane_records if record["breach"])
    return {
        "status": "lane_reliability_breached"
        if breached_count
        else "all_lanes_within_cadence",
        "lane_count": len(lane_records),
        "breached_lane_count": breached_count,
        "lanes": lane_records,
        "breach": breached_count > 0,
    }


def classify_repair_queue(now: datetime) -> dict[str, Any]:
    path = (
        ART
        / "research_supervisor"
        / "resilient_research_supervisor_repair_queue.jsonl"
    )
    if not path.exists():
        return {
            "status": "empty",
            "open_item_count": 0,
            "oldest_item_age_hours": None,
            "items_missing_recorded_at": 0,
            "breach": False,
        }
    ages: list[float] = []
    missing_recorded_at = 0
    item_count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                record = json.loads(raw)
                if not isinstance(record, dict):
                    raise TypeError(
                        "supervisor repair queue entry must be an object: "
                        f"path={path}, line={line_number}"
                    )
                item_count += 1
                age = _hours_since(
                    str(record.get("recorded_at_utc", "")),
                    now,
                )
                if age is None:
                    missing_recorded_at += 1
                else:
                    ages.append(age)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        return {
            "status": "unreadable_repair_queue",
            "open_item_count": item_count,
            "oldest_item_age_hours": None,
            "items_missing_recorded_at": missing_recorded_at,
            "error": f"{type(error).__name__}: {error}",
            "breach": True,
        }
    oldest_age = max(ages) if ages else None
    breach = bool(
        missing_recorded_at
        or (oldest_age is not None and oldest_age > REPAIR_QUEUE_MAX_AGE_HOURS)
        or any(age < 0 for age in ages)
    )
    return {
        "status": "repair_queue_age_breached"
        if breach
        else "open_items_within_response_window"
        if item_count
        else "empty",
        "open_item_count": item_count,
        "oldest_item_age_hours": oldest_age,
        "items_missing_recorded_at": missing_recorded_at,
        "maximum_item_age_hours": REPAIR_QUEUE_MAX_AGE_HOURS,
        "breach": breach,
    }


def run_reliability_slo(
    as_of: date | None = None,
    now: datetime | None = None,
    disk_free_gb: float | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.today()
    now = now or datetime.now(timezone.utc)
    if disk_free_gb is None:
        disk_free_gb = _disk_free_gb()
    fetch = fetch_adherence(as_of)

    walk = _load_json(ART / "forward_walk" / "forward_walk_summary.json")
    last_marking = str(walk.get("snapshot_date", "") or "")
    try:
        last_marking_date = date.fromisoformat(last_marking)
    except ValueError:
        last_marking_date = None
    marking_lag_sessions = None
    if last_marking_date is not None and last_marking_date <= as_of:
        marking_lag_sessions = sum(
            1
            for day in trailing_trading_days(as_of, WINDOW_TRADING_DAYS)
            if day > last_marking
        )

    journal_entry = _last_jsonl_entry(
        ART / "research_supervisor" / "supervisor_run_journal.jsonl"
    )
    journal_timestamp = str(
        journal_entry.get("finished_at_utc") or journal_entry.get("run_utc") or ""
    )
    supervisor_age = _hours_since(journal_timestamp, now)
    active_run = classify_supervisor_active_run(now)
    lane_reliability = classify_lane_reliability(now)
    repair_queue = classify_repair_queue(now)
    nightly = _load_json(ART / "nightly" / "nightly_latest.json")
    nightly_age = _hours_since(str(nightly.get("finished_at_utc", "")), now)

    breaches: list[str] = []
    if fetch["budget_exhausted"]:
        breaches.append(
            f"chain-fetch error budget exhausted: {fetch['missed_count']} missed of "
            f"{fetch['window_trading_days']} trading days (SLO {FETCH_ADHERENCE_SLO:.0%})"
        )
    if last_marking_date is None:
        breaches.append("forward-walk marking timestamp is missing or invalid")
    elif last_marking_date > as_of:
        breaches.append(
            "forward-walk marking timestamp is future-dated: "
            f"snapshot_date={last_marking}, as_of_date={as_of.isoformat()}"
        )
    elif marking_lag_sessions is not None and marking_lag_sessions > 1:
        breaches.append(
            f"forward walk has not marked for {marking_lag_sessions} trading sessions"
        )
    if supervisor_age is None:
        breaches.append("supervisor journal timestamp is missing or invalid")
    elif supervisor_age < 0:
        breaches.append(
            f"supervisor journal timestamp is future-dated: age_hours={supervisor_age}"
        )
    elif supervisor_age > SUPERVISOR_FRESH_HOURS:
        breaches.append(
            f"supervisor journal is {supervisor_age:.0f}h old (limit {SUPERVISOR_FRESH_HOURS:.0f}h)"
        )
    if active_run["breach"]:
        breaches.append(
            "supervisor active-run liveness is unverified: "
            f"status={active_run['status']}, "
            f"heartbeat_age_hours={active_run['heartbeat_age_hours']}"
        )
    if lane_reliability["breach"]:
        breached_lane_ids = [
            str(record["lane_id"])
            for record in lane_reliability["lanes"]
            if record["breach"]
        ]
        breaches.append(
            "research lane liveness breached: "
            f"breached_lane_count={lane_reliability['breached_lane_count']}, "
            f"lane_ids={breached_lane_ids}"
        )
    if repair_queue["breach"]:
        breaches.append(
            "supervisor repair queue response window breached: "
            f"status={repair_queue['status']}, "
            f"open_item_count={repair_queue['open_item_count']}, "
            f"oldest_item_age_hours={repair_queue['oldest_item_age_hours']}, "
            f"items_missing_recorded_at={repair_queue['items_missing_recorded_at']}"
        )
    if nightly_age is None:
        breaches.append("nightly summary timestamp is missing or invalid")
    elif nightly_age < 0:
        breaches.append(
            f"nightly summary timestamp is future-dated: age_hours={nightly_age}"
        )
    elif nightly_age > NIGHTLY_FRESH_HOURS:
        breaches.append(
            f"nightly summary is {nightly_age:.0f}h old (limit {NIGHTLY_FRESH_HOURS:.0f}h)"
        )
    if disk_free_gb is None:
        breaches.append("disk headroom is unavailable")
    elif disk_free_gb < DISK_FREE_FLOOR_GB:
        breaches.append(
            f"disk headroom {disk_free_gb:.1f}GB below the {DISK_FREE_FLOOR_GB:.0f}GB floor: "
            "the streaming atomic writer will hit ENOSPC mid-rewrite"
        )

    summary = {
        "artifact_type": "reliability_slo",
        "slo_version": SLO_VERSION,
        "generated_at_utc": now.astimezone(timezone.utc).isoformat(),
        "slo_status": "error_budget_breached" if breaches else "within_error_budget",
        "as_of_date": as_of.isoformat(),
        "fetch_adherence": fetch,
        "marking_lag_sessions": marking_lag_sessions,
        "supervisor_journal_age_hours": supervisor_age,
        "supervisor_active_run": active_run,
        "lane_reliability": lane_reliability,
        "supervisor_repair_queue": repair_queue,
        "nightly_age_hours": nightly_age,
        "disk_free_gb": disk_free_gb,
        "disk_free_floor_gb": DISK_FREE_FLOOR_GB,
        "breaches": breaches,
        "recommendation": (
            "error budget breached: reliability work outranks research work until green"
            if breaches
            else "within budget: research work may proceed"
        ),
        "operational_cadence_guard_allowed": True,
        "operational_cadence_guard_scope": "fail_closed_cadence_acceleration_only",
        "edge_evidence_allowed": False,
        "readiness_gate_input_allowed": False,
        "trading_gate_input_allowed": False,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = stable_hash(summary)
    write_json_atomic(SLO_PATH, summary)
    return summary
