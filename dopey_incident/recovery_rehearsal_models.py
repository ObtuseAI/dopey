"""Deterministic incident recovery rehearsal models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash


@dataclass(frozen=True)
class IncidentRecoveryPlan:
    recovery_plan_id: str
    source_incident_id: str
    current_kill_switch_state: str
    target_state: str
    required_checks: list[str]
    required_artifacts: list[str]
    cooldown_steps: int
    recovery_allowed: bool
    recovery_blockers: list[str]
    paper_only: bool
    live_blocked: bool
    plan_hash: str

    def __post_init__(self) -> None:
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("incident recovery plan must be paper_only and live_blocked")
        if self.current_kill_switch_state == "terminal_block" and self.recovery_allowed is True:
            raise ValueError("terminal block cannot auto-recover")
        if self.current_kill_switch_state == "terminal_block" and self.target_state == "inactive":
            raise ValueError("terminal block cannot jump to inactive")
        if self.plan_hash and self.plan_hash != incident_recovery_plan_hash(self):
            raise ValueError("incident recovery plan hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "IncidentRecoveryPlan":
        return cls(
            recovery_plan_id=str(record["recovery_plan_id"]),
            source_incident_id=str(record["source_incident_id"]),
            current_kill_switch_state=str(record["current_kill_switch_state"]),
            target_state=str(record["target_state"]),
            required_checks=[str(value) for value in record["required_checks"]],
            required_artifacts=[str(value) for value in record["required_artifacts"]],
            cooldown_steps=int(record["cooldown_steps"]),
            recovery_allowed=bool(record["recovery_allowed"]),
            recovery_blockers=[str(value) for value in record["recovery_blockers"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            plan_hash=str(record.get("plan_hash", "")),
        )


def incident_recovery_plan_hash(record: IncidentRecoveryPlan) -> str:
    return reproducibility_hash({key: value for key, value in record.to_dict().items() if key != "plan_hash"})
