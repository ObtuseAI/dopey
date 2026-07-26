"""Expanded deterministic IV surface fixture models for DOPEY."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


IV_SURFACE_EXPANSION_VERSION = "dopey-iv-surface-expansion-v1"


@dataclass(frozen=True)
class IVSurfacePoint:
    expiration_bucket: str
    moneyness_bucket: str
    option_type: str
    iv: float
    relative_iv: float
    surface_weight: float
    notes: str
    version: str = IV_SURFACE_EXPANSION_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IVSurfaceGrid:
    surface_id: str
    underlying: str
    regime_tag: str
    points: list[IVSurfacePoint]
    atm_iv: float
    front_iv: float
    back_iv: float
    wings_elevated: bool
    surface_stability_score: float
    surface_convexity_score: float
    surface_opportunity_score: float
    version: str = IV_SURFACE_EXPANSION_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["points"] = [point.to_dict() for point in sorted(
            self.points,
            key=lambda item: (item.expiration_bucket, item.moneyness_bucket, item.option_type),
        )]
        return data


@dataclass(frozen=True)
class IVSurfaceScenario:
    scenario_id: str
    regime_tag: str
    iv_rank: float
    iv_percentile: float
    realized_volatility: float
    implied_vs_realized_gap: float
    front_event_bump: float
    term_slope: float
    put_skew: float
    call_skew: float
    wing_elevation: float
    iv_crush_risk: float
    iv_expansion_potential: float
    surface_instability: float
    preferred_strategy_families: list[str]
    penalized_strategy_families: list[str]
    strategy_outcome_hints: dict[str, str] = field(default_factory=dict)
    version: str = IV_SURFACE_EXPANSION_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["preferred_strategy_families"] = sorted(self.preferred_strategy_families)
        data["penalized_strategy_families"] = sorted(self.penalized_strategy_families)
        data["strategy_outcome_hints"] = {
            key: self.strategy_outcome_hints[key]
            for key in sorted(self.strategy_outcome_hints)
        }
        return data


@dataclass(frozen=True)
class IVSurfaceRiskSummary:
    iv_crush_score: float
    iv_expansion_score: float
    term_structure_risk_score: float
    skew_risk_score: float
    surface_instability_score: float
    premium_overpayment_score: float
    compression_opportunity_score: float
    expansion_opportunity_score: float
    risk_flags: list[str]
    verdict: str
    version: str = IV_SURFACE_EXPANSION_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk_flags"] = sorted(self.risk_flags)
        return data


@dataclass(frozen=True)
class IVOpportunityVerdict:
    scenario_id: str
    strategy_family: str
    verdict: str
    opportunity_score: float
    risk_score: float
    reasons: list[str]
    version: str = IV_SURFACE_EXPANSION_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reasons"] = sorted(self.reasons)
        return data


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_surface_grid(scenario: IVSurfaceScenario, underlying: str) -> IVSurfaceGrid:
    front_iv = clamp(0.16 + scenario.iv_rank * 0.22 + scenario.front_event_bump * 0.08, 0.05, 1.20)
    back_iv = clamp(front_iv + scenario.term_slope, 0.05, 1.20)
    atm_iv = round((front_iv + back_iv) / 2.0, 6)
    wing_lift = scenario.wing_elevation * 0.07
    put_lift = scenario.put_skew * 0.05
    call_lift = scenario.call_skew * 0.05
    points = [
        IVSurfacePoint("front", "put_wing", "put", round(front_iv + wing_lift + put_lift, 6), round(wing_lift + put_lift, 6), 0.18, "front put wing"),
        IVSurfacePoint("front", "atm", "call", round(front_iv, 6), round(front_iv - atm_iv, 6), 0.22, "front atm call"),
        IVSurfacePoint("front", "call_wing", "call", round(front_iv + wing_lift + call_lift, 6), round(wing_lift + call_lift, 6), 0.18, "front call wing"),
        IVSurfacePoint("back", "put_wing", "put", round(back_iv + wing_lift * 0.70 + put_lift * 0.70, 6), round(back_iv - atm_iv + wing_lift * 0.70 + put_lift * 0.70, 6), 0.14, "back put wing"),
        IVSurfacePoint("back", "atm", "call", round(back_iv, 6), round(back_iv - atm_iv, 6), 0.14, "back atm call"),
        IVSurfacePoint("back", "call_wing", "call", round(back_iv + wing_lift * 0.70 + call_lift * 0.70, 6), round(back_iv - atm_iv + wing_lift * 0.70 + call_lift * 0.70, 6), 0.14, "back call wing"),
    ]
    convexity = round(clamp(scenario.wing_elevation * 0.70 + max(scenario.put_skew, scenario.call_skew) * 0.30, 0.0, 1.0), 6)
    stability = round(clamp(1.0 - scenario.surface_instability, 0.0, 1.0), 6)
    opportunity = round(clamp(
        scenario.iv_expansion_potential * 0.42
        + scenario.iv_crush_risk * 0.24
        + scenario.wing_elevation * 0.18
        + stability * 0.16,
        0.0,
        1.0,
    ), 6)
    return IVSurfaceGrid(
        surface_id=f"surface-{scenario.scenario_id}",
        underlying=underlying,
        regime_tag=scenario.regime_tag,
        points=points,
        atm_iv=atm_iv,
        front_iv=round(front_iv, 6),
        back_iv=round(back_iv, 6),
        wings_elevated=scenario.wing_elevation >= 0.55,
        surface_stability_score=stability,
        surface_convexity_score=convexity,
        surface_opportunity_score=opportunity,
    )


def summarize_iv_surface_risk(scenario: IVSurfaceScenario, grid: IVSurfaceGrid) -> IVSurfaceRiskSummary:
    term_risk = clamp(
        abs(scenario.term_slope) * 5.0 + scenario.front_event_bump * 0.35 + max(0.0, -scenario.term_slope) * 2.5,
        0.0,
        1.0,
    )
    skew_risk = clamp(max(scenario.put_skew, scenario.call_skew) * 0.72 + scenario.wing_elevation * 0.28, 0.0, 1.0)
    premium_overpayment = clamp(
        scenario.iv_rank * 0.42
        + scenario.iv_percentile * 0.22
        + scenario.iv_crush_risk * 0.24
        + scenario.front_event_bump * 0.18
        - scenario.iv_expansion_potential * 0.18,
        0.0,
        1.0,
    )
    compression = clamp(
        scenario.iv_crush_risk * 0.55
        + (1.0 - scenario.surface_instability) * 0.25
        + max(0.0, scenario.term_slope) * 1.20
        + (1.0 - scenario.wing_elevation) * 0.10,
        0.0,
        1.0,
    )
    expansion = clamp(
        scenario.iv_expansion_potential * 0.52
        + scenario.front_event_bump * 0.18
        + scenario.wing_elevation * 0.18
        + max(0.0, -scenario.term_slope) * 1.20,
        0.0,
        1.0,
    )
    flags: list[str] = []
    if scenario.iv_crush_risk >= 0.72:
        flags.append("iv_crush_danger")
    if scenario.iv_expansion_potential >= 0.72:
        flags.append("iv_expansion_opportunity")
    if premium_overpayment >= 0.72:
        flags.append("premium_overpayment_trap")
    if scenario.front_event_bump >= 0.65:
        flags.append("front_expiry_event_bump")
    if scenario.wing_elevation >= 0.65:
        flags.append("wing_elevation")
    if scenario.surface_instability >= 0.70:
        flags.append("surface_instability")
    if scenario.term_slope <= -0.05:
        flags.append("backwardation")
    if scenario.term_slope >= 0.04:
        flags.append("contango")

    if premium_overpayment >= 0.78:
        verdict = "premium_overpayment_trap"
    elif scenario.iv_crush_risk >= 0.78 and scenario.iv_expansion_potential <= 0.35:
        verdict = "iv_crush_danger"
    elif expansion >= 0.78 and scenario.surface_instability <= 0.60:
        verdict = "excellent_expansion_setup"
    elif expansion >= 0.65:
        verdict = "good_expansion_setup"
    elif compression >= 0.66:
        verdict = "compression_opportunity"
    elif scenario.surface_instability >= 0.82:
        verdict = "reject"
    elif scenario.surface_instability >= 0.62 or term_risk >= 0.72:
        verdict = "fragile_surface"
    else:
        verdict = "neutral_surface"

    return IVSurfaceRiskSummary(
        iv_crush_score=round(clamp(scenario.iv_crush_risk, 0.0, 1.0), 6),
        iv_expansion_score=round(clamp(scenario.iv_expansion_potential, 0.0, 1.0), 6),
        term_structure_risk_score=round(term_risk, 6),
        skew_risk_score=round(skew_risk, 6),
        surface_instability_score=round(clamp(scenario.surface_instability, 0.0, 1.0), 6),
        premium_overpayment_score=round(premium_overpayment, 6),
        compression_opportunity_score=round(compression, 6),
        expansion_opportunity_score=round(expansion, 6),
        risk_flags=flags,
        verdict=verdict,
    )
