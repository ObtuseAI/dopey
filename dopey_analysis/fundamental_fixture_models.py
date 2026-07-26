"""Deterministic sector / peer / fundamental fixture models for DOPEY paper replay.

All values are deterministic 0..1 fixture scores plus deterministic categorical labels.
They do not represent real sector data, peer compositions, fundamentals, SEC filings,
analyst estimates, or institutional flow data. No real data is fetched.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


FUNDAMENTAL_FIXTURE_VERSION = "dopey-fundamental-fixture-v1"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class SectorContext:
    sector_id: str
    sector_name: str
    sector_regime: str
    sector_momentum_score: float
    sector_relative_strength_score: float
    sector_dispersion_score: float
    sector_volatility_score: float
    sector_rotation_score: float
    defensive_cyclical_bias: str
    growth_value_bias: str
    liquidity_context: str
    notes: str = ""
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PeerRelativeContext:
    peer_group_id: str
    peer_count: int
    peer_relative_strength_score: float
    peer_dispersion_score: float
    peer_leadership_score: float
    peer_breakdown_pressure: float
    peer_confirmation_score: float
    peer_contradiction_score: float
    crowding_proxy_score: float
    notes: str = ""
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FundamentalFixture:
    fundamental_id: str
    symbol: str
    sector_id: str
    revenue_growth_proxy: float
    margin_quality_proxy: float
    earnings_quality_proxy: float
    balance_sheet_risk_proxy: float
    cash_flow_quality_proxy: float
    valuation_stretch_proxy: float
    revision_momentum_proxy: float
    event_catalyst_quality_proxy: float
    short_interest_pressure_proxy: float
    fundamental_trend_score: float
    fundamental_fragility_score: float
    notes: str = ""
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValuationContext:
    valuation_regime: str
    relative_valuation_score: float
    valuation_stretch_score: float
    multiple_compression_risk: float
    multiple_expansion_support: float
    growth_adjusted_value_score: float
    valuation_trap_score: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EarningsQualityContext:
    earnings_quality_score: float
    earnings_consistency_score: float
    margin_quality_score: float
    cash_flow_quality_score: float
    revenue_growth_score: float
    revision_momentum_score: float
    event_catalyst_quality_score: float
    balance_sheet_risk_score: float
    short_interest_pressure_score: float
    fragility_score: float
    notes: str = ""
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FundamentalRiskSummary:
    fundamental_confirmation_score: float
    fundamental_contradiction_score: float
    quality_score: float
    fragility_score: float
    valuation_risk_score: float
    peer_confirmation_score: float
    sector_confirmation_score: float
    event_quality_score: float
    crowding_risk_score: float
    risk_flags: list[str]
    verdict: str
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk_flags"] = sorted(self.risk_flags)
        return data


@dataclass(frozen=True)
class FundamentalOpportunityVerdict:
    scenario_id: str
    strategy_family: str
    verdict: str
    opportunity_score: float
    risk_score: float
    reasons: list[str]
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reasons"] = sorted(self.reasons)
        return data


@dataclass(frozen=True)
class SectorPeerFundamentalScenario:
    scenario_id: str
    regime_tag: str
    sector_context: SectorContext
    peer_context: PeerRelativeContext
    fundamental_fixture: FundamentalFixture
    valuation_context: ValuationContext
    earnings_quality_context: EarningsQualityContext
    risk_summary: FundamentalRiskSummary
    preferred_strategy_families: list[str]
    penalized_strategy_families: list[str]
    expected_macro_effect: str
    expected_iv_effect: str
    expected_liquidity_slippage_effect: str
    expected_pattern_effect: str
    expected_failure_modes: list[str]
    notes: str = ""
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["sector_context"] = self.sector_context.to_dict()
        data["peer_context"] = self.peer_context.to_dict()
        data["fundamental_fixture"] = self.fundamental_fixture.to_dict()
        data["valuation_context"] = self.valuation_context.to_dict()
        data["earnings_quality_context"] = self.earnings_quality_context.to_dict()
        data["risk_summary"] = self.risk_summary.to_dict()
        data["preferred_strategy_families"] = sorted(self.preferred_strategy_families)
        data["penalized_strategy_families"] = sorted(self.penalized_strategy_families)
        data["expected_failure_modes"] = sorted(self.expected_failure_modes)
        return data


@dataclass(frozen=True)
class FamilyFundamentalScore:
    strategy_family: str
    scenario_id: str
    regime_tag: str
    fundamental_fit_score: float
    sector_fit_score: float
    peer_confirmation_score: float
    fundamental_confirmation_score: float
    valuation_risk_score: float
    earnings_quality_score: float
    crowding_risk_score: float
    fundamental_contradiction_penalty: float
    fragility_penalty: float
    family_fundamental_fit_score: float
    risk_flags: list[str]
    verdict: str
    version: str = FUNDAMENTAL_FIXTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk_flags"] = sorted(self.risk_flags)
        return data


def scenario_hash(scenario: SectorPeerFundamentalScenario) -> str:
    """Deterministic hash of the scenario's fixture content (sorted keys, SHA256)."""
    import hashlib
    import json

    payload = {
        "scenario_id": scenario.scenario_id,
        "regime_tag": scenario.regime_tag,
        "sector_context": scenario.sector_context.to_dict(),
        "peer_context": scenario.peer_context.to_dict(),
        "fundamental_fixture": scenario.fundamental_fixture.to_dict(),
        "valuation_context": scenario.valuation_context.to_dict(),
        "earnings_quality_context": scenario.earnings_quality_context.to_dict(),
        "preferred_strategy_families": sorted(scenario.preferred_strategy_families),
        "penalized_strategy_families": sorted(scenario.penalized_strategy_families),
        "expected_failure_modes": sorted(scenario.expected_failure_modes),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
