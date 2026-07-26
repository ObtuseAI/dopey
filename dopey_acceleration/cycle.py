"""Execute allowlisted research schedule lanes with locking and evidence."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from operator_tools.operational_run_marker import operational_run_active
from operator_tools.process_tree import (
    ProcessTreeTerminationError,
    run_captured_process_tree,
)

from .common import (
    ARTIFACT_ROOT,
    read_optional_json,
    stable_hash,
    stamped,
    write_json_atomic,
)
from .provider_control import load_provider_control
from .research_mutations import load_research_overrides
from .schedule import (
    EXTERNAL_LANE_OWNERS,
    LANE_EVIDENCE_CONTRACTS,
    SCHEDULE_STATE_PATH,
    SCHEDULE_STATE_VERSION,
    LaneEvidenceStatus,
    build_schedule_plan,
    evaluate_lane_evidence,
)


LOCK_PATH = ARTIFACT_ROOT / "acceleration_cycle.lock"
CYCLE_RESULT_PATH = ARTIFACT_ROOT / "acceleration_cycle_result.json"
SUPERVISOR_LOCK_PATH = ARTIFACT_ROOT.parent.parent / ".supervisor.lock"
LEGACY_OR_CORRUPT_LOCK_STALE_SECONDS = 24 * 60 * 60
EVIDENCE_RECOVERY_TIMESTAMP_KEYS: Final[dict[str, str]] = {
    "llm_frontier_research": "issued_at",
    "playbook_refresh": "completed_utc",
}
EVIDENCE_RECOVERY_PRIOR_STATUSES: Final[frozenset[str]] = frozenset(
    {"failed", "degraded_evidence", "completed"}
)


def _pid_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise RuntimeError(
                "SystemRoot is required to verify a Windows acceleration lock owner"
            )
        tasklist = Path(system_root) / "System32" / "tasklist.exe"
        completed = subprocess.run(
            [str(tasklist), "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Windows process-liveness check failed: "
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


def _process_started_at_utc(process_id: int) -> str | None:
    if process_id <= 0:
        return None
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise RuntimeError(
                "SystemRoot is required to verify Windows acceleration process identity"
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
            "Windows acceleration process identity returned an invalid timestamp: "
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


def _valid_process_start_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _read_lock_payload() -> dict[str, Any] | None:
    try:
        raw_payload = LOCK_PATH.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return payload
    try:
        legacy_pid = int(raw_payload)
    except ValueError:
        return None
    return {
        "pid": legacy_pid,
        "legacy_pid_only": True,
    }


def _lock_age_seconds() -> float:
    return max(0.0, time.time() - LOCK_PATH.stat().st_mtime)


def _commands(repo_root: Path) -> dict[str, list[str]]:
    python = str(repo_root / ".venv" / "Scripts" / "python.exe")
    active_policy_path = (
        repo_root
        / "artifacts"
        / "dopey"
        / "acceleration"
        / "autonomous_improvement"
        / "active_policy.json"
    )
    active_policy, active_policy_availability = read_optional_json(
        active_policy_path
    )
    if active_policy_availability == "available":
        claimed_hash = active_policy.get("reproducibility_hash")
        unhashed_policy = dict(active_policy)
        unhashed_policy.pop("reproducibility_hash", None)
        if (
            not isinstance(claimed_hash, str)
            or stable_hash(unhashed_policy) != claimed_hash
        ):
            raise ValueError(
                "active autonomous policy failed command-routing integrity "
                f"validation: path={active_policy_path}"
            )
    research_overrides = load_research_overrides(active_policy)
    autoresearch_candidate_budget = research_overrides.get(
        "autonomous_strategy_research.candidate_budget",
        24,
    )
    intelligence_hypothesis_budget = research_overrides.get(
        "intelligence_discovery_research.hypothesis_budget",
        16,
    )
    return {
        "news_intake": [python, "-m", "operator_tools.operator_fetch_news_context"],
        "cross_asset_intake": [
            python,
            "-m",
            "operator_tools.operator_fetch_cross_asset_context",
        ],
        "quant_context_intake": [
            python,
            "-m",
            "operator_tools.operator_fetch_quant_context",
            "--sec-symbol-limit",
            "250",
        ],
        "context_outcome_settlement": [
            python,
            "-m",
            "operator_tools.update_context_decision_outcomes",
            "--batch-size",
            "500",
        ],
        "equity_swing_engine": [
            python,
            "-m",
            "dopey_equity_swing.run_equity_first_swing_engine",
        ],
        "playbook_refresh": [
            python,
            "-m",
            "dopey.strategy_engineering.run_playbook_refresh",
        ],
        "symbol_intelligence_lab": [
            python,
            "-m",
            "dopey_symbol_lab.run_symbol_lab",
            "--all",
        ],
        "intraday_watch": [python, "-m", "operator_tools.operator_intraday"],
        "universe_candidate_seed": [
            python,
            "-m",
            "dopey_acceleration.run_universe_acceleration",
            "--batch-size",
            "50",
        ],
        "governed_universe_growth": [
            python,
            "-m",
            "operator_tools.operator_universe_ritual",
        ],
        "vnext_forward_research": [
            python,
            "-m",
            "dopey.runtime.run_cross_sectional_vnext",
        ],
        "vnext_forward_settlement": [
            python,
            "-m",
            "dopey.settlement.run_operational_settlement",
        ],
        "autonomous_experiment_evaluation": [
            python,
            "-m",
            "dopey.autoresearch.run_experiment_evaluation",
            "--experiment-ledger",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "autoresearch"
                / "experiment_ledger.jsonl"
            ),
            "--history-manifest",
            str(repo_root / "dopey_data" / "history" / "history_dataset_manifest.json"),
            "--history-root",
            str(repo_root / "dopey_data" / "history"),
            "--findings-output",
            str(repo_root / "artifacts" / "dopey" / "vnext" / "research_findings.json"),
            "--evaluation-output-root",
            str(repo_root / "artifacts" / "dopey" / "autoresearch"),
        ],
        "autonomous_strategy_research": [
            python,
            "-m",
            "dopey.autoresearch.run_autoresearch_cycle",
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "autoresearch"),
            "--findings",
            str(repo_root / "artifacts" / "dopey" / "vnext" / "research_findings.json"),
            "--candidate-budget",
            str(autoresearch_candidate_budget),
        ],
        "coached_evolution_cycle": [
            python,
            "-m",
            "dopey_evolution.run_coached_evolution_cycle",
            "--repo-root",
            str(repo_root),
            "--symbol",
            "SPY",
            "--timeframe",
            "daily",
            "--head-coach",
            "claude",
            "--timeout-seconds",
            "300",
            "--daily-new-session-limit",
            "1",
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "coached_evolution"),
            "--coach-root",
            str(repo_root / "artifacts" / "dopey" / "two_coach" / "latest"),
            "--proposal-root",
            str(repo_root / "artifacts" / "dopey" / "two_coach" / "mutation_proposals"),
            "--history-manifest",
            str(repo_root / "dopey_data" / "history" / "history_dataset_manifest.json"),
            "--experiment-root",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "two_coach"
                / "experiments"
                / "channel_containment"
            ),
        ],
        "coach_proposal_quarantine": [
            python,
            "-m",
            "dopey_evolution.run_coach_bridge",
            "--coach-root",
            str(repo_root / "artifacts" / "dopey" / "two_coach" / "latest"),
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "two_coach" / "mutation_proposals"),
        ],
        "autonomous_threshold_audit": [
            python,
            "-m",
            "dopey.gates.run_audit",
            "--output",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "threshold_fabric"
                / "latest_audit.json"
            ),
        ],
        "strategy_engineering_research": [
            python,
            "-m",
            "dopey.strategy_engineering.run_cycle",
            "--predictions",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "vnext"
                / "cross_sectional_operational"
                / "forward_predictions.jsonl"
            ),
            "--settlements",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "vnext"
                / "cross_sectional_operational"
                / "memory"
                / "settlements.jsonl"
            ),
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "strategy_engineering"),
            "--candidate-budget",
            "32",
            "--minimum-reverse-support",
            "20",
        ],
        "evidence_intelligence": [
            python,
            "-m",
            "dopey_reporting.run_evidence_intelligence_cycle",
        ],
        "autonomous_promotion_evidence_synthesis": [
            python,
            "-m",
            "dopey.autoresearch.run_evidence_synthesis",
            "--autoresearch-cycle",
            str(
                repo_root / "artifacts" / "dopey" / "autoresearch" / "latest_cycle.json"
            ),
            "--forward-predictions",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "vnext"
                / "cross_sectional_operational"
                / "forward_predictions.jsonl"
            ),
            "--public-history-root",
            str(repo_root / "dopey_data" / "market_lake" / "public" / "daily_ohlcv"),
            "--output",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "autoresearch"
                / "promotion_evidence.json"
            ),
        ],
        "autonomous_promotion_evaluation": [
            python,
            "-m",
            "dopey.promotion.run_promotion_cycle",
            "--evidence",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "autoresearch"
                / "promotion_evidence.json"
            ),
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "autoresearch"),
        ],
        "autonomous_self_improvement": [
            python,
            "-m",
            "dopey_acceleration.run_autonomous_improvement",
            "--repo-root",
            str(repo_root),
            "--output-root",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "acceleration"
                / "autonomous_improvement"
            ),
        ],
        "intelligence_discovery_research": [
            python,
            "-m",
            "dopey.intelligence_research.run_intelligence_cycle",
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "intelligence_research"),
            "--readiness",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "acceleration"
                / "readiness_acceleration_plan.json"
            ),
            "--schedule-state",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "acceleration"
                / "schedule_state.json"
            ),
            "--autoresearch",
            str(
                repo_root / "artifacts" / "dopey" / "autoresearch" / "latest_cycle.json"
            ),
            "--promotion-cycle",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "autoresearch"
                / "latest_promotion_cycle.json"
            ),
            "--llm-research",
            str(
                repo_root / "artifacts" / "dopey" / "llm_research" / "latest_cycle.json"
            ),
            "--question-budget",
            "8",
            "--hypothesis-budget",
            str(intelligence_hypothesis_budget),
            "--cognitive-level",
            "2",
        ],
        "llm_frontier_research": [
            python,
            "-m",
            "dopey_acceleration.run_llm_research",
            "--repo-root",
            str(repo_root),
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "llm_research"),
            "--timeout-seconds",
            "300",
        ],
        "intelligence_evidence_evaluation": [
            python,
            "-m",
            "dopey.intelligence_research.run_cognitive_evidence_cycle",
            "--discovery-cycle",
            str(
                repo_root
                / "artifacts"
                / "dopey"
                / "intelligence_research"
                / "latest_cycle.json"
            ),
            "--task-store-root",
            str(repo_root / "dopey_data" / "cognitive_evaluation"),
            "--output-root",
            str(repo_root / "artifacts" / "dopey" / "intelligence_research"),
            "--visible-variants",
            "16",
        ],
        "weekly_sharpness_research": [
            python,
            "-m",
            "dopey_evolution.run_sharpness_tuning",
        ],
    }


def _run_command(
    command: list[str], repo_root: Path, timeout_seconds: int, attempts: int
) -> dict[str, Any]:
    last_error = ""
    environment = dict(os.environ)
    environment["DOPEY_RESEARCH_INSTRUMENT_MODE"] = load_provider_control()[
        "instrument_mode"
    ]
    environment["DOPEY_PAPER_ONLY"] = "1"
    environment["DOPEY_LIVE_BLOCKED"] = "1"
    for attempt in range(1, attempts + 1):
        try:
            completed = run_captured_process_tree(
                command,
                repo_root,
                environment,
                timeout_seconds,
            )
        except ProcessTreeTerminationError as error:
            raise RuntimeError(
                "research lane timed out and its process tree could not be "
                f"proven terminated: command={command}, error={error}"
            ) from error
        except OSError as error:
            last_error = f"{type(error).__name__}: {error}"
            print(
                json.dumps(
                    {
                        "warning": "research_lane_attempt_failed",
                        "attempt": attempt,
                        "error": last_error,
                    }
                ),
                file=sys.stderr,
            )
            continue
        if completed["timed_out"]:
            last_error = f"inconclusive_timeout after {timeout_seconds}s"
            print(
                json.dumps(
                    {
                        "warning": "research_lane_inconclusive_timeout",
                        "attempt": attempt,
                        "error": last_error,
                    }
                ),
                file=sys.stderr,
            )
            if attempt == attempts:
                return {
                    "command_status": "inconclusive_timeout",
                    "return_code": None,
                    "attempt": attempt,
                    "stdout_tail": completed["stdout"][-12_000:],
                    "stderr_tail": completed["stderr"][-12_000:],
                    "process_tree_terminated": completed[
                        "process_tree_terminated"
                    ],
                }
            continue
        if completed["return_code"] == 0:
            return {
                "command_status": "completed",
                "return_code": 0,
                "attempt": attempt,
                "stdout_tail": completed["stdout"][-12000:],
                "stderr_tail": completed["stderr"][-12000:],
                "process_tree_terminated": False,
            }
        if completed["return_code"] == 2:
            # Exit code 2 is a usage/argparse error: the command never ran its
            # workload. That is a hard failure, not an inconclusive timeout -
            # recording it as one would trigger timeout-doubling recovery and
            # hide a broken command definition. Usage errors do not heal with
            # retries, so fail immediately.
            raise RuntimeError(
                "research lane command rejected its invocation (exit code 2): "
                f"command={command}, stderr={completed['stderr'][-4000:]}"
            )
        last_error = (
            f"return_code={completed['return_code']}, "
            f"stderr={completed['stderr'][-4000:]}"
        )
        print(
            json.dumps(
                {
                    "warning": "research_lane_nonzero",
                    "attempt": attempt,
                    "error": last_error,
                }
            ),
            file=sys.stderr,
        )
    raise RuntimeError(
        f"research lane failed after {attempts} attempt(s): command={command}, last_error={last_error}"
    )


def _acquire_lock() -> str:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    process_started_at_utc = _process_started_at_utc(os.getpid())
    if process_started_at_utc is None:
        raise RuntimeError(
            "cannot acquire acceleration lock without a verifiable process start time: "
            f"pid={os.getpid()}"
        )
    for _attempt in range(3):
        if LOCK_PATH.exists():
            lock_age_seconds = _lock_age_seconds()
            prior_payload = _read_lock_payload()
            if prior_payload is None:
                if lock_age_seconds < LEGACY_OR_CORRUPT_LOCK_STALE_SECONDS:
                    raise RuntimeError(
                        "acceleration lock is unreadable and was preserved: "
                        f"lock={LOCK_PATH}, age_seconds={lock_age_seconds:.3f}"
                    )
                LOCK_PATH.unlink(missing_ok=True)
                continue
            lock_pid = prior_payload.get("pid")
            if (
                not isinstance(lock_pid, int)
                or isinstance(lock_pid, bool)
                or lock_pid <= 0
            ):
                if lock_age_seconds < LEGACY_OR_CORRUPT_LOCK_STALE_SECONDS:
                    raise RuntimeError(
                        "acceleration lock has an invalid pid and was preserved: "
                        f"lock={LOCK_PATH}, pid={lock_pid}, "
                        f"age_seconds={lock_age_seconds:.3f}"
                    )
                LOCK_PATH.unlink(missing_ok=True)
                continue
            if _pid_running(lock_pid):
                expected_start = prior_payload.get("process_started_at_utc")
                if (
                    expected_start is not None
                    and not _valid_process_start_timestamp(expected_start)
                    and lock_age_seconds < LEGACY_OR_CORRUPT_LOCK_STALE_SECONDS
                ):
                    raise RuntimeError(
                        "acceleration lock has an invalid process identity and was preserved: "
                        f"lock={LOCK_PATH}, pid={lock_pid}, "
                        f"age_seconds={lock_age_seconds:.3f}"
                    )
                if _process_identity_matches(lock_pid, expected_start):
                    raise RuntimeError(
                        "acceleration cycle already running: "
                        f"lock={LOCK_PATH}, pid={lock_pid}"
                    )
                if (
                    expected_start is None
                    and lock_age_seconds < LEGACY_OR_CORRUPT_LOCK_STALE_SECONDS
                ):
                    raise RuntimeError(
                        "legacy acceleration cycle lock has a live pid and was preserved: "
                        f"lock={LOCK_PATH}, pid={lock_pid}, "
                        f"age_seconds={lock_age_seconds:.3f}"
                    )
            LOCK_PATH.unlink(missing_ok=True)
            continue
        lock_id = str(uuid.uuid4())
        try:
            descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
            lock_file.write(
                json.dumps(
                    {
                        "lock_id": lock_id,
                        "pid": os.getpid(),
                        "process_started_at_utc": process_started_at_utc,
                        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            lock_file.flush()
            os.fsync(lock_file.fileno())
        return lock_id
    raise RuntimeError(
        f"failed to acquire acceleration lock after stale-lock recovery: lock={LOCK_PATH}"
    )


def _release_lock(lock_id: str) -> None:
    payload = _read_lock_payload()
    if payload is None or payload.get("lock_id") != lock_id:
        return
    LOCK_PATH.unlink(missing_ok=True)


def _active_supervisor_owner() -> int | None:
    if not SUPERVISOR_LOCK_PATH.exists():
        return None
    try:
        payload = json.loads(SUPERVISOR_LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"supervisor lock is unreadable and was preserved: lock={SUPERVISOR_LOCK_PATH}"
        ) from error
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"supervisor lock must be a JSON object: lock={SUPERVISOR_LOCK_PATH}"
        )
    owner = payload.get("pid")
    if not isinstance(owner, int) or isinstance(owner, bool) or owner <= 0:
        raise RuntimeError(
            f"supervisor lock has an invalid pid and was preserved: lock={SUPERVISOR_LOCK_PATH}, pid={owner}"
        )
    return owner if _pid_running(owner) else None


def _string_mapping(record: dict[str, Any], key: str) -> dict[str, str]:
    value = record.get(key)
    if not isinstance(value, dict):
        return {}
    return {
        str(item_key): item_value
        for item_key, item_value in value.items()
        if isinstance(item_value, str) and item_value
    }


def _record_mapping(record: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    value = record.get(key)
    if not isinstance(value, dict):
        return {}
    return {
        str(item_key): dict(item_value)
        for item_key, item_value in value.items()
        if isinstance(item_value, dict)
    }


def _newer_verified_artifact_completion_utc(
    lane_id: str,
    evidence: LaneEvidenceStatus,
    prior_attempt_utc: str | None,
    prior_status: str,
) -> str | None:
    timestamp_key = EVIDENCE_RECOVERY_TIMESTAMP_KEYS.get(lane_id)
    if (
        timestamp_key is None
        or prior_status not in EVIDENCE_RECOVERY_PRIOR_STATUSES
        or not evidence["verified_complete"]
        or prior_attempt_utc is None
    ):
        return None
    artifact_path = Path(evidence["artifact_path"])
    artifact, availability = read_optional_json(artifact_path)
    if availability != "available":
        return None
    raw_completion = artifact.get(timestamp_key)
    if not isinstance(raw_completion, str) or not raw_completion:
        return None
    completion = datetime.fromisoformat(raw_completion.replace("Z", "+00:00"))
    prior_attempt = datetime.fromisoformat(prior_attempt_utc.replace("Z", "+00:00"))
    if completion.tzinfo is None or prior_attempt.tzinfo is None:
        raise ValueError(
            "evidence recovery timestamps must be timezone-aware: "
            f"lane_id={lane_id}, artifact={artifact_path}, timestamp_key={timestamp_key}"
        )
    completion_utc = completion.astimezone(timezone.utc)
    prior_attempt_normalized = prior_attempt.astimezone(timezone.utc)
    if completion_utc <= prior_attempt_normalized:
        return None
    return completion_utc.isoformat()


def _reconcile_evidence_state(
    state: dict[str, Any],
    evidence_by_lane: dict[str, LaneEvidenceStatus],
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    last_attempt = _string_mapping(state, "last_attempt_utc")
    last_success = _string_mapping(state, "last_success_utc")
    lane_statuses = _record_mapping(state, "lane_statuses")
    legacy_state = (
        str(state.get("schedule_state_version", "")) != SCHEDULE_STATE_VERSION
    )
    for lane_id, evidence in evidence_by_lane.items():
        prior_success = last_success.get(lane_id)
        if lane_id not in last_attempt and prior_success is not None:
            last_attempt[lane_id] = prior_success
        if evidence["verified_complete"]:
            prior_status_record = lane_statuses.get(lane_id, {})
            prior_status = str(prior_status_record.get("status", "unknown"))
            prior_attempt_utc = last_attempt.get(lane_id)
            recovered_completion_utc = _newer_verified_artifact_completion_utc(
                lane_id,
                evidence,
                prior_attempt_utc,
                prior_status,
            )
            if recovered_completion_utc is not None:
                last_attempt[lane_id] = recovered_completion_utc
                last_success[lane_id] = recovered_completion_utc
                lane_statuses[lane_id] = {
                    "status": "completed",
                    "completed_utc": recovered_completion_utc,
                    "error": "",
                    "evidence_verification": evidence,
                    "reconciled_from_legacy_state": False,
                    "reconciled_from_newer_verified_artifact": True,
                    "reconciliation_source": {
                        "artifact_path": evidence["artifact_path"],
                        "timestamp_key": EVIDENCE_RECOVERY_TIMESTAMP_KEYS[lane_id],
                        "prior_status": prior_status,
                        "prior_attempt_utc": prior_attempt_utc,
                    },
                }
            continue
        if legacy_state and prior_success is not None:
            last_success.pop(lane_id, None)
        lane_statuses[lane_id] = {
            "status": "degraded_evidence",
            "completed_utc": last_attempt.get(lane_id, ""),
            "error": "",
            "evidence_verification": evidence,
            "reconciled_from_legacy_state": legacy_state and prior_success is not None,
        }
    for lane_id, completed_utc in last_success.items():
        if lane_id not in last_attempt:
            last_attempt[lane_id] = completed_utc
    return last_attempt, last_success, lane_statuses


def _record_completed_lane(
    last_attempt: dict[str, str],
    last_success: dict[str, str],
    lane_statuses: dict[str, dict[str, Any]],
    lane_id: str,
    completed_utc: str,
    evidence: LaneEvidenceStatus,
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]], str]:
    updated_attempt = dict(last_attempt)
    updated_success = dict(last_success)
    updated_statuses = {key: dict(value) for key, value in lane_statuses.items()}
    updated_attempt[lane_id] = completed_utc
    outcome_status = (
        "completed" if evidence["verified_complete"] else "degraded_evidence"
    )
    if evidence["verified_complete"]:
        updated_success[lane_id] = completed_utc
    updated_statuses[lane_id] = {
        "status": outcome_status,
        "completed_utc": completed_utc,
        "error": "",
        "evidence_verification": evidence,
        "reconciled_from_legacy_state": False,
    }
    return updated_attempt, updated_success, updated_statuses, outcome_status


def _record_started_lane(
    last_attempt: dict[str, str],
    last_success: dict[str, str],
    lane_statuses: dict[str, dict[str, Any]],
    lane_id: str,
    attempt_started_utc: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    updated_attempt = dict(last_attempt)
    updated_success = dict(last_success)
    updated_statuses = {key: dict(value) for key, value in lane_statuses.items()}
    updated_attempt[lane_id] = attempt_started_utc
    updated_statuses[lane_id] = {
        "status": "attempt_started",
        "attempt_started_utc": attempt_started_utc,
        "completed_utc": "",
        "error": "",
        "evidence_verification": evaluate_lane_evidence(lane_id),
        "reconciled_from_legacy_state": False,
    }
    return updated_attempt, updated_success, updated_statuses


def _record_failed_lane(
    last_attempt: dict[str, str],
    last_success: dict[str, str],
    lane_statuses: dict[str, dict[str, Any]],
    lane_id: str,
    completed_utc: str,
    error: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    updated_attempt = dict(last_attempt)
    updated_success = dict(last_success)
    updated_statuses = {key: dict(value) for key, value in lane_statuses.items()}
    updated_attempt[lane_id] = completed_utc
    updated_statuses[lane_id] = {
        "status": "failed",
        "completed_utc": completed_utc,
        "error": error,
        "evidence_verification": evaluate_lane_evidence(lane_id),
        "reconciled_from_legacy_state": False,
    }
    return updated_attempt, updated_success, updated_statuses


def _record_inconclusive_lane(
    last_attempt: dict[str, str],
    last_success: dict[str, str],
    lane_statuses: dict[str, dict[str, Any]],
    lane_id: str,
    completed_utc: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    updated_attempt = dict(last_attempt)
    updated_success = dict(last_success)
    updated_statuses = {key: dict(value) for key, value in lane_statuses.items()}
    updated_attempt[lane_id] = completed_utc
    updated_statuses[lane_id] = {
        "status": "inconclusive_timeout",
        "completed_utc": completed_utc,
        "error": "execution exceeded its truthful time envelope; no pass was recorded",
        "evidence_verification": evaluate_lane_evidence(lane_id),
        "reconciled_from_legacy_state": False,
    }
    return updated_attempt, updated_success, updated_statuses


def _schedule_state_record(
    previous_state: dict[str, Any],
    last_attempt: dict[str, str],
    last_success: dict[str, str],
    lane_statuses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    output = dict(previous_state)
    output.update(
        {
            "artifact_type": "research_acceleration_schedule_state",
            "schedule_state_version": SCHEDULE_STATE_VERSION,
            "last_attempt_utc": last_attempt,
            "last_success_utc": last_success,
            "lane_statuses": lane_statuses,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    return output


def run_acceleration_cycle(
    repo_root: Path, mode: str, lane_ids: tuple[str, ...], now_utc: datetime
) -> dict[str, Any]:
    if mode not in {"plan", "execute"}:
        raise ValueError(f"mode must be plan or execute: actual={mode}")
    if mode == "plan":
        return build_schedule_plan(repo_root, now_utc, lane_ids)
    lock_id = _acquire_lock()
    try:
        supervisor_owner = _active_supervisor_owner()
        daily_ritual_active = operational_run_active(
            "daily_ritual", datetime.now(timezone.utc)
        )
        if supervisor_owner is not None:
            output = stamped(
                {
                    "artifact_type": "research_acceleration_cycle_result",
                    "cycle_version": "dopey-research-acceleration-cycle-v13",
                    "cycle_status": "deferred_active_supervisor",
                    "active_supervisor_pid": supervisor_owner,
                    "attempted_lane_ids": [],
                    "executed_lane_ids": [],
                    "verified_success_lane_ids": [],
                    "degraded_lane_ids": [],
                    "inconclusive_lane_ids": [],
                    "failed_lane_ids": [],
                    "results": [],
                    "paper_only": True,
                    "live_blocked": True,
                    "broker_commands_executed": False,
                }
            )
            write_json_atomic(CYCLE_RESULT_PATH, output)
        elif daily_ritual_active:
            output = stamped(
                {
                    "artifact_type": "research_acceleration_cycle_result",
                    "cycle_version": "dopey-research-acceleration-cycle-v13",
                    "cycle_status": "deferred_active_daily_ritual",
                    "attempted_lane_ids": [],
                    "executed_lane_ids": [],
                    "verified_success_lane_ids": [],
                    "degraded_lane_ids": [],
                    "inconclusive_lane_ids": [],
                    "failed_lane_ids": [],
                    "results": [],
                    "paper_only": True,
                    "live_blocked": True,
                    "broker_commands_executed": False,
                }
            )
            write_json_atomic(CYCLE_RESULT_PATH, output)
    except Exception:
        _release_lock(lock_id)
        raise
    if supervisor_owner is not None or daily_ritual_active:
        _release_lock(lock_id)
        return output
    try:
        state, _ = read_optional_json(SCHEDULE_STATE_PATH)
        evidence_by_lane = {
            lane_id: evaluate_lane_evidence(lane_id)
            for lane_id in LANE_EVIDENCE_CONTRACTS
        }
        last_attempt, last_success, lane_statuses = _reconcile_evidence_state(
            state, evidence_by_lane
        )
        reconciled_state = _schedule_state_record(
            state, last_attempt, last_success, lane_statuses
        )
        if reconciled_state != state:
            write_json_atomic(SCHEDULE_STATE_PATH, reconciled_state)
        plan = build_schedule_plan(repo_root, now_utc, lane_ids)
        externally_owned_due_lanes = sorted(
            set(plan["due_lane_ids"]) & set(EXTERNAL_LANE_OWNERS)
        )
        if externally_owned_due_lanes:
            raise RuntimeError(
                "acceleration plan attempted to execute externally owned lanes: "
                f"lane_ids={externally_owned_due_lanes}, owners={EXTERNAL_LANE_OWNERS}"
            )
        commands = _commands(repo_root)
        policy_by_id = {str(lane["lane_id"]): lane for lane in plan["lanes"]}
        results: list[dict[str, Any]] = []
        failed_lane_ids: list[str] = []
        inconclusive_lane_ids: list[str] = []
        degraded_lane_ids: list[str] = []
    except Exception:
        _release_lock(lock_id)
        raise
    try:
        for lane_id in plan["due_lane_ids"]:
            policy = policy_by_id[lane_id]
            attempt_started_utc = datetime.now(timezone.utc).isoformat()
            last_attempt, last_success, lane_statuses = _record_started_lane(
                last_attempt,
                last_success,
                lane_statuses,
                lane_id,
                attempt_started_utc,
            )
            write_json_atomic(
                SCHEDULE_STATE_PATH,
                _schedule_state_record(
                    state,
                    last_attempt,
                    last_success,
                    lane_statuses,
                ),
            )
            try:
                result = _run_command(
                    commands[lane_id],
                    repo_root,
                    int(policy["timeout_seconds"]),
                    int(policy["retries"]),
                )
            except RuntimeError as error:
                completed_utc = datetime.now(timezone.utc).isoformat()
                error_text = str(error)
                last_attempt, last_success, lane_statuses = _record_failed_lane(
                    last_attempt,
                    last_success,
                    lane_statuses,
                    lane_id,
                    completed_utc,
                    error_text,
                )
                failed_lane_ids.append(lane_id)
                results.append(
                    {
                        "lane_id": lane_id,
                        "lane_status": "failed",
                        "completed_utc": completed_utc,
                        "return_code": None,
                        "attempt": int(policy["retries"]),
                        "stdout_tail": "",
                        "stderr_tail": "",
                        "error": error_text,
                        "evidence_verification": evaluate_lane_evidence(lane_id),
                    }
                )
                write_json_atomic(
                    SCHEDULE_STATE_PATH,
                    _schedule_state_record(
                        state, last_attempt, last_success, lane_statuses
                    ),
                )
                continue
            completed_utc = datetime.now(timezone.utc).isoformat()
            if result["command_status"] == "inconclusive_timeout":
                last_attempt, last_success, lane_statuses = _record_inconclusive_lane(
                    last_attempt,
                    last_success,
                    lane_statuses,
                    lane_id,
                    completed_utc,
                )
                inconclusive_lane_ids.append(lane_id)
                evidence = evaluate_lane_evidence(lane_id)
                results.append(
                    {
                        "lane_id": lane_id,
                        "lane_status": "inconclusive_timeout",
                        "completed_utc": completed_utc,
                        "error": "execution exceeded its truthful time envelope; no pass was recorded",
                        "evidence_verification": evidence,
                        **result,
                    }
                )
                write_json_atomic(
                    SCHEDULE_STATE_PATH,
                    _schedule_state_record(
                        state, last_attempt, last_success, lane_statuses
                    ),
                )
                continue
            evidence = evaluate_lane_evidence(lane_id)
            last_attempt, last_success, lane_statuses, outcome_status = (
                _record_completed_lane(
                    last_attempt,
                    last_success,
                    lane_statuses,
                    lane_id,
                    completed_utc,
                    evidence,
                )
            )
            if outcome_status == "degraded_evidence":
                degraded_lane_ids.append(lane_id)
            write_json_atomic(
                SCHEDULE_STATE_PATH,
                _schedule_state_record(
                    state, last_attempt, last_success, lane_statuses
                ),
            )
            results.append(
                {
                    "lane_id": lane_id,
                    "lane_status": outcome_status,
                    "completed_utc": completed_utc,
                    "error": "",
                    "evidence_verification": evidence,
                    **result,
                }
            )
    finally:
        _release_lock(lock_id)
    if failed_lane_ids:
        cycle_status = "completed_with_failures"
    elif inconclusive_lane_ids:
        cycle_status = "completed_inconclusive_timeout"
    elif degraded_lane_ids:
        cycle_status = "completed_with_degraded_evidence"
    elif results:
        cycle_status = "completed"
    else:
        cycle_status = "nothing_due"
    output = stamped(
        {
            "artifact_type": "research_acceleration_cycle_result",
            "cycle_version": "dopey-research-acceleration-cycle-v13",
            "cycle_status": cycle_status,
            "attempted_lane_ids": [record["lane_id"] for record in results],
            "executed_lane_ids": [
                record["lane_id"]
                for record in results
                if record["lane_status"] != "failed"
            ],
            "verified_success_lane_ids": [
                record["lane_id"]
                for record in results
                if record["lane_status"] == "completed"
            ],
            "degraded_lane_ids": degraded_lane_ids,
            "inconclusive_lane_ids": inconclusive_lane_ids,
            "failed_lane_ids": failed_lane_ids,
            "results": results,
            "paper_only": True,
            "live_blocked": True,
            "broker_commands_executed": False,
        }
    )
    write_json_atomic(CYCLE_RESULT_PATH, output)
    return output
