"""Offline data-source candidate models for DOPEY.

These dataclasses describe possible future data inflow sources without fetching from them.
They are deterministic planning artifacts only: no network, no credentials, no broker access.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SourceCandidate:
    source_id: str
    source_name: str
    source_type: str
    intended_use: str
    asset_scope: str
    latency_class: str
    freshness_class: str
    license_status: str
    credential_required: bool
    network_required: bool
    allowed_in_current_pass: bool
    risk_notes: str
    expected_edge_contribution: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SourceCandidate":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class SourceContributionHypothesis:
    source_id: str
    contribution_type: str
    target_layers: list[str] = field(default_factory=list)
    expected_lift_score: float = 0.0
    confidence: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SourceContributionHypothesis":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class SourcePromotionDecision:
    source_id: str
    decision: str
    reasons: list[str] = field(default_factory=list)
    allowed_in_current_pass: bool = False
    network_required: bool = False
    credential_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SourcePromotionDecision":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
