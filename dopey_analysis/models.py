"""Dopey analysis context models (stdlib dataclasses, deterministic, offline).

Each context is a serializable snapshot of one analysis layer for a fixture window. All scores
are 0..1 floats. These are deterministic fixture values in this pass; real-data feeds are
deferred (no network, no credentials).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class MacroContext:
    regime_tag: str = ""
    risk_on_score: float = 0.5
    volatility_regime_score: float = 0.5
    event_risk_score: float = 0.2
    sector_rotation_score: float = 0.5
    breadth_score: float = 0.5
    liquidity_regime_score: float = 0.5
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MacroContext":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class MicrostructureContext:
    spread_quality_score: float = 0.5
    liquidity_score: float = 0.5
    slippage_sensitivity_score: float = 0.5
    volume_oi_anomaly_score: float = 0.2
    quote_stability_score: float = 0.5
    contract_fillability_score: float = 0.5
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MicrostructureContext":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TechnicalContext:
    trend_score: float = 0.5
    momentum_score: float = 0.5
    realized_volatility_score: float = 0.5
    breakout_score: float = 0.3
    fakeout_risk_score: float = 0.2
    support_resistance_score: float = 0.5
    volume_confirmation_score: float = 0.5
    gap_behavior_score: float = 0.5
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TechnicalContext":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class FundamentalContext:
    earnings_risk_score: float = 0.2
    filing_event_score: float = 0.1
    valuation_context_score: float = 0.5
    growth_quality_score: float = 0.5
    analyst_revision_score: float = 0.5
    sector_peer_score: float = 0.5
    fundamental_support_score: float = 0.5
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FundamentalContext":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PatternSignal:
    pattern_id: str = ""
    pattern_type: str = ""
    confidence: float = 0.0
    directional_bias: str = "neutral"   # long | short | neutral
    volatility_bias: str = "neutral"    # expansion | compression | neutral
    regime_dependency: str = "neutral"
    failure_mode: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PatternSignal":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AnalysisFusionScore:
    macro_score: float = 0.0
    microstructure_score: float = 0.0
    technical_score: float = 0.0
    fundamental_score: float = 0.0
    pattern_score: float = 0.0
    contradiction_penalty: float = 0.0
    freshness_reliability_score: float = 1.0
    replay_confirmation_score: float = 0.0
    overall_score: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisFusionScore":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
