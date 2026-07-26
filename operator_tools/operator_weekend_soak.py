"""OPERATOR TOOL - weekend soak: repeated full-stack runs on closed markets.

Closed markets produce no new evidence, so the weekend's honest job is
STABILITY: run the whole supervisor repeatedly, prove no stage regresses
between consecutive runs, prove the evolution fitness is deterministic, and
prove the honest-lane tests stay green under repetition. Any regression stops
the soak with a non-zero exit so it is impossible to miss.

Usage:  .venv\\Scripts\\python operator_tools\\operator_weekend_soak.py [iterations]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_research_pipeline.artifact_io import append_jsonl, write_json_atomic  # noqa: E402
from operator_tools.process_tree import (  # noqa: E402
    ProcessTreeTerminationError,
    run_captured_process_tree,
)

PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")
SOAK_LOG = REPO / "artifacts" / "dopey" / "soak" / "soak_log.jsonl"
SUPERVISOR_ACTIVE_RUN_PATH = (
    REPO
    / "artifacts"
    / "dopey"
    / "research_supervisor"
    / "supervisor_active_run.json"
)
SUPERVISOR_TIMEOUT_SECONDS = 11 * 60 * 60
FITNESS_TIMEOUT_SECONDS = 1_800
HONEST_TEST_TIMEOUT_SECONDS = 1_200
HONEST_LANE_TESTS = (
    "tests/test_hardening_pass.py",
    "tests/test_macro_expansion.py",
    "tests/test_action_readiness_gate.py",
)


class CommandResult(TypedDict):
    status: str
    return_code: int | None
    output: str
    timeout_seconds: int


def _run(args: list[str], timeout: int) -> CommandResult:
    try:
        result = run_captured_process_tree(args, REPO, None, timeout)
    except ProcessTreeTerminationError as termination_error:
        return {
            "status": "failed",
            "return_code": None,
            "output": f"process_tree_termination_failed: {termination_error}",
            "timeout_seconds": timeout,
        }
    return {
        "status": (
            "inconclusive_timeout"
            if result["timed_out"]
            else "passed"
            if result["return_code"] == 0
            else "failed"
        ),
        "return_code": result["return_code"],
        "output": result["stdout"] + result["stderr"],
        "timeout_seconds": timeout,
    }


def _last_journal_entry() -> dict[str, Any]:
    path = REPO / "artifacts" / "dopey" / "research_supervisor" / "supervisor_run_journal.jsonl"
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return json.loads(lines[-1]) if lines else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _tombstone_timed_out_supervisor() -> None:
    if not SUPERVISOR_ACTIVE_RUN_PATH.exists():
        return
    try:
        active_run = json.loads(
            SUPERVISOR_ACTIVE_RUN_PATH.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "timed-out supervisor active-run artifact is unreadable: "
            f"path={SUPERVISOR_ACTIVE_RUN_PATH}, error={error}"
        ) from error
    if not isinstance(active_run, dict):
        raise TypeError(
            "timed-out supervisor active-run artifact must be an object: "
            f"path={SUPERVISOR_ACTIVE_RUN_PATH}"
        )
    if active_run.get("run_status") != "running":
        return
    recorded_at_utc = datetime.now(timezone.utc).isoformat()
    write_json_atomic(
        SUPERVISOR_ACTIVE_RUN_PATH,
        {
            **active_run,
            "run_status": "terminated_by_weekend_soak_timeout",
            "heartbeat_at_utc": recorded_at_utc,
            "finished_at_utc": recorded_at_utc,
            "recorded_as_pass": False,
            "paper_only": True,
            "live_blocked": True,
        },
    )


def _read_phase(checkpoint_root: Path | None, phase_name: str) -> dict[str, Any] | None:
    if checkpoint_root is None:
        return None
    path = checkpoint_root / f"{phase_name}.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"nightly soak phase checkpoint must be an object: path={path}")
    if value.get("phase_status") != "complete" or value.get("phase_name") != phase_name:
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        raise TypeError(f"nightly soak phase result must be an object: path={path}")
    return dict(result)


def _write_phase(checkpoint_root: Path | None, phase_name: str, result: dict[str, Any]) -> None:
    if checkpoint_root is None:
        return
    write_json_atomic(
        checkpoint_root / f"{phase_name}.json",
        {
            "artifact_type": "nightly_soak_subphase_checkpoint",
            "phase_name": phase_name,
            "phase_status": "complete",
            "result": result,
            "paper_only": True,
            "live_blocked": True,
        },
    )


def _command_phase_status(results: list[CommandResult]) -> str:
    statuses = [result["status"] for result in results]
    if "inconclusive_timeout" in statuses:
        return "inconclusive_timeout"
    if "failed" in statuses:
        return "failed"
    return "complete"


def soak_iteration(index: int, checkpoint_root: Path | None) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()

    supervisor_phase = _read_phase(checkpoint_root, "supervisor")
    supervisor_reused = supervisor_phase is not None
    if supervisor_phase is None:
        prior_journal = _last_journal_entry()
        supervisor_command = _run(
            [PYTHON, "-m", "dopey_autonomy.run_resilient_research_supervisor"],
            SUPERVISOR_TIMEOUT_SECONDS,
        )
        if supervisor_command["status"] == "inconclusive_timeout":
            _tombstone_timed_out_supervisor()
        journal = (
            _last_journal_entry()
            if supervisor_command["status"] == "passed"
            else {}
        )
        prior_run_id = str(prior_journal.get("run_id", ""))
        journal_run_id = str(journal.get("run_id", ""))
        journal_matches_command = bool(
            journal_run_id and journal_run_id != prior_run_id
        )
        command_status = supervisor_command["status"]
        if command_status == "passed" and not journal_matches_command:
            command_status = "failed"
        supervisor_phase = {
            "command_status": command_status,
            "supervisor_rc": supervisor_command["return_code"],
            "supervisor_status": (
                journal.get("supervisor_status", "unknown")
                if journal_matches_command
                else "unavailable_command_not_passed"
                if supervisor_command["status"] != "passed"
                else "unverified_missing_matching_journal"
            ),
            "journal_run_id": journal_run_id if journal_matches_command else "",
            "journal_matches_command": journal_matches_command,
            "stage_regressions": (
                list(journal.get("regressions_vs_previous_run", []))
                if journal_matches_command
                else []
            ),
            "output_tail": supervisor_command["output"][-12_000:],
            "timeout_seconds": supervisor_command["timeout_seconds"],
        }
        if command_status == "passed":
            _write_phase(checkpoint_root, "supervisor", supervisor_phase)

    fitness_phase = _read_phase(checkpoint_root, "fitness")
    fitness_reused = fitness_phase is not None
    if fitness_phase is None and supervisor_phase["command_status"] == "passed":
        fitness_results = [
            _run([PYTHON, "operator_tools/operator_evolve_fitness.py"], FITNESS_TIMEOUT_SECONDS)
            for _ in range(2)
        ]
        fitness_scores: list[str] = []
        for result in fitness_results:
            lines = [line.strip() for line in result["output"].splitlines() if line.strip()]
            if result["status"] == "passed" and lines:
                fitness_scores.append(lines[-1])
            else:
                fitness_scores.append(f"status={result['status']};rc={result['return_code']}")
        fitness_phase = {
            "command_status": _command_phase_status(fitness_results),
            "fitness_scores": fitness_scores,
            "fitness_deterministic": len(set(fitness_scores)) == 1
            and not fitness_scores[0].startswith("status="),
        }
        if fitness_phase["command_status"] == "complete":
            _write_phase(checkpoint_root, "fitness", fitness_phase)

    tests_phase = _read_phase(checkpoint_root, "honest_tests")
    tests_reused = tests_phase is not None
    if (
        tests_phase is None
        and supervisor_phase["command_status"] == "passed"
        and fitness_phase is not None
        and fitness_phase["command_status"] == "complete"
    ):
        tests_result = _run(
            [PYTHON, "-m", "pytest", *HONEST_LANE_TESTS, "-q", "--no-header"],
            HONEST_TEST_TIMEOUT_SECONDS,
        )
        tail = [line for line in tests_result["output"].splitlines() if line.strip()][-1:]
        tests_phase = {
            "command_status": "complete" if tests_result["status"] == "passed" else tests_result["status"],
            "honest_lane_tests_rc": tests_result["return_code"],
            "honest_lane_tests_tail": tail[0] if tail else "",
        }
        if tests_phase["command_status"] == "complete":
            _write_phase(checkpoint_root, "honest_tests", tests_phase)

    phase_statuses = [str(supervisor_phase["command_status"])]
    if fitness_phase is not None:
        phase_statuses.append(str(fitness_phase["command_status"]))
    if tests_phase is not None:
        phase_statuses.append(str(tests_phase["command_status"]))
    soak_status = (
        "inconclusive_timeout"
        if "inconclusive_timeout" in phase_statuses
        else "failed"
        if "failed" in phase_statuses or len(phase_statuses) < 3
        else "complete"
    )
    fitness_scores = list(fitness_phase.get("fitness_scores", [])) if fitness_phase is not None else []
    fitness_deterministic = bool(fitness_phase.get("fitness_deterministic", False)) if fitness_phase is not None else False
    tests_rc = tests_phase.get("honest_lane_tests_rc") if tests_phase is not None else None
    tests_tail = str(tests_phase.get("honest_lane_tests_tail", "")) if tests_phase is not None else ""
    regressions = list(supervisor_phase.get("stage_regressions", []))
    supervisor_rc = supervisor_phase.get("supervisor_rc")

    record = {
        "artifact_type": "weekend_soak_iteration",
        "iteration": index,
        "started_at_utc": started,
        "soak_status": soak_status,
        "supervisor_rc": supervisor_rc,
        "supervisor_command_status": supervisor_phase["command_status"],
        "supervisor_status": supervisor_phase.get("supervisor_status", "unknown"),
        "stage_regressions": regressions,
        "fitness_scores": fitness_scores,
        "fitness_deterministic": fitness_deterministic,
        "honest_lane_tests_rc": tests_rc,
        "honest_lane_tests_tail": tests_tail,
        "phase_checkpoint_reuse": {
            "supervisor": supervisor_reused,
            "fitness": fitness_reused,
            "honest_tests": tests_reused,
        },
        "soak_pass": soak_status == "complete"
        and supervisor_rc == 0
        and not regressions
        and fitness_deterministic
        and tests_rc == 0,
        "paper_only": True,
        "live_blocked": True,
    }
    append_jsonl(SOAK_LOG, record)
    return record


def main() -> int:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    for index in range(1, iterations + 1):
        record = soak_iteration(index, None)
        print(json.dumps({k: record[k] for k in (
            "iteration", "soak_status", "supervisor_status", "stage_regressions",
            "fitness_deterministic", "honest_lane_tests_tail", "soak_pass",
        )}), flush=True)
        if not record["soak_pass"]:
            print(f"SOAK FAILED at iteration {index} - investigate before Monday", flush=True)
            return 2 if record["soak_status"] == "inconclusive_timeout" else 1
    print(f"SOAK PASSED: {iterations} full-stack iterations, no regressions, deterministic fitness", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
