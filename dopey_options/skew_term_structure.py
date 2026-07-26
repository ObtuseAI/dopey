"""Expanded deterministic skew and term-structure fixture scoring."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .iv_surface_expansion import IVSurfaceScenario, clamp


SKEW_TERM_STRUCTURE_VERSION = "dopey-skew-term-structure-v1"


@dataclass(frozen=True)
class SkewProfile:
    put_skew_score: float
    call_skew_score: float
    skew_steepness: float
    skew_direction: str
    left_tail_pressure: float
    right_tail_pressure: float
    skew_opportunity_score: float
    skew_trap_score: float
    version: str = SKEW_TERM_STRUCTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TermStructureProfile:
    front_iv: float
    back_iv: float
    term_slope: float
    term_state: str
    event_bump_score: float
    backwardation_pressure: float
    contango_pressure: float
    roll_down_risk: float
    term_opportunity_score: float
    term_risk_score: float
    version: str = SKEW_TERM_STRUCTURE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SkewTermScore:
    scenario_id: str
    strategy_family: str
    skew_fit_score: float
    term_fit_score: float
    combined_score: float
    penalty_score: float
    risk_flags: list[str]
    version: str = SKEW_TERM_STRUCTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk_flags"] = sorted(self.risk_flags)
        return data


@dataclass(frozen=True)
class SkewTermVerdict:
    scenario_id: str
    strategy_family: str
    verdict: str
    score: float
    reasons: list[str]
    version: str = SKEW_TERM_STRUCTURE_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reasons"] = sorted(self.reasons)
        return data


def build_skew_profile(scenario: IVSurfaceScenario) -> SkewProfile:
    steepness = clamp(abs(scenario.put_skew - scenario.call_skew) + scenario.wing_elevation * 0.35, 0.0, 1.0)
    if scenario.put_skew > scenario.call_skew + 0.10:
        direction = "put_skew"
    elif scenario.call_skew > scenario.put_skew + 0.10:
        direction = "call_skew"
    else:
        direction = "balanced"
    opportunity = clamp(max(scenario.put_skew, scenario.call_skew) * 0.50 + scenario.wing_elevation * 0.35 + (1.0 - scenario.surface_instability) * 0.15, 0.0, 1.0)
    trap = clamp(steepness * 0.48 + scenario.surface_instability * 0.36 + scenario.iv_crush_risk * 0.16, 0.0, 1.0)
    return SkewProfile(
        put_skew_score=round(clamp(scenario.put_skew, 0.0, 1.0), 6),
        call_skew_score=round(clamp(scenario.call_skew, 0.0, 1.0), 6),
        skew_steepness=round(steepness, 6),
        skew_direction=direction,
        left_tail_pressure=round(clamp(scenario.put_skew * 0.75 + scenario.surface_instability * 0.25, 0.0, 1.0), 6),
        right_tail_pressure=round(clamp(scenario.call_skew * 0.75 + scenario.surface_instability * 0.25, 0.0, 1.0), 6),
        skew_opportunity_score=round(opportunity, 6),
        skew_trap_score=round(trap, 6),
    )


def build_term_structure_profile(scenario: IVSurfaceScenario) -> TermStructureProfile:
    front_iv = clamp(0.16 + scenario.iv_rank * 0.22 + scenario.front_event_bump * 0.10, 0.05, 1.20)
    back_iv = clamp(front_iv + scenario.term_slope, 0.05, 1.20)
    if scenario.surface_instability >= 0.75:
        state = "unstable"
    elif scenario.front_event_bump >= 0.72 and scenario.term_slope < -0.03:
        state = "front_event_bump"
    elif scenario.term_slope <= -0.06:
        state = "backwardation"
    elif scenario.iv_crush_risk >= 0.75 and scenario.front_event_bump <= 0.25:
        state = "post_event_collapse"
    elif scenario.term_slope >= 0.025:
        state = "normal_contango"
    else:
        state = "flat"
    backwardation = clamp(max(0.0, -scenario.term_slope) * 7.5 + scenario.front_event_bump * 0.25, 0.0, 1.0)
    contango = clamp(max(0.0, scenario.term_slope) * 8.0, 0.0, 1.0)
    roll_down = clamp(scenario.front_event_bump * 0.44 + scenario.iv_crush_risk * 0.28 + abs(scenario.term_slope) * 2.0, 0.0, 1.0)
    opportunity = clamp(
        (0.40 if state in {"front_event_bump", "backwardation"} else 0.0)
        + (0.35 if state in {"post_event_collapse", "normal_contango", "flat"} else 0.0)
        + scenario.iv_expansion_potential * 0.20
        + scenario.iv_crush_risk * 0.20,
        0.0,
        1.0,
    )
    risk = clamp(backwardation * 0.35 + roll_down * 0.35 + scenario.surface_instability * 0.30, 0.0, 1.0)
    return TermStructureProfile(
        front_iv=round(front_iv, 6),
        back_iv=round(back_iv, 6),
        term_slope=round(scenario.term_slope, 6),
        term_state=state,
        event_bump_score=round(clamp(scenario.front_event_bump, 0.0, 1.0), 6),
        backwardation_pressure=round(backwardation, 6),
        contango_pressure=round(contango, 6),
        roll_down_risk=round(roll_down, 6),
        term_opportunity_score=round(opportunity, 6),
        term_risk_score=round(risk, 6),
    )


def score_skew_term_for_family(
    strategy_family: str,
    scenario: IVSurfaceScenario,
    skew: SkewProfile,
    term: TermStructureProfile,
) -> SkewTermScore:
    flags: list[str] = []
    if strategy_family == "volatility_expansion":
        skew_fit = clamp(0.40 + skew.skew_opportunity_score * 0.36 + scenario.wing_elevation * 0.24, 0.0, 1.0)
        term_fit = clamp(term.event_bump_score * 0.45 + term.backwardation_pressure * 0.35 + term.term_opportunity_score * 0.20, 0.0, 1.0)
        penalty = clamp(scenario.iv_crush_risk * 0.55 + term.roll_down_risk * 0.20, 0.0, 1.0)
    elif strategy_family == "volatility_compression":
        skew_fit = clamp((1.0 - skew.skew_trap_score) * 0.55 + scenario.iv_crush_risk * 0.45, 0.0, 1.0)
        term_fit = clamp((1.0 - term.backwardation_pressure) * 0.55 + (0.45 if term.term_state in {"normal_contango", "flat", "post_event_collapse"} else 0.0), 0.0, 1.0)
        penalty = clamp(term.backwardation_pressure * 0.55 + scenario.front_event_bump * 0.30 + scenario.wing_elevation * 0.20, 0.0, 1.0)
    elif strategy_family == "short_duration_defined_risk":
        skew_fit = clamp(1.0 - skew.skew_trap_score * 0.80, 0.0, 1.0)
        term_fit = clamp(1.0 - term.term_risk_score * 0.85, 0.0, 1.0)
        penalty = clamp(term.event_bump_score * 0.45 + scenario.surface_instability * 0.35 + skew.skew_trap_score * 0.25, 0.0, 1.0)
    else:
        directional_skew = max(skew.call_skew_score, skew.put_skew_score)
        skew_fit = clamp(0.52 + directional_skew * 0.24 + (1.0 - skew.skew_trap_score) * 0.24, 0.0, 1.0)
        term_fit = clamp(1.0 - term.term_risk_score * 0.50, 0.0, 1.0)
        penalty = clamp(scenario.surface_instability * 0.40 + skew.skew_trap_score * 0.35 + scenario.iv_crush_risk * 0.20, 0.0, 1.0)
    if penalty >= 0.65:
        flags.append("skew_term_trap")
    if term.term_state in {"front_event_bump", "backwardation", "unstable"}:
        flags.append(term.term_state)
    return SkewTermScore(
        scenario_id=scenario.scenario_id,
        strategy_family=strategy_family,
        skew_fit_score=round(skew_fit, 6),
        term_fit_score=round(term_fit, 6),
        combined_score=round(clamp(0.50 * skew_fit + 0.50 * term_fit - penalty * 0.18, 0.0, 1.0), 6),
        penalty_score=round(penalty, 6),
        risk_flags=flags,
    )
