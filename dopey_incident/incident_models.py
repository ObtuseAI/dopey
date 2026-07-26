"""Deterministic incident response models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash


ALLOWED_INCIDENT_FAMILIES = {
    "policy_violation",
    "no_day_trade_violation",
    "zero_dte_lifecycle_violation",
    "portfolio_exposure_violation",
    "crisis_mode_violation",
    "paperbroker_override_attempt",
    "live_path_injection",
    "broker_path_injection",
    "credential_exposure",
    "scheduler_emergence",
    "real_market_data_reference",
    "real_sizing_reference",
    "artifact_integrity_drift",
    "audit_staleness",
    "proof_contradiction",
    "export_safety_violation",
    "validation_failure",
    "unknown_state",
}
ALLOWED_SEVERITIES = {"info", "warning", "elevated", "severe", "critical", "lockdown"}


@dataclass(frozen=True)
class IncidentSignal:
    signal_id: str
    incident_family: str
    incident_type: str
    source_component: str
    detected_at_stage: str
    severity: str
    trigger_conditions: list[str]
    evidence_paths: list[str]
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    signal_hash: str

    def __post_init__(self) -> None:
        if self.incident_family not in ALLOWED_INCIDENT_FAMILIES:
            raise ValueError(f"unsupported incident family: {self.incident_family}")
        if self.severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"unsupported incident severity: {self.severity}")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("incident signal must be paper_only and live_blocked")
        if self.signal_hash and self.signal_hash != incident_signal_hash(self):
            raise ValueError("incident signal hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "IncidentSignal":
        return cls(
            signal_id=str(record["signal_id"]),
            incident_family=str(record["incident_family"]),
            incident_type=str(record["incident_type"]),
            source_component=str(record["source_component"]),
            detected_at_stage=str(record["detected_at_stage"]),
            severity=str(record["severity"]),
            trigger_conditions=[str(value) for value in record["trigger_conditions"]],
            evidence_paths=[str(value) for value in record["evidence_paths"]],
            reason_codes=[str(value) for value in record["reason_codes"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            signal_hash=str(record.get("signal_hash", "")),
        )


def incident_signal_hash(record: IncidentSignal) -> str:
    return _hash_without(record.to_dict(), "signal_hash")


def _hash_without(record: dict[str, Any], field_name: str) -> str:
    return reproducibility_hash({key: value for key, value in record.items() if key != field_name})

