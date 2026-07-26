"""OPERATOR TOOL - nightly effectiveness harness (runs unattended at 5 AM local).

A long test run is only worth the wall-clock if it catches things a single
`pytest` pass cannot. This harness bundles the three signals that actually
matter overnight and writes ONE dated verdict a human can glance at each
morning:

1. Full regression suite - the ~3k-test enumeration, under the isolation
   layer (cannot pollute the live tree), wall-clock capped.
2. Stack stability - verify the most recent PRODUCTION supervisor run from
   its append-only journal: fresh within the daily cadence, zero failed
   stages, zero dependency skips, zero regressions vs the prior run. The
   18:30 production pass is the real stack signal; re-running a duplicate
   multi-hour supervisor here proved worse than useless - it could not fit
   the nightly window (permanent inconclusive_timeout) and its concurrent
   full-spine loads caused the memory pressure and mid-write corruption it
   existed to detect.
3. Determinism - the held-out evolution fitness run twice; a drift means the
   research scorer became non-reproducible (a silent-corruption alarm).

Any red -> non-zero exit + a loud line in the report. Green nights are boring
by design. This does NOT fetch data, enter trades, or run apply-mode search;
it observes. Paper-only, live-blocked, evidence-neutral. The weekend soak
(Saturday, wide window) remains the place a supervisor is re-run for stability.

Usage:  .venv\\Scripts\\python operator_tools\\operator_nightly.py
Schedule ownership: operator_tools/install_operational_cadence.ps1 keeps this
at 05:00 local, after the 15:15 daily ritual and 18:30 research supervisor.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_research_pipeline.artifact_io import append_jsonl, write_json_atomic  # noqa: E402
from dopey_autonomy.run_resilient_research_supervisor import (  # noqa: E402
    read_supervisor_progress,
    supervisor_run_active,
)
from operator_tools.operator_cleanup_stale_pytest_temp import run_cleanup  # noqa: E402
from operator_tools.nightly_shards import run_sharded_suite  # noqa: E402
from operator_tools.process_tree import (  # noqa: E402
    ProcessTreeTerminationError,
    run_captured_process_tree,
)

PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")
NIGHTLY_DIR = REPO / "artifacts" / "dopey" / "nightly"
NIGHTLY_LEDGER = NIGHTLY_DIR / "nightly_ledger.jsonl"
SUPERVISOR_JOURNAL_PATH = (
    REPO / "artifacts" / "dopey" / "research_supervisor" / "supervisor_run_journal.jsonl"
)
SHARD_COUNT = 8
# The public-signal and export/audit shards launch nested validators; two
# workers preserve a conclusive memory envelope while still overlapping lanes.
SHARD_WORKERS = 2
SHARD_TIMEOUT_SECONDS = 5400
# Production supervisor cadence is daily (18:30); 26h tolerates schedule jitter
# without accepting a skipped day as "fresh".
MAX_PRODUCTION_RUN_AGE_HOURS = 26.0
FITNESS_TIMEOUT_SECONDS = 1_800


def _with_summary_hash(record: dict[str, object]) -> dict[str, object]:
    encoded = json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return {
        **record,
        "summary_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _verify_production_stack() -> dict[str, object]:
    """Assess the latest completed production supervisor run from its journal.

    A journal entry is only written by a run that reached completion, so a
    crashed/killed supervisor shows up here as a stale (or missing) entry,
    never as a green one.
    """
    check = {
        "check_mode": "production_run_journal_verification",
        "journal_path": str(SUPERVISOR_JOURNAL_PATH),
        "supervisor_status": "no_production_run_journal",
        "assessed_run_utc": "",
        "assessed_run_age_hours": None,
        "stage_regressions": [],
        "stages_failed_absorbed": None,
        "stages_skipped_dependency": None,
        "green": False,
        "red_reasons": [],
    }
    if not SUPERVISOR_JOURNAL_PATH.exists():
        check["red_reasons"] = ["journal_missing"]
        return check
    last_line = ""
    with SUPERVISOR_JOURNAL_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last_line = line
    if not last_line:
        check["red_reasons"] = ["journal_empty"]
        return check
    entry = json.loads(last_line)
    if not isinstance(entry, dict):
        check["red_reasons"] = ["journal_entry_not_object"]
        return check
    run_utc_raw = str(entry.get("run_utc", ""))
    regressions = entry.get("regressions_vs_previous_run", [])
    if not isinstance(regressions, list):
        regressions = [f"unreadable_regressions_field:{type(regressions).__name__}"]
    failed_absorbed = int(entry.get("stages_failed_absorbed", -1))
    skipped_dependency = int(entry.get("stages_skipped_dependency", -1))
    early_return = entry.get("early_return") is True
    check.update(
        {
            "supervisor_status": str(entry.get("supervisor_status", "unknown")),
            "assessed_run_utc": run_utc_raw,
            "stage_regressions": regressions,
            "stages_failed_absorbed": failed_absorbed,
            "stages_skipped_dependency": skipped_dependency,
        }
    )
    reasons: list[str] = []
    if early_return:
        reasons.append(
            "supervisor_early_return:"
            f"{entry.get('supervisor_status', 'unknown')}"
        )
    try:
        run_utc = datetime.fromisoformat(run_utc_raw)
        if run_utc.tzinfo is None:
            run_utc = run_utc.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - run_utc).total_seconds() / 3600.0
        check["assessed_run_age_hours"] = round(age_hours, 2)
        if age_hours > MAX_PRODUCTION_RUN_AGE_HOURS:
            reasons.append(f"stale_production_run:{age_hours:.1f}h")
    except ValueError:
        reasons.append(f"unparseable_run_utc:{run_utc_raw!r}")
    if failed_absorbed != 0:
        reasons.append(f"stages_failed_absorbed:{failed_absorbed}")
    if skipped_dependency != 0:
        reasons.append(f"stages_skipped_dependency:{skipped_dependency}")
    if regressions:
        reasons.append(f"stage_regressions:{len(regressions)}")
    check["red_reasons"] = reasons
    check["green"] = not reasons
    return check


def _run_fitness_once() -> dict[str, object]:
    command = [
        PYTHON,
        str(REPO / "operator_tools" / "operator_evolve_fitness.py"),
    ]
    try:
        completed = run_captured_process_tree(
            command,
            REPO,
            None,
            FITNESS_TIMEOUT_SECONDS,
        )
    except ProcessTreeTerminationError as error:
        raise RuntimeError(
            "nightly fitness timed out and its process tree could not be "
            f"proven terminated: command={command}, error={error}"
        ) from error
    if completed["timed_out"]:
        return {
            "score": "status=inconclusive_timeout",
            "ok": False,
            "stderr_tail": completed["stderr"][-500:],
            "process_tree_terminated": completed["process_tree_terminated"],
        }
    lines = [line for line in completed["stdout"].splitlines() if line.strip()]
    if completed["return_code"] != 0 or not lines:
        return {
            "score": f"status=failed;rc={completed['return_code']}",
            "ok": False,
            "stderr_tail": completed["stderr"][-500:],
            "process_tree_terminated": False,
        }
    return {
        "score": lines[-1].strip(),
        "ok": True,
        "stderr_tail": "",
        "process_tree_terminated": False,
    }


def _run_fitness_determinism() -> dict[str, object]:
    """Run the held-out evolution fitness twice; equal scores or red."""
    results = []
    for _ in range(2):
        results.append(_run_fitness_once())
    scores = [str(result["score"]) for result in results]
    deterministic = (
        all(result["ok"] for result in results) and len(set(scores)) == 1
    )
    return {
        "scores": scores,
        "deterministic": deterministic,
        "stderr_tails": [str(result["stderr_tail"]) for result in results if result["stderr_tail"]],
    }


def run_suite() -> dict[str, object]:
    return run_sharded_suite(
        PYTHON,
        REPO,
        REPO / "tests",
        NIGHTLY_DIR,
        SHARD_COUNT,
        SHARD_WORKERS,
        SHARD_TIMEOUT_SECONDS,
    )


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    if supervisor_run_active():
        supervisor_progress = read_supervisor_progress()
        suite_summary = "nightly validation deferred because the production supervisor is still active"
        record = {
            "artifact_type": "nightly_effectiveness_report",
            "date": date.today().isoformat(),
            "started_at_utc": started,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "verdict": "inconclusive_active_supervisor",
            "suite": {
                "suite_status": "not_run_active_supervisor",
                "summary_line": suite_summary,
            },
            "suite_green": False,
            "active_supervisor_progress": supervisor_progress,
            "stack_stability": {
                "supervisor_status": "locked_concurrent_run",
                "check_mode": "not_run_active_supervisor",
                "stage_regressions": [],
                "red_reasons": ["production_supervisor_still_active"],
                "green": False,
            },
            "fitness_determinism": {
                "scores": [],
                "deterministic": False,
            },
            "paper_only": True,
            "live_blocked": True,
        }
        record = _with_summary_hash(record)
        write_json_atomic(NIGHTLY_DIR / "nightly_latest.json", record)
        append_jsonl(
            NIGHTLY_LEDGER,
            {
                "date": record["date"],
                "verdict": record["verdict"],
                "suite_green": False,
                "suite_summary": suite_summary,
                "stack_check_mode": "not_run_active_supervisor",
                "stage_regressions": [],
                "fitness_deterministic": False,
                "finished_at_utc": record["finished_at_utc"],
                "active_supervisor_run_id": supervisor_progress.get("run_id", ""),
                "active_supervisor_current_stage": supervisor_progress.get("current_stage", "unknown_uninstrumented_run"),
            },
        )
        print(json.dumps({
            "verdict": record["verdict"],
            "suite": suite_summary,
        }, indent=2), flush=True)
        return 2
    pytest_temp_cleanup = run_cleanup(True)
    suite = run_suite()
    stack = _verify_production_stack()
    determinism = _run_fitness_determinism()

    suite_green = suite["suite_status"] == "complete_green"
    stack_green = stack["green"] is True
    determinism_green = determinism["deterministic"] is True
    all_green = suite_green and stack_green and determinism_green
    inconclusive = suite["suite_status"] == "inconclusive_timeout"
    verdict = "all_green" if all_green else "inconclusive_timeout" if inconclusive else "attention_required"

    record = {
        "artifact_type": "nightly_effectiveness_report",
        "date": date.today().isoformat(),
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "suite": suite,
        "suite_green": suite_green,
        "pytest_temp_cleanup": pytest_temp_cleanup,
        "stack_stability": {
            "supervisor_status": stack["supervisor_status"],
            "check_mode": stack["check_mode"],
            "assessed_run_utc": stack["assessed_run_utc"],
            "assessed_run_age_hours": stack["assessed_run_age_hours"],
            "stage_regressions": stack["stage_regressions"],
            "red_reasons": stack["red_reasons"],
            "green": stack_green,
        },
        "fitness_determinism": {
            "scores": determinism["scores"],
            "deterministic": determinism_green,
        },
        "paper_only": True,
        "live_blocked": True,
    }
    record = _with_summary_hash(record)
    write_json_atomic(NIGHTLY_DIR / "nightly_latest.json", record)
    append_jsonl(NIGHTLY_LEDGER, {
        "date": record["date"],
        "verdict": record["verdict"],
        "suite_green": suite_green,
        "suite_summary": suite["summary_line"],
        "stack_check_mode": stack["check_mode"],
        "stack_red_reasons": stack["red_reasons"],
        "stage_regressions": stack["stage_regressions"],
        "fitness_deterministic": determinism_green,
        "pytest_temp_cleanup_status": pytest_temp_cleanup["cleanup_status"],
        "pytest_temp_estimated_removed_bytes": pytest_temp_cleanup[
            "estimated_removed_bytes"
        ],
        "finished_at_utc": record["finished_at_utc"],
    })

    print(json.dumps({
        "verdict": record["verdict"],
        "suite": suite["summary_line"],
        "stack_red_reasons": stack["red_reasons"],
        "stack_regressions": stack["stage_regressions"],
        "fitness_deterministic": determinism_green,
        "pytest_temp_cleanup_status": pytest_temp_cleanup["cleanup_status"],
        "pytest_temp_estimated_removed_bytes": pytest_temp_cleanup[
            "estimated_removed_bytes"
        ],
    }, indent=2), flush=True)
    return 0 if all_green else 2 if inconclusive else 1


if __name__ == "__main__":
    raise SystemExit(main())
