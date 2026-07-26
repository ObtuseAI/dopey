"""Dopey strategy genome: stdlib dataclass describing a strategy family + parameters.

DOPEY-native. No pydantic. The genome is the unit the mutation engine perturbs and the
aggression gate scores. live_allowed is always false in the first pass; promotion to any live
tier requires an explicit future enablement + proof bundle.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class StrategyGenome:
    genome_id: str
    family: str
    preferred_regime: str = "neutral"
    entry_threshold: float = 0.0
    max_position_fraction: float = 0.0
    min_open_interest: int = 0
    defined_risk_only: bool = True
    live_allowed: bool = False
    version: int = 1
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyGenome":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
