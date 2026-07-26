"""Family-specific deterministic IV surface, skew, and term scoring."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .iv_surface_expansion import (
    IVOpportunityVerdict,
    IVSurfaceScenario,
    build_surface_grid,
    clamp,
    summarize_iv_surface_risk,
)
from .skew_term_structure import (
    build_skew_profile,
    build_term_structure_profile,
    score_skew_term_for_family,
)


IV_FAMILY_SCORING_VERSION = "dopey-iv-family-scoring-v1"


@dataclass(frozen=True)
class FamilyIVSurfaceScore:
    strategy_family: str
    scenario_id: str
    regime_tag: str
    family_iv_fit_score: float
    iv_surface_fit_score: float
    skew_term_score: float
    premium_overpayment_score: float
    iv_crush_expansion_mismatch_penalty: float
    surface_instability_penalty: float
    term_structure_risk_penalty: float
    iv_crush_score: float
    iv_expansion_score: float
    front_event_bump_score: float
    skew_trap_score: float
    wing_elevation_score: float
    risk_flags: list[str]
    verdict: str
    version: str = IV_FAMILY_SCORING_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk_flags"] = sorted(self.risk_flags)
        return data


def _moderate_iv_score(iv_rank: float) -> float:
    return clamp(1.0 - abs(iv_rank - 0.45) / 0.55, 0.0, 1.0)


def _family_base_score(strategy_family: str, scenario: IVSurfaceScenario) -> tuple[float, list[str]]:
    flags: list[str] = []
    grid = build_surface_grid(scenario, "SPY_FIXTURE")
    risk = summarize_iv_surface_risk(scenario, grid)
    skew = build_skew_profile(scenario)
    term = build_term_structure_profile(scenario)
    skew_term = score_skew_term_for_family(strategy_family, scenario, skew, term)

    if strategy_family == "volatility_expansion":
        score = (
            0.36 * risk.expansion_opportunity_score
            + 0.20 * scenario.front_event_bump
            + 0.16 * scenario.wing_elevation
            + 0.16 * term.backwardation_pressure
            + 0.12 * skew_term.combined_score
        )
        if scenario.iv_crush_risk >= 0.72:
            flags.append("iv_crush_after_vol_expansion_risk")
            score -= 0.22
        if scenario.iv_rank >= 0.78 and scenario.iv_expansion_potential < 0.45:
            flags.append("high_iv_without_expansion_catalyst")
            score -= 0.18
        if risk.premium_overpayment_score >= 0.70:
            flags.append("premium_overpayment_trap")
            score -= 0.14
        if scenario.surface_instability >= 0.70 and scenario.iv_expansion_potential < 0.70:
            flags.append("unstable_surface_without_movement_confirmation")
            score -= 0.12
    elif strategy_family == "volatility_compression":
        score = (
            0.38 * risk.compression_opportunity_score
            + 0.24 * scenario.iv_crush_risk
            + 0.16 * (1.0 - term.backwardation_pressure)
            + 0.12 * (1.0 - skew.skew_trap_score)
            + 0.10 * grid.surface_stability_score
        )
        if scenario.front_event_bump >= 0.65:
            flags.append("front_event_bump_against_compression")
            score -= 0.22
        if term.backwardation_pressure >= 0.62:
            flags.append("backwardation_against_compression")
            score -= 0.20
        if scenario.wing_elevation >= 0.65 and scenario.iv_expansion_potential >= 0.55:
            flags.append("wing_elevation_breakout_risk")
            score -= 0.12
        if scenario.surface_instability >= 0.62:
            flags.append("unstable_skew_for_compression")
            score -= 0.10
    elif strategy_family == "short_duration_defined_risk":
        score = (
            0.32 * grid.surface_stability_score
            + 0.24 * (1.0 - risk.premium_overpayment_score)
            + 0.18 * (1.0 - skew.skew_trap_score)
            + 0.16 * (1.0 - term.term_risk_score)
            + 0.10 * _moderate_iv_score(scenario.iv_rank)
        )
        if scenario.front_event_bump >= 0.55:
            flags.append("short_duration_front_iv_instability")
            score -= 0.20
        if scenario.surface_instability >= 0.60:
            flags.append("surface_instability_short_duration")
            score -= 0.16
        if skew.skew_trap_score >= 0.62:
            flags.append("short_duration_skew_trap")
            score -= 0.12
    else:
        score = (
            0.28 * _moderate_iv_score(scenario.iv_rank)
            + 0.22 * grid.surface_stability_score
            + 0.18 * (1.0 - risk.premium_overpayment_score)
            + 0.16 * scenario.iv_expansion_potential
            + 0.10 * max(scenario.put_skew, scenario.call_skew)
            + 0.06 * skew_term.combined_score
        )
        if risk.premium_overpayment_score >= 0.70:
            flags.append("premium_overpayment_trap")
            score -= 0.20
        if scenario.iv_crush_risk >= 0.75 and scenario.iv_expansion_potential <= 0.35:
            flags.append("iv_crush_danger")
            score -= 0.12
        if skew.skew_trap_score >= 0.65:
            flags.append("skew_trap_against_directional")
            score -= 0.12
        if scenario.surface_instability >= 0.70:
            flags.append("surface_instability_fakeout_failure")
            score -= 0.16
    return clamp(score, 0.0, 1.0), sorted(set(flags + skew_term.risk_flags + risk.risk_flags))


def _verdict(score: float, flags: list[str]) -> str:
    if score >= 0.78:
        return "excellent_iv_fit"
    if score >= 0.64:
        return "good_iv_fit"
    if score >= 0.48:
        return "acceptable_iv_fit"
    if score >= 0.32:
        return "fragile_iv_fit"
    if "premium_overpayment_trap" in flags:
        return "premium_overpayment_trap"
    return "reject_iv_surface"


def score_family_iv_surface(strategy_family: str, scenario: IVSurfaceScenario) -> FamilyIVSurfaceScore:
    grid = build_surface_grid(scenario, "SPY_FIXTURE")
    risk = summarize_iv_surface_risk(scenario, grid)
    skew = build_skew_profile(scenario)
    term = build_term_structure_profile(scenario)
    skew_term = score_skew_term_for_family(strategy_family, scenario, skew, term)
    base, flags = _family_base_score(strategy_family, scenario)
    mismatch = 0.0
    if strategy_family == "volatility_expansion":
        mismatch = risk.iv_crush_score * 0.62 + risk.premium_overpayment_score * 0.25
    elif strategy_family == "volatility_compression":
        mismatch = risk.iv_expansion_score * 0.45 + scenario.front_event_bump * 0.35 + term.backwardation_pressure * 0.20
    elif strategy_family == "short_duration_defined_risk":
        mismatch = scenario.front_event_bump * 0.38 + risk.surface_instability_score * 0.32 + risk.premium_overpayment_score * 0.20
    else:
        mismatch = risk.premium_overpayment_score * 0.35 + risk.iv_crush_score * 0.25 + risk.surface_instability_score * 0.22
    family_score = clamp(base - mismatch * 0.12, 0.0, 1.0)
    return FamilyIVSurfaceScore(
        strategy_family=strategy_family,
        scenario_id=scenario.scenario_id,
        regime_tag=scenario.regime_tag,
        family_iv_fit_score=round(family_score, 6),
        iv_surface_fit_score=round(clamp(base, 0.0, 1.0), 6),
        skew_term_score=skew_term.combined_score,
        premium_overpayment_score=risk.premium_overpayment_score,
        iv_crush_expansion_mismatch_penalty=round(clamp(mismatch, 0.0, 1.0), 6),
        surface_instability_penalty=risk.surface_instability_score,
        term_structure_risk_penalty=risk.term_structure_risk_score,
        iv_crush_score=risk.iv_crush_score,
        iv_expansion_score=risk.iv_expansion_score,
        front_event_bump_score=round(clamp(scenario.front_event_bump, 0.0, 1.0), 6),
        skew_trap_score=round(skew.skew_trap_score, 6),
        wing_elevation_score=round(clamp(scenario.wing_elevation, 0.0, 1.0), 6),
        risk_flags=flags,
        verdict=_verdict(family_score, flags),
    )


def build_iv_opportunity_verdict(strategy_family: str, scenario: IVSurfaceScenario) -> IVOpportunityVerdict:
    score = score_family_iv_surface(strategy_family, scenario)
    return IVOpportunityVerdict(
        scenario_id=scenario.scenario_id,
        strategy_family=strategy_family,
        verdict=score.verdict,
        opportunity_score=score.family_iv_fit_score,
        risk_score=round(clamp(
            0.34 * score.premium_overpayment_score
            + 0.24 * score.iv_crush_expansion_mismatch_penalty
            + 0.22 * score.surface_instability_penalty
            + 0.20 * score.term_structure_risk_penalty,
            0.0,
            1.0,
        ), 6),
        reasons=score.risk_flags,
    )


def score_all_families_for_scenario(scenario: IVSurfaceScenario) -> dict[str, FamilyIVSurfaceScore]:
    families = [
        "directional_convexity",
        "volatility_expansion",
        "volatility_compression",
        "short_duration_defined_risk",
    ]
    return {family: score_family_iv_surface(family, scenario) for family in families}
