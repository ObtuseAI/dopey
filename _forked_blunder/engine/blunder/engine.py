"""Blunder recursive work loop: plan -> mock -> execute -> validate -> repair -> ledger -> learn.

A Task supplies the task-specific mock/execute/validate/repair steps; the engine drives them through the
proof-gated loop and emits an append-only proof-ledger entry. Execution is sandboxed to a per-run workdir;
risky/irreversible packets BLOCK unless an operator gate is supplied.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import parse_proof_ledger
from .core import (
    FinalStatus, MockResult, ValidationResult, WorkPacket, sha256_obj,
)

MAX_REPAIR_ATTEMPTS = 3


# ----------------------------------------------------------------------------- plan engine
def make_plan(packet: WorkPacket) -> dict:
    """Short, executable plan (not endless doctrine)."""
    steps = [
        "mock/dry-run the change and compare to expected outputs",
        "execute the safest real next step inside the sandboxed workdir",
        "validate against the declared validation_targets",
        "repair (bounded) if validation fails, else record proof",
    ]
    return {
        "goal": packet.objective or packet.title,
        "decomposition": [packet.title, *packet.expected_outputs],
        "steps": steps,
        "expected_artifacts": list(packet.expected_outputs),
        "predicted_failure_points": [
            "missing/extra required fields in the produced artifact",
            "schema or golden-fixture mismatch",
            "non-zero exit / unwritten artifact",
        ],
        "validation_strategy": list(packet.validation_targets) or ["schema_validation", "golden_fixture", "negative_test"],
        "rollback_or_containment": packet.rollback_plan or "all writes confined to the run workdir; discard workdir to roll back",
    }


# ----------------------------------------------------------------------------- Task contract
class Task:
    """Subclass and implement the task-specific steps. All file effects MUST stay inside `workdir`."""

    def mock(self, packet: WorkPacket, workdir: Path) -> tuple[MockResult, dict]:
        raise NotImplementedError

    def execute(self, packet: WorkPacket, workdir: Path) -> dict:
        """Return an execution_result dict (commands_run/files_touched/artifacts_created/diff_summary/
        stdout_stderr_summary/exit_codes/duration/environment_notes)."""
        raise NotImplementedError

    def validate(self, packet: WorkPacket, workdir: Path) -> tuple[ValidationResult, dict]:
        """Return (result, detail). detail SHOULD include 'failures': [..] and 'test_results': {..}."""
        raise NotImplementedError

    def repair(self, packet: WorkPacket, workdir: Path, failures: list, attempt: int) -> dict:
        """Attempt a bounded fix based on validation failures; return a repair record."""
        return {"attempt": attempt, "action": "no_repair_available", "patched": False}


# ----------------------------------------------------------------------------- proof ledger (append-only)
@dataclass
class ProofEntry:
    run_id: str
    task_id: str
    timestamp: str
    input_hash: str
    plan_hash: str
    mock_trial_result: str
    execution_result: dict
    validation_result: str
    repair_attempts: int
    artifacts: list
    diffs: list
    test_results: dict
    final_status: str
    lessons_candidate: list
    promotion_candidate: list
    limitations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class ProofLedger:
    """Append-only JSONL proof ledger with a consistency self-check."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: ProofEntry) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def consistency_check(self) -> dict:
        text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        return parse_proof_ledger(text)


# ----------------------------------------------------------------------------- learning / skill promotion
def evaluate_lessons(candidates: list[dict]) -> dict:
    """Promote a lesson only if it meets ALL criteria (real run + evidence + reusable + safe + verified)."""
    promoted, rejected = [], []
    for c in candidates:
        reasons = []
        if not c.get("from_real_run"):
            reasons.append("not from a real run")
        if not c.get("evidence"):
            reasons.append("no evidence")
        if not c.get("improved_or_prevented_failure"):
            reasons.append("did not improve/prevent failure")
        if not c.get("reusable"):
            reasons.append("not reusable")
        if c.get("weakens_safety"):
            reasons.append("would weaken safety")
        if not c.get("validator_or_replay_checked"):
            reasons.append("not validator/replay checked")
        if reasons:
            rejected.append({**c, "reject_reasons": reasons})
        else:
            promoted.append(c)
    return {"promoted": promoted, "rejected": rejected}


