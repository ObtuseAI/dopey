"""Deterministic kill-switch state models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash


ALLOWED_KILL_SWITCH_STATES = {
    "inactive",
    "monitor",
    "paper_throttle",
    "paper_lockdown",
    "audit_only",
    "manual_review_required",
    "terminal_block",
}


@dataclass(frozen=True)
class KillSwitchState:
    kill_switch_id: str
    state_name: str
    state_rank: int
    triggering_incident_ids: list[str]
    blocked_actions: list[str]
    allowed_actions: list[str]
    audit_only_actions: list[str]
    paper_only_actions: list[str]
    recovery_requirements: list[str]
    manual_review_required: bool
    paper_only: bool
    live_blocked: bool
    state_hash: str

    def __post_init__(self) -> None:
        if self.state_name not in ALLOWED_KILL_SWITCH_STATES:
            raise ValueError(f"unsupported kill-switch state: {self.state_name}")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("kill-switch state must be paper_only and live_blocked")
        if self.state_hash and self.state_hash != kill_switch_state_hash(self):
            raise ValueError("kill-switch state hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "KillSwitchState":
        return cls(
            kill_switch_id=str(record["kill_switch_id"]),
            state_name=str(record["state_name"]),
            state_rank=int(record["state_rank"]),
            triggering_incident_ids=[str(value) for value in record["triggering_incident_ids"]],
            blocked_actions=[str(value) for value in record["blocked_actions"]],
            allowed_actions=[str(value) for value in record["allowed_actions"]],
            audit_only_actions=[str(value) for value in record["audit_only_actions"]],
            paper_only_actions=[str(value) for value in record["paper_only_actions"]],
            recovery_requirements=[str(value) for value in record["recovery_requirements"]],
            manual_review_required=bool(record["manual_review_required"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            state_hash=str(record.get("state_hash", "")),
        )


def kill_switch_state_hash(record: KillSwitchState) -> str:
    return reproducibility_hash({key: value for key, value in record.to_dict().items() if key != "state_hash"})

