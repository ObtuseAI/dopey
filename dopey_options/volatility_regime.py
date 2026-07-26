"""Deterministic volatility-regime transition fixtures for DOPEY."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .iv_surface_expansion import IVSurfaceScenario, clamp


VOLATILITY_REGIME_VERSION = "dopey-volatility-regime-transition-v1"


@dataclass(frozen=True)
class VolatilityRegimeTransition:
    scenario_id: str
    from_regime: str
    to_regime: str
    transition_pressure: float
    expansion_pressure: float
    compression_pressure: float
    transition_risk_score: float
    notes: str
    version: str = VOLATILITY_REGIME_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def build_volatility_regime_transition(scenario: IVSurfaceScenario) -> VolatilityRegimeTransition:
    expansion = clamp(scenario.iv_expansion_potential + scenario.front_event_bump * 0.30 + max(0.0, -scenario.term_slope) * 1.50, 0.0, 1.0)
    compression = clamp(scenario.iv_crush_risk + max(0.0, scenario.term_slope) * 1.50 - scenario.surface_instability * 0.20, 0.0, 1.0)
    pressure = clamp(abs(expansion - compression) * 0.45 + scenario.surface_instability * 0.35 + scenario.wing_elevation * 0.20, 0.0, 1.0)
    if expansion > compression + 0.18:
        to_regime = "iv_expansion"
    elif compression > expansion + 0.18:
        to_regime = "iv_compression"
    else:
        to_regime = "mixed_transition"
    if scenario.iv_rank >= 0.70:
        from_regime = "high_iv"
    elif scenario.iv_rank <= 0.30:
        from_regime = "low_iv"
    else:
        from_regime = "normal_iv"
    return VolatilityRegimeTransition(
        scenario_id=scenario.scenario_id,
        from_regime=from_regime,
        to_regime=to_regime,
        transition_pressure=round(pressure, 6),
        expansion_pressure=round(expansion, 6),
        compression_pressure=round(compression, 6),
        transition_risk_score=round(clamp(pressure * 0.60 + scenario.surface_instability * 0.40, 0.0, 1.0), 6),
        notes="deterministic fixture transition, not live volatility forecasting",
    )
