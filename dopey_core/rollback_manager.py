"""Dopey rollback manager: bounded repair / rollback containment for the autonomy loop.

Forked from Blunder engine (Z:\\Obtuse\\engine\\blunder\\engine.py); the bounded repair loop
inside Blunder's `run()` was extracted here as a recommend-only rollback/repair policy. DOPEY
keeps the bounded repair attempt cap and the workdir-confined containment doctrine. No live
trading or funded-broker effects are possible here.

DOPEY lineage: Blunder engine.py (repair loop + containment) -> dopey_core.rollback_manager
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_REPAIR_ATTEMPTS = 3


def should_repair(validation_result: str, repair_attempts: int) -> bool:
    """Return True only while validation is failing AND the bounded repair budget is not exhausted."""
    return validation_result == "VALIDATION_FAIL" and repair_attempts < MAX_REPAIR_ATTEMPTS


def run_bounded_repair(task: Any, packet: Any, workdir: Path, failures: list, attempt: int) -> dict:
    """Invoke a task's repair step once; return its repair record. The task's repair() returns a
    dict with at least 'patched' (bool). If the task does not patch, the loop stops (fail-closed)."""
    rec = task.repair(packet, workdir, failures, attempt)
    if not isinstance(rec, dict):
        return {"attempt": attempt, "action": "no_repair_available", "patched": False}
    rec.setdefault("patched", False)
    rec.setdefault("attempt", attempt)
    return rec


def containment_note(rollback_plan: str = "") -> str:
    """Default containment doctrine when no explicit rollback plan is supplied."""
    return rollback_plan or "all writes confined to the run workdir; discard workdir to roll back"
