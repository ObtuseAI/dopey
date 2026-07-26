"""Deterministic macro-event fixture models for DOPEY paper replay.

All values are deterministic 0..1 fixture scores. They do not represent real macro data,
calendars, FRED/VIX feeds, futures prices, or live broker market data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


MACRO_EVENT_FIXTURE_VERSION = "dopey-macro-event-fixture-v1"


@dataclass(frozen=True)
class MacroEventFixture:
    event_id: str
    event_type: str
    event_window: str
    event_intensity: float
    surprise_direction: str  # hawkish | dovish | upside | downside | neutral
    risk_on_off_bias: str    # risk_on | risk_off | neutral
    volatility_impulse: float
    rates_pressure: float
    dollar_pressure: float
    sector_rotation_pressure: float
    breadth_pressure: float
    liquidity_pressure: float
    overnight_futures_pressure: float
    notes: str = ""
    version: str = MACRO_EVENT_FIXTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MacroRegimeContext:
    regime_id: str
    risk_on_score: float = 0.5
    risk_off_score: float = 0.5
    rate_shock_score: float = 0.5
    inflation_pressure_score: float = 0.5
    dollar_strength_score: float = 0.5
    vix_stress_score: float = 0.5
    vvix_stress_score: float = 0.5
    breadth_score: float = 0.5
    sector_rotation_score: float = 0.5
    liquidity_regime_score: float = 0.5
    overnight_pressure_score: float = 0.5
    macro_trend_score: float = 0.5
    macro_fakeout_risk_score: float = 0.5
    notes: str = ""
    version: str = MACRO_EVENT_FIXTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MacroEventRiskSummary:
    macro_shock_score: float
    vol_expansion_support_score: float
    compression_danger_score: float
    directional_confirmation_score: float
    directional_fakeout_score: float
    short_duration_liquidity_risk_score: float
    macro_contradiction_score: float
    event_gap_risk_score: float
    risk_flags: list[str]
    verdict: str
    version: str = MACRO_EVENT_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk_flags"] = sorted(self.risk_flags)
        return data


@dataclass(frozen=True)
class MacroShockProfile:
    profile_id: str
    macro_shock_score: float
    rate_shock_pressure: float
    inflation_surprise_pressure: float
    dollar_pressure: float
    vix_vvix_pressure: float
    breadth_pressure: float
    liquidity_pressure: float
    overnight_pressure: float
    notes: str = ""
    version: str = MACRO_EVENT_FIXTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MacroOpportunityVerdict:
    scenario_id: str
    strategy_family: str
    verdict: str
    opportunity_score: float
    risk_score: float
    reasons: list[str]
    version: str = MACRO_EVENT_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reasons"] = sorted(self.reasons)
        return data


@dataclass(frozen=True)
class MacroEventScenario:
    scenario_id: str
    regime_tag: str
    macro_event: MacroEventFixture
    regime_context: MacroRegimeContext
    risk_summary: MacroEventRiskSummary
    preferred_strategy_families: list[str]
    penalized_strategy_families: list[str]
    expected_iv_effect: str
    expected_slippage_effect: str
    expected_pattern_effect: str
    expected_failure_modes: list[str]
    notes: str = ""
    version: str = MACRO_EVENT_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["macro_event"] = self.macro_event.to_dict()
        data["regime_context"] = self.regime_context.to_dict()
        data["risk_summary"] = self.risk_summary.to_dict()
        data["preferred_strategy_families"] = sorted(self.preferred_strategy_families)
        data["penalized_strategy_families"] = sorted(self.penalized_strategy_families)
        data["expected_failure_modes"] = sorted(self.expected_failure_modes)
        return data


@dataclass(frozen=True)
class FamilyMacroEventScore:
    strategy_family: str
    scenario_id: str
    regime_tag: str
    macro_fit_score: float
    macro_opportunity_score: float
    macro_risk_score: float
    event_risk_score: float
    rate_shock_score: float
    vix_vvix_stress_score: float
    breadth_sector_confirmation_score: float
    liquidity_regime_macro_score: float
    macro_contradiction_penalty: float
    event_gap_risk_penalty: float
    risk_flags: list[str]
    verdict: str
    version: str = MACRO_EVENT_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk_flags"] = sorted(self.risk_flags)
        return data


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _event_gap_risk(event: MacroEventFixture, regime: MacroRegimeContext) -> float:
    return clamp(
        0.40 * event.event_intensity
        + 0.30 * event.overnight_futures_pressure
        + 0.20 * (1.0 - regime.liquidity_regime_score)
        + 0.10 * regime.vix_stress_score,
    )


def _regime_event_gap_risk(regime: MacroRegimeContext) -> float:
    return clamp(
        0.35 * (1.0 - regime.liquidity_regime_score)
        + 0.30 * regime.overnight_pressure_score
        + 0.20 * regime.vix_stress_score
        + 0.15 * regime.rate_shock_score,
    )


def summarize_macro_risk(
    event: MacroEventFixture,
    regime: MacroRegimeContext,
) -> MacroEventRiskSummary:
    """Convert event + regime into family-agnostic macro risk summary."""
    event_gap = _event_gap_risk(event, regime)
    macro_shock = clamp(
        0.22 * event.event_intensity
        + 0.18 * regime.rate_shock_score
        + 0.16 * regime.inflation_pressure_score
        + 0.16 * regime.vix_stress_score
        + 0.14 * event.overnight_futures_pressure
        + 0.14 * (1.0 - regime.breadth_score),
    )
    vol_expansion_support = clamp(
        0.30 * event.volatility_impulse
        + 0.24 * regime.vix_stress_score
        + 0.18 * event.event_intensity
        + 0.16 * event.overnight_futures_pressure
        + 0.12 * regime.rate_shock_score,
    )
    compression_danger = clamp(
        0.28 * macro_shock
        + 0.22 * _regime_event_gap_risk(regime)
        + 0.18 * regime.vix_stress_score
        + 0.16 * event.overnight_futures_pressure
        + 0.16 * (1.0 - regime.liquidity_regime_score),
    )
    directional_confirmation = clamp(
        0.30 * regime.macro_trend_score
        + 0.22 * regime.breadth_score
        + 0.18 * (1.0 - regime.macro_fakeout_risk_score)
        + 0.16 * abs(regime.risk_on_score - regime.risk_off_score)
        + 0.14 * (1.0 - event_gap),
    )
    directional_fakeout = clamp(
        0.32 * regime.macro_fakeout_risk_score
        + 0.24 * event.overnight_futures_pressure
        + 0.20 * (1.0 - regime.breadth_score)
        + 0.14 * event.volatility_impulse
        + 0.10 * event.event_intensity,
    )
    short_duration_liquidity_risk = clamp(
        0.28 * (1.0 - regime.liquidity_regime_score)
        + 0.24 * event.overnight_futures_pressure
        + 0.20 * event_gap
        + 0.16 * event.volatility_impulse
        + 0.12 * regime.vix_stress_score,
    )
    macro_contradiction = clamp(
        0.35 * abs(regime.risk_on_score - regime.risk_off_score)
        * regime.macro_fakeout_risk_score
        + 0.25 * event.volatility_impulse * (1.0 - regime.macro_trend_score)
        + 0.20 * regime.sector_rotation_score * (1.0 - regime.breadth_score)
        + 0.20 * event.overnight_futures_pressure * regime.macro_fakeout_risk_score,
    )

    flags: list[str] = []
    if macro_shock >= 0.70:
        flags.append("macro_shock_danger")
    if compression_danger >= 0.70:
        flags.append("compression_macro_danger")
    if directional_fakeout >= 0.70:
        flags.append("directional_fakeout_risk")
    if short_duration_liquidity_risk >= 0.70:
        flags.append("short_duration_bad_fill_risk")
    if macro_contradiction >= 0.65:
        flags.append("macro_contradiction")
    if event_gap >= 0.65:
        flags.append("event_gap_risk")
    if vol_expansion_support >= 0.70:
        flags.append("vol_expansion_supported")
    if directional_confirmation >= 0.70:
        flags.append("directional_confirmed")

    if macro_shock >= 0.78 and compression_danger >= 0.70:
        verdict = "macro_shock_danger"
    elif directional_fakeout >= 0.78:
        verdict = "macro_fakeout_risk"
    elif short_duration_liquidity_risk >= 0.78:
        verdict = "short_duration_bad_fill_risk"
    elif compression_danger >= 0.78:
        verdict = "compression_danger"
    elif macro_contradiction >= 0.75 and vol_expansion_support < 0.55:
        verdict = "macro_contradiction"
    elif directional_confirmation >= 0.75:
        verdict = "directional_confirmed"
    elif vol_expansion_support >= 0.75:
        verdict = "vol_expansion_supported"
    elif event_gap >= 0.75:
        verdict = "event_gap_risk"
    else:
        verdict = "macro_neutral"

    return MacroEventRiskSummary(
        macro_shock_score=round(macro_shock, 6),
        vol_expansion_support_score=round(vol_expansion_support, 6),
        compression_danger_score=round(compression_danger, 6),
        directional_confirmation_score=round(directional_confirmation, 6),
        directional_fakeout_score=round(directional_fakeout, 6),
        short_duration_liquidity_risk_score=round(short_duration_liquidity_risk, 6),
        macro_contradiction_score=round(macro_contradiction, 6),
        event_gap_risk_score=round(event_gap, 6),
        risk_flags=sorted(flags),
        verdict=verdict,
    )
