"""Dopey core kernel: work packet, statuses, hashing, and the safety / human-gate model.

Forked from Blunder Recursive Work Engine V1 (Z:\\Obtuse\\engine\\blunder\\core.py) and renamed
to the Dopey namespace. Logic preserved verbatim; only the module name and version constant
changed. DOPEY keeps Blunder's fail-closed safety model intact.

DOPEY lineage: Blunder engine core -> dopey_core._kernel
DOPEY_VERSION supersedes BLUNDER_VERSION for Dopey-native code; the original Blunder copy on Z:
is never modified.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

DOPEY_VERSION = "0.1.0"
BLUNDER_LINEAGE_VERSION = "1.0.0"  # the Blunder version this kernel was forked from


# ----------------------------------------------------------------------------- statuses (explicit, no vague PASS)
class MockResult(str, Enum):
    MOCK_PASS = "MOCK_PASS"
    MOCK_WARN = "MOCK_WARN"
    MOCK_FAIL = "MOCK_FAIL"
    MOCK_BLOCKED = "MOCK_BLOCKED"


class ValidationResult(str, Enum):
    VALIDATION_PASS = "VALIDATION_PASS"
    VALIDATION_WARN = "VALIDATION_WARN"
    VALIDATION_FAIL = "VALIDATION_FAIL"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"


class FinalStatus(str, Enum):
    PASS = "PASS"
    PASS_WITH_NOTES = "PASS_WITH_NOTES"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


class TaskType(str, Enum):
    PLANNING_ONLY = "planning_only"
    CODE_FILE = "code_file"
    BENCHMARK = "benchmark"
    VALIDATION = "validation"
    SELF_IMPROVEMENT = "self_improvement"
    RISKY_IRREVERSIBLE = "risky_irreversible"


# ----------------------------------------------------------------------------- hashing
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False))


# ----------------------------------------------------------------------------- safety / human-gate model
# Allowed WITHOUT a human gate (the Blunder Fusion Doctrine "bounded, proof-gated lanes").
GATE_FREE_ACTIONS = {
    "local_inspection", "read_file", "safe_fixture", "dry_run", "mock_trial",
    "run_tests", "schema_validation", "local_proof_generation", "non_destructive_repo_edit",
    "write_workdir", "compute", "parse_artifact",
}
# REQUIRE a single human gate (risky / irreversible / external / credential / system).
GATE_REQUIRED_ACTIONS = {
    "production_deploy", "external_service", "network_submission", "destructive_file_op",
    "credential_use", "system_change", "validator_weakening", "security_sensitive",
    "delete_outside_workdir", "remote_command", "push",
}


def classify_action(action: str) -> dict:
    """Classify an action as gate-free or gate-required (used by intake + execution)."""
    a = (action or "").strip().lower()
    if a in GATE_REQUIRED_ACTIONS:
        return {"action": a, "gate_required": True, "reason": "risky/irreversible/external/credential/system"}
    if a in GATE_FREE_ACTIONS:
        return {"action": a, "gate_required": False, "reason": "bounded safe lane"}
    # Unknown action -> conservative: require a gate (fail-closed).
    return {"action": a, "gate_required": True, "reason": "unknown action -> fail-closed (gate required)"}


# ----------------------------------------------------------------------------- work packet
@dataclass
class WorkPacket:
    task_id: str
    title: str
    objective: str
    task_type: str = TaskType.CODE_FILE.value
    risk_level: str = RiskLevel.LOW.value
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    expected_outputs: list[str] = field(default_factory=list)
    validation_targets: list[str] = field(default_factory=list)
    rollback_plan: str = ""
    human_gate_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def packet_hash(self) -> str:
        return sha256_obj(self.to_dict())


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")[:48] or "task"


def intake(raw: dict) -> WorkPacket:
    """Convert a raw task dict into a structured, safety-classified WorkPacket.

    Distinguishes task types and FORCES human_gate_required for risky/irreversible work or for any
    requested action that classifies as gate-required (fail-closed)."""
    title = raw.get("title", "Untitled task")
    task_type = raw.get("task_type", TaskType.CODE_FILE.value)
    risk = raw.get("risk_level", RiskLevel.LOW.value)
    allowed = list(raw.get("allowed_actions", []))
    forbidden = list(raw.get("forbidden_actions", []))

    # Fail-closed gate: irreversible/high risk, the risky task type, or any gate-required allowed action.
    gate = bool(raw.get("human_gate_required", False))
    if task_type == TaskType.RISKY_IRREVERSIBLE.value:
        gate = True
    if risk in (RiskLevel.HIGH.value, RiskLevel.IRREVERSIBLE.value):
        gate = True
    for a in allowed:
        if classify_action(a)["gate_required"]:
            gate = True
            break

    task_id = raw.get("task_id") or f"dopey-{_slug(title)}"
    return WorkPacket(
        task_id=task_id,
        title=title,
        objective=raw.get("objective", ""),
        task_type=task_type,
        risk_level=risk,
        allowed_actions=allowed,
        forbidden_actions=forbidden,
        inputs=dict(raw.get("inputs", {})),
        expected_outputs=list(raw.get("expected_outputs", [])),
        validation_targets=list(raw.get("validation_targets", [])),
        rollback_plan=raw.get("rollback_plan", ""),
        human_gate_required=gate,
    )
