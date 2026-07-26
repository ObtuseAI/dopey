"""State-change-gated autonomous coaching and deterministic experiment cycle."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Literal

from dopey.evolution.coach_bridge import (
    REFERENCE_PATTERN,
    build_quarantined_coach_proposal_batch,
)
from dopey.protocols.identity import canonical_hash
from dopey_analysis.two_coach_engine import (
    build_evidence_coach_packet,
    run_two_coach_review,
)
from dopey_chart_vision.run_channel_containment_audit import (
    run_channel_containment_audit,
)
from dopey_research_pipeline.artifact_io import append_jsonl, write_json_atomic

from .run_coach_bridge import persist_coach_batch


COACHED_EVOLUTION_VERSION: Final[str] = "dopey-autonomous-coached-evolution-v1"
COMPLETE_STATUS: Final[str] = "complete"
SessionAction = Literal["generated_changed_packet", "reused_unchanged_packet"]


class CoachedEvolutionError(RuntimeError):
    """Raised when autonomous coaching cannot preserve its evidence contract."""


def _pid_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise CoachedEvolutionError(
                "SystemRoot is required to verify a Windows coach lock owner"
            )
        completed = subprocess.run(
            [
                str(Path(system_root) / "System32" / "tasklist.exe"),
                "/FI",
                f"PID eq {process_id}",
                "/FO",
                "CSV",
                "/NH",
            ],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            raise CoachedEvolutionError(
                "coach process-liveness check failed: "
                f"pid={process_id}, return_code={completed.returncode}, "
                f"stderr={completed.stderr[-2_000:]}"
            )
        return any(
            len(row) >= 2 and row[1].strip() == str(process_id)
            for row in csv.reader(completed.stdout.splitlines())
        )
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _acquire_operation_lock(lock_path: Path) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            descriptor = os.open(
                lock_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            existing = _load_json_object(lock_path)
            raw_pid = existing.get("pid")
            if isinstance(raw_pid, bool) or not isinstance(raw_pid, int):
                raise CoachedEvolutionError(
                    f"coached evolution lock has an invalid pid: path={lock_path}"
                )
            if _pid_running(raw_pid):
                raise CoachedEvolutionError(
                    f"coached evolution is already running: path={lock_path}, pid={raw_pid}"
                )
            try:
                lock_path.unlink()
            except FileNotFoundError:
                continue
            continue
        payload = json.dumps(
            {
                "artifact_type": "coached_evolution_operation_lock",
                "pid": os.getpid(),
                "acquired_utc": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        ).encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
        return descriptor
    raise CoachedEvolutionError(
        f"coached evolution could not acquire its operation lock: path={lock_path}"
    )


def _release_operation_lock(descriptor: int, lock_path: Path) -> None:
    os.close(descriptor)
    try:
        lock_path.unlink()
    except FileNotFoundError as error:
        raise CoachedEvolutionError(
            f"coached evolution lock disappeared before release: path={lock_path}"
        ) from error


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoachedEvolutionError(
            f"coached evolution could not read JSON evidence: path={path}, error={error}"
        ) from error
    if not isinstance(value, dict):
        raise CoachedEvolutionError(
            f"coached evolution requires a JSON object: path={path}, actual={type(value).__name__}"
        )
    return value


def _load_optional_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_object(path)


def _normalized_utc(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        raise ValueError("coached evolution now_utc must be timezone-aware")
    return now_utc.astimezone(timezone.utc)


def _session_path(coach_root: Path, symbol: str, timeframe: str) -> Path:
    return coach_root / f"{symbol.strip().lower()}_{timeframe.strip().lower()}.json"


def session_matches_packet(
    session: Mapping[str, Any],
    packet: Mapping[str, Any],
    head_coach_id: str,
) -> bool:
    """Return whether a saved session is the exact requested deterministic packet."""

    evidence = session.get("evidence_coach")
    topology = session.get("topology")
    if not isinstance(evidence, Mapping) or not isinstance(topology, Mapping):
        return False
    return (
        session.get("artifact_type") == "two_coach_chart_research_session"
        and session.get("session_id") == packet.get("session_id")
        and evidence.get("packet_hash") == packet.get("packet_hash")
        and topology.get("head_coach_id") == head_coach_id
        and topology.get("runtime_fallback_allowed") is False
    )


def count_paid_sessions_on_utc_date(ledger_path: Path, utc_date: str) -> int:
    """Count paid two-coach attempts, including partial paid failures."""

    if not ledger_path.exists():
        return 0
    count = 0
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value: Any = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise CoachedEvolutionError(
                    "two-coach session ledger is malformed: "
                    f"path={ledger_path}, line={line_number}, error={error}"
                ) from error
            if not isinstance(value, dict):
                raise CoachedEvolutionError(
                    "two-coach session ledger record must be an object: "
                    f"path={ledger_path}, line={line_number}"
                )
            artifact_type = value.get("artifact_type")
            if artifact_type not in {
                "two_coach_chart_research_session",
                "two_coach_session_failure",
            }:
                continue
            timestamp = value.get("generated_utc", value.get("recorded_utc"))
            head_coach = value.get("head_coach")
            paid_response_count = (
                head_coach.get("paid_response_count")
                if isinstance(head_coach, dict)
                else value.get("paid_response_count")
            )
            if not isinstance(timestamp, str):
                continue
            if (
                timestamp.startswith(f"{utc_date}T")
                and isinstance(paid_response_count, int)
                and not isinstance(paid_response_count, bool)
                and paid_response_count > 0
            ):
                count += 1
    return count


def _direct_trend_hypothesis_count(session: Mapping[str, Any]) -> int:
    evidence = session.get("evidence_coach")
    head_coach = session.get("head_coach")
    if not isinstance(evidence, Mapping) or not isinstance(head_coach, Mapping):
        raise CoachedEvolutionError(
            "coached session lacks evidence or head-coach objects"
        )
    structures = evidence.get("structure_registry")
    analysis = head_coach.get("structured_analysis")
    if not isinstance(structures, list) or not isinstance(analysis, Mapping):
        raise CoachedEvolutionError(
            "coached session lacks structure registry or analysis"
        )
    hypotheses = analysis.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise CoachedEvolutionError("coached session hypotheses must be an array")
    trend_refs = {
        str(record["structure_id"])
        for record in structures
        if isinstance(record, Mapping)
        and record.get("structure_type") == "trend_channel"
        and isinstance(record.get("structure_id"), str)
    }
    direct_count = 0
    for index, hypothesis in enumerate(hypotheses):
        if not isinstance(hypothesis, Mapping):
            raise CoachedEvolutionError(
                f"coached hypothesis must be an object: index={index}"
            )
        texts = [value for value in hypothesis.values() if isinstance(value, str)]
        direct_refs = {
            reference for text in texts for reference in REFERENCE_PATTERN.findall(text)
        }
        if trend_refs.intersection(direct_refs):
            direct_count += 1
    return direct_count


def _numeric_usage(session: Mapping[str, Any], key: str) -> float:
    head_coach = session.get("head_coach")
    usage = head_coach.get("usage") if isinstance(head_coach, Mapping) else None
    value = usage.get(key) if isinstance(usage, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoachedEvolutionError(
            f"coached session usage is missing numeric field: field={key}, value={value!r}"
        )
    return float(value)


def _paid_response_count(session: Mapping[str, Any]) -> int:
    head_coach = session.get("head_coach")
    value = (
        head_coach.get("paid_response_count")
        if isinstance(head_coach, Mapping)
        else None
    )
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CoachedEvolutionError(
            f"coached session paid response count is invalid: value={value!r}"
        )
    return value


def _append_content_addressed(
    path: Path, record: dict[str, Any], identity_key: str
) -> bool:
    identity = record.get(identity_key)
    if not isinstance(identity, str) or not identity:
        raise CoachedEvolutionError(
            f"content-addressed record lacks identity: key={identity_key}"
        )
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    value: Any = json.loads(stripped)
                except json.JSONDecodeError as error:
                    raise CoachedEvolutionError(
                        f"coached evolution ledger is malformed: path={path}, line={line_number}"
                    ) from error
                if not isinstance(value, dict) or value.get(identity_key) != identity:
                    continue
                if canonical_hash(value) != canonical_hash(record):
                    raise CoachedEvolutionError(
                        f"coached evolution identity conflict: path={path}, {identity_key}={identity}"
                    )
                return False
    append_jsonl(path, record)
    return True


def _blocked_run(
    output_root: Path,
    completed_utc: str,
    packet: Mapping[str, Any],
    head_coach_id: str,
    paid_session_count: int,
    daily_new_session_limit: int,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "artifact_type": "coached_evolution_run",
        "schema_version": COACHED_EVOLUTION_VERSION,
        "run_status": "blocked_daily_new_session_limit",
        "outcome_status": "blocked_changed_packet_pending_next_utc_budget_window",
        "completed_utc": completed_utc,
        "source_packet_hash": str(packet["packet_hash"]),
        "requested_session_id": str(packet["session_id"]),
        "head_coach_id": head_coach_id,
        "paid_session_count_utc_date": paid_session_count,
        "daily_new_session_limit": daily_new_session_limit,
        "network_call_performed": False,
        "new_paid_response_count": 0,
        "new_reported_openrouter_cost_usd": 0.0,
        "automatic_apply_allowed": False,
        "strategy_mutation_allowed": False,
        "strategy_promotion_allowed": False,
        "broker_access": False,
        "order_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "reproducibility_hash": canonical_hash(body)}
    write_json_atomic(output_root / "latest_run.json", output)
    append_jsonl(output_root / "run_ledger.jsonl", output)
    return output


def _persist_cycle(
    output_root: Path,
    session: Mapping[str, Any],
    batch: Mapping[str, Any],
    experiment: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    session_head_coach = session.get("head_coach")
    if not isinstance(session_head_coach, Mapping):
        raise CoachedEvolutionError("coached session lacks head coach")
    body: dict[str, Any] = {
        "artifact_type": "coached_evolution_cycle",
        "schema_version": COACHED_EVOLUTION_VERSION,
        "cycle_status": COMPLETE_STATUS,
        "outcome_status": (
            "complete_quarantined_with_deterministic_experiment"
            if experiment.get("experiment_status") == "complete"
            else "complete_quarantined_no_applicable_deterministic_experiment"
        ),
        "source_session_id": str(session["session_id"]),
        "source_session_hash": str(session["session_hash"]),
        "source_session_status": str(session["status"]),
        "source_session_verdict": str(session["verdict"]),
        "head_coach_id": str(session_head_coach["head_coach_id"]),
        "head_coach_model": str(session_head_coach["head_coach_model"]),
        "source_paid_response_count": _paid_response_count(session),
        "source_reported_openrouter_cost_usd": _numeric_usage(session, "cost"),
        "proposal_batch_id": str(batch["batch_id"]),
        "proposal_batch_hash": str(batch["batch_hash"]),
        "proposal_count": int(batch["proposal_count"]),
        "linked_proposal_count": int(batch["linked_proposal_count"]),
        "blocked_proposal_count": int(batch["blocked_proposal_count"]),
        "evidence_weight": float(batch["evidence_weight"]),
        "mutation_targets_resolved": int(batch["mutation_targets_resolved"]),
        "deterministic_experiment": dict(experiment),
        "next_gate": str(batch["next_gate"]),
        "automatic_apply_allowed": False,
        "strategy_mutation_allowed": False,
        "code_mutation_allowed": False,
        "prompt_mutation_allowed": False,
        "strategy_promotion_allowed": False,
        "broker_access": False,
        "order_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
    cycle_hash = canonical_hash(body)
    output = {
        **body,
        "cycle_hash": cycle_hash,
        "cycle_id": f"coached-evolution:{cycle_hash[:24]}",
    }
    cycle_path = output_root / "cycles" / f"{cycle_hash}.json"
    if cycle_path.exists():
        existing = _load_json_object(cycle_path)
        if existing != output:
            raise CoachedEvolutionError(
                f"coached evolution cycle identity conflict: path={cycle_path}"
            )
    else:
        write_json_atomic(cycle_path, output)
    appended = _append_content_addressed(
        output_root / "cycle_ledger.jsonl",
        output,
        "cycle_id",
    )
    write_json_atomic(output_root / "latest_cycle.json", output)
    return output, appended


def _run_coached_evolution_cycle_locked(
    repository_root: Path,
    symbol: str,
    timeframe: str,
    head_coach_id: str,
    timeout_seconds: int,
    daily_new_session_limit: int,
    output_root: Path,
    coach_root: Path,
    proposal_root: Path,
    history_manifest: Path,
    experiment_root: Path,
    now_utc: datetime,
) -> dict[str, Any]:
    """Run one bounded coach, quarantine, and deterministic-experiment operation."""

    normalized_now = _normalized_utc(now_utc)
    if timeout_seconds <= 0:
        raise ValueError("coached evolution timeout_seconds must be positive")
    if daily_new_session_limit <= 0:
        raise ValueError("coached evolution daily_new_session_limit must be positive")
    normalized_root = repository_root.resolve()
    normalized_head_coach = head_coach_id.strip().casefold()
    packet = build_evidence_coach_packet(
        normalized_root,
        symbol,
        timeframe,
        normalized_head_coach,
    )
    normalized_coach_root = coach_root.resolve()
    latest_session_path = _session_path(normalized_coach_root, symbol, timeframe)
    saved_session = _load_optional_json_object(latest_session_path)
    ledger_path = normalized_coach_root.parent / "session_ledger.jsonl"
    utc_date = normalized_now.date().isoformat()
    paid_session_count = count_paid_sessions_on_utc_date(ledger_path, utc_date)
    session_action: SessionAction
    if saved_session is not None and session_matches_packet(
        saved_session, packet, normalized_head_coach
    ):
        build_quarantined_coach_proposal_batch((saved_session,))
        session = saved_session
        session_action = "reused_unchanged_packet"
        new_paid_response_count = 0
        new_reported_cost = 0.0
    else:
        if paid_session_count >= daily_new_session_limit:
            return _blocked_run(
                output_root,
                normalized_now.isoformat(),
                packet,
                normalized_head_coach,
                paid_session_count,
                daily_new_session_limit,
            )
        session = run_two_coach_review(
            normalized_root,
            symbol,
            timeframe,
            normalized_head_coach,
            timeout_seconds,
        )
        if not session_matches_packet(session, packet, normalized_head_coach):
            raise CoachedEvolutionError(
                "generated coach session does not match its deterministic source packet"
            )
        build_quarantined_coach_proposal_batch((session,))
        session_action = "generated_changed_packet"
        new_paid_response_count = _paid_response_count(session)
        new_reported_cost = _numeric_usage(session, "cost")

    bridge_result = persist_coach_batch((dict(session),), proposal_root)
    batch = _load_json_object(proposal_root / "latest_batch.json")
    batch_sessions = batch.get("sessions")
    if (
        batch.get("source_session_count") != 1
        or not isinstance(batch_sessions, list)
        or len(batch_sessions) != 1
        or not isinstance(batch_sessions[0], Mapping)
        or batch_sessions[0].get("source_session_hash") != session.get("session_hash")
    ):
        raise CoachedEvolutionError(
            "persisted coach proposal batch is not exactly linked to the current session"
        )
    direct_trend_hypothesis_count = _direct_trend_hypothesis_count(session)
    if direct_trend_hypothesis_count == 0:
        experiment: dict[str, Any] = {
            "experiment_id": "channel_containment",
            "experiment_status": "not_applicable_no_direct_trend_channel_hypothesis",
            "automatic_activation_allowed": False,
            "strategy_promotion_allowed": False,
        }
    else:
        audit_result = run_channel_containment_audit(
            latest_session_path,
            history_manifest,
            experiment_root,
        )
        experiment = {
            "experiment_id": "channel_containment",
            "experiment_status": str(audit_result["audit_status"]),
            "outcome_status": str(audit_result["outcome_status"]),
            "audit_hash": str(audit_result["audit_hash"]),
            "artifact_path": str(audit_result["artifact_path"]),
            "latest_containment_state": str(audit_result["latest_containment_state"]),
            "automatic_activation_allowed": False,
            "strategy_promotion_allowed": False,
        }
    cycle, cycle_appended = _persist_cycle(output_root, session, batch, experiment)
    completed_utc = datetime.now(timezone.utc).isoformat()
    run_body: dict[str, Any] = {
        "artifact_type": "coached_evolution_run",
        "schema_version": COACHED_EVOLUTION_VERSION,
        "run_status": COMPLETE_STATUS,
        "outcome_status": str(cycle["outcome_status"]),
        "completed_utc": completed_utc,
        "session_action": session_action,
        "network_call_performed": session_action == "generated_changed_packet",
        "new_paid_response_count": new_paid_response_count,
        "new_reported_openrouter_cost_usd": new_reported_cost,
        "paid_session_count_utc_date_before_run": paid_session_count,
        "daily_new_session_limit": daily_new_session_limit,
        "source_session_id": str(session["session_id"]),
        "source_session_hash": str(session["session_hash"]),
        "proposal_batch_id": str(batch["batch_id"]),
        "proposal_batch_ledger_appended": bool(bridge_result["ledger_appended"]),
        "cycle_id": str(cycle["cycle_id"]),
        "cycle_hash": str(cycle["cycle_hash"]),
        "cycle_ledger_appended": cycle_appended,
        "automatic_apply_allowed": False,
        "strategy_mutation_allowed": False,
        "strategy_promotion_allowed": False,
        "broker_access": False,
        "order_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
    run_output = {**run_body, "reproducibility_hash": canonical_hash(run_body)}
    write_json_atomic(output_root / "latest_run.json", run_output)
    append_jsonl(output_root / "run_ledger.jsonl", run_output)
    return run_output


def run_coached_evolution_cycle(
    repository_root: Path,
    symbol: str,
    timeframe: str,
    head_coach_id: str,
    timeout_seconds: int,
    daily_new_session_limit: int,
    output_root: Path,
    coach_root: Path,
    proposal_root: Path,
    history_manifest: Path,
    experiment_root: Path,
    now_utc: datetime,
) -> dict[str, Any]:
    """Run one serialized autonomous coached-evolution operation."""

    normalized_output_root = output_root.resolve()
    lock_path = normalized_output_root / ".coached_evolution_cycle.lock"
    descriptor = _acquire_operation_lock(lock_path)
    try:
        return _run_coached_evolution_cycle_locked(
            repository_root,
            symbol,
            timeframe,
            head_coach_id,
            timeout_seconds,
            daily_new_session_limit,
            normalized_output_root,
            coach_root,
            proposal_root,
            history_manifest,
            experiment_root,
            now_utc,
        )
    finally:
        _release_operation_lock(descriptor, lock_path)