# ----------------------------------------------------------------------------- the loop
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(packet: WorkPacket, task: Task, workdir: Path, ledger: ProofLedger,
        run_id: str, operator_approved: bool = False) -> dict:
    """Drive one packet through the full recursive loop and append a proof entry. Returns a run report."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    plan = make_plan(packet)
    input_hash = packet.packet_hash()
    plan_hash = sha256_obj(plan)
    notes: list[str] = []

    # ---- Human gate (fail-closed) ----
    if packet.human_gate_required and not operator_approved:
        entry = ProofEntry(
            run_id=run_id, task_id=packet.task_id, timestamp=_now_iso(),
            input_hash=input_hash, plan_hash=plan_hash,
            mock_trial_result=MockResult.MOCK_BLOCKED.value, execution_result={"blocked": True},
            validation_result=ValidationResult.VALIDATION_BLOCKED.value, repair_attempts=0,
            artifacts=[], diffs=[], test_results={},
            final_status=FinalStatus.BLOCKED.value,
            lessons_candidate=[], promotion_candidate=[],
            limitations=["human gate required and not granted -> blocked before any execution"],
        )
        ledger.append(entry)
        return {"status": FinalStatus.BLOCKED.value, "entry": entry.to_dict(), "plan": plan}

    # ---- Mock trial (before any execution) ----
    mock_result, mock_detail = task.mock(packet, workdir)
    if mock_result in (MockResult.MOCK_FAIL, MockResult.MOCK_BLOCKED):
        # Do NOT blindly execute; record and stop (the plan would need repair first).
        entry = ProofEntry(
            run_id=run_id, task_id=packet.task_id, timestamp=_now_iso(),
            input_hash=input_hash, plan_hash=plan_hash,
            mock_trial_result=mock_result.value, execution_result={"skipped": "mock did not pass"},
            validation_result=ValidationResult.VALIDATION_BLOCKED.value, repair_attempts=0,
            artifacts=[], diffs=[], test_results={"mock": mock_detail},
            final_status=(FinalStatus.BLOCKED.value if mock_result == MockResult.MOCK_BLOCKED else FinalStatus.FAIL.value),
            lessons_candidate=[], promotion_candidate=[],
            limitations=["mock trial did not pass; execution withheld pending plan repair"],
        )
        ledger.append(entry)
        return {"status": entry.final_status, "entry": entry.to_dict(), "plan": plan, "mock": mock_detail}
    if mock_result == MockResult.MOCK_WARN:
        notes.append(f"mock trial warned: {mock_detail.get('summary','')}")

    # ---- Execute ----
    t0 = time.perf_counter()
    execution_result = task.execute(packet, workdir)
    execution_result.setdefault("duration", round(time.perf_counter() - t0, 4))

    # ---- Validate (+ bounded repair) ----
    val_result, val_detail = task.validate(packet, workdir)
    repair_attempts = 0
    repair_log: list[dict] = []
    while val_result == ValidationResult.VALIDATION_FAIL and repair_attempts < MAX_REPAIR_ATTEMPTS:
        repair_attempts += 1
        rec = task.repair(packet, workdir, val_detail.get("failures", []), repair_attempts)
        repair_log.append(rec)
        if not rec.get("patched"):
            break
        val_result, val_detail = task.validate(packet, workdir)

    # ---- Final status ----
    if val_result == ValidationResult.VALIDATION_PASS:
        final = FinalStatus.PASS_WITH_NOTES if (notes or repair_attempts) else FinalStatus.PASS
    elif val_result == ValidationResult.VALIDATION_WARN:
        final = FinalStatus.PASS_WITH_NOTES
    elif val_result == ValidationResult.VALIDATION_BLOCKED:
        final = FinalStatus.BLOCKED
    else:
        final = FinalStatus.FAIL

    artifacts = execution_result.get("artifacts_created", [])
    diffs = [execution_result.get("diff_summary", "")] + [r.get("diff", "") for r in repair_log if r.get("diff")]
    diffs = [d for d in diffs if d]
    test_results = {"mock": mock_detail, "validation": val_detail, "repairs": repair_log}

    lessons = list(val_detail.get("lessons_candidate", [])) + (task.lessons(packet, val_detail, repair_log)
                                                               if hasattr(task, "lessons") else [])
    promo = evaluate_lessons(lessons)

    limitations = list(val_detail.get("limitations", []))
    if final != FinalStatus.PASS:
        limitations.append(f"final status {final.value}; see validation detail")

    entry = ProofEntry(
        run_id=run_id, task_id=packet.task_id, timestamp=_now_iso(),
        input_hash=input_hash, plan_hash=plan_hash,
        mock_trial_result=mock_result.value, execution_result=execution_result,
        validation_result=val_result.value, repair_attempts=repair_attempts,
        artifacts=artifacts, diffs=diffs, test_results=test_results,
        final_status=final.value,
        lessons_candidate=[l for l in lessons],
        promotion_candidate=promo["promoted"],
        limitations=limitations,
    )
    ledger.append(entry)
    return {
        "status": final.value, "entry": entry.to_dict(), "plan": plan,
        "mock": mock_detail, "validation": val_detail, "repairs": repair_log,
        "promotion": promo, "notes": notes,
    }
