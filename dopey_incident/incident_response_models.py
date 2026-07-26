"""Deterministic incident response decision models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash


ALLOWED_RESPONSE_DECISIONS = {
    "continue_monitoring",
    "throttle_paper_allocation",
    "block_new_entries",
    "block_zero_dte",
    "paper_lockdown",
    "audit_only_mode",
    "manual_review_required",
    "terminal_block",
    "reject_incident_fixture",
}


@dataclass(frozen=True)
class IncidentResponseDecision:
    response_id: str
    incident_id: str
    kill_switch_state: str
    decision: str
    blocked_actions: list[str]
    allowed_actions: list[str]
    audit_actions: list[str]
    remediation_actions: list[str]
    recovery_plan_id: str
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def __post_init__(self) -> None:
        if self.decision not in ALLOWED_RESPONSE_DECISIONS:
            raise ValueError(f"unsupported incident response decision: {self.decision}")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("incident response decision must be paper_only and live_blocked")
        if any("live_order" in action or "broker_execute" in action for action in self.allowed_actions):
            raise ValueError("incident response decision cannot allow live path")
        if self.decision_hash and self.decision_hash != incident_response_decision_hash(self):
            raise ValueError("incident response decision hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "IncidentResponseDecision":
        return cls(
            response_id=str(record["response_id"]),
            incident_id=str(record["incident_id"]),
            kill_switch_state=str(record["kill_switch_state"]),
            decision=str(record["decision"]),
            blocked_actions=[str(value) for value in record["blocked_actions"]],
            allowed_actions=[str(value) for value in record["allowed_actions"]],
            audit_actions=[str(value) for value in record["audit_actions"]],
            remediation_actions=[str(value) for value in record["remediation_actions"]],
            recovery_plan_id=str(record["recovery_plan_id"]),
            reason_codes=[str(value) for value in record["reason_codes"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            decision_hash=str(record.get("decision_hash", "")),
        )


def incident_response_decision_hash(record: IncidentResponseDecision) -> str:
    return reproducibility_hash({key: value for key, value in record.to_dict().items() if key != "decision_hash"})

