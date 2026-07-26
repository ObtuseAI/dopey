"""Deterministic Greeks exposure, risk-fit, and attribution validation.

This module scores paper option structures against fixture Greeks and IV context. It is pure
fixture math: no live pricing, no broker calls, no market-data fetches, and no profit claims.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

from .iv_surface_fixture import IVContext, IVSurfaceSummary, SkewSummary, TermStructureSummary


GREEKS_VALIDATION_MODEL_VERSION = "dopey-greeks-validation-v1"


@dataclass(frozen=True)
class GreekVector:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float
    source: str
    notes: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GreekVector":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class GreekExposureSummary:
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    net_rho: float
    absolute_delta: float
    absolute_gamma: float
    theta_decay_pressure: float
    vega_sensitivity: float
    convexity_score: float
    directional_exposure_score: float
    volatility_exposure_score: float
    model_version: str = GREEKS_VALIDATION_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GreekRiskVerdict:
    strategy_id: str
    strategy_family: str
    greek_fit_score: float
    delta_fit_score: float
    gamma_fit_score: float
    theta_fit_score: float
    vega_fit_score: float
    risk_flags: list[str] = field(default_factory=list)
    verdict: str = "acceptable_fit"
    model_version: str = GREEKS_VALIDATION_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GreekAttributionResult:
    strategy_id: str
    window_id: str
    strategy_family: str
    delta_contribution: float
    gamma_contribution: float
    theta_contribution: float
    vega_contribution: float
    iv_contribution: float
    residual_fixture_effect: float
    attribution_quality_score: float
    notes: str
    model_version: str = GREEKS_VALIDATION_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyGreekProfile:
    strategy_family: str
    preferred_delta_range: tuple[float, float]
    preferred_gamma_bias: str
    preferred_theta_bias: str
    preferred_vega_bias: str
    preferred_iv_regime: str
    preferred_term_structure: str
    preferred_skew_context: str
    avoid_conditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["preferred_delta_range"] = list(self.preferred_delta_range)
        return data


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fit_from_distance(value: float, target_low: float, target_high: float, tolerance: float) -> float:
    if target_low <= value <= target_high:
        return 1.0
    if value < target_low:
        return _clamp(1.0 - ((target_low - value) / tolerance), 0.0, 1.0)
    return _clamp(1.0 - ((value - target_high) / tolerance), 0.0, 1.0)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _side_multiplier(side: str) -> float:
    return -1.0 if side == "sell" else 1.0


def greek_vector_from_leg(leg: dict[str, Any]) -> GreekVector:
    return GreekVector(
        delta=round(float(leg.get("delta", 0.0)), 6),
        gamma=round(float(leg.get("gamma", 0.0)), 6),
        theta=round(float(leg.get("theta", 0.0)), 6),
        vega=round(float(leg.get("vega", 0.0)), 6),
        rho=round(float(leg.get("rho", 0.0)), 6),
        iv=round(float(leg.get("iv", 0.0)), 6),
        source=str(leg.get("symbol", "")),
        notes=str(leg.get("notes", "fixture_contract_greeks")),
    )


def summarize_greek_exposure(legs: list[dict[str, Any]]) -> GreekExposureSummary:
    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0
    net_rho = 0.0
    absolute_delta = 0.0
    absolute_gamma = 0.0
    for leg in legs:
        ratio = float(leg.get("ratio", 1.0))
        side = _side_multiplier(str(leg.get("side", "buy")))
        vector = greek_vector_from_leg(leg)
        mult = ratio * side
        net_delta += vector.delta * mult
        net_gamma += vector.gamma * mult
        net_theta += vector.theta * mult
        net_vega += vector.vega * mult
        net_rho += vector.rho * mult
        absolute_delta += abs(vector.delta * ratio)
        absolute_gamma += abs(vector.gamma * ratio)
    theta_pressure = _clamp(max(0.0, -net_theta) / 0.35, 0.0, 1.0)
    vega_sensitivity = _clamp(abs(net_vega) / 0.75, 0.0, 1.0)
    convexity = _clamp(max(0.0, net_gamma) * 35.0 + absolute_gamma * 4.0, 0.0, 1.0)
    directional = _clamp(abs(net_delta) / 0.85, 0.0, 1.0)
    volatility = _clamp(max(0.0, net_vega) / 0.65, 0.0, 1.0)
    return GreekExposureSummary(
        net_delta=round(net_delta, 6),
        net_gamma=round(net_gamma, 6),
        net_theta=round(net_theta, 6),
        net_vega=round(net_vega, 6),
        net_rho=round(net_rho, 6),
        absolute_delta=round(absolute_delta, 6),
        absolute_gamma=round(absolute_gamma, 6),
        theta_decay_pressure=round(theta_pressure, 6),
        vega_sensitivity=round(vega_sensitivity, 6),
        convexity_score=round(convexity, 6),
        directional_exposure_score=round(directional, 6),
        volatility_exposure_score=round(volatility, 6),
    )


def strategy_greek_profile(strategy_family: str) -> StrategyGreekProfile:
    profiles = {
        "directional_convexity": StrategyGreekProfile(
            strategy_family="directional_convexity",
            preferred_delta_range=(0.20, 0.75),
            preferred_gamma_bias="positive",
            preferred_theta_bias="controlled_negative",
            preferred_vega_bias="moderate_positive",
            preferred_iv_regime="normal_or_expansion",
            preferred_term_structure="flat_or_mild_backwardation",
            preferred_skew_context="directional_not_extreme",
            avoid_conditions=["wrong_sign_delta", "iv_crush_with_high_vega", "range_bound_theta_bleed"],
        ),
        "volatility_expansion": StrategyGreekProfile(
            strategy_family="volatility_expansion",
            preferred_delta_range=(-0.20, 0.20),
            preferred_gamma_bias="positive",
            preferred_theta_bias="tolerable_negative",
            preferred_vega_bias="positive",
            preferred_iv_regime="expansion_potential",
            preferred_term_structure="front_event_bump_or_backwardation",
            preferred_skew_context="elevated_wings",
            avoid_conditions=["post_event_iv_crush", "high_iv_rank_without_expansion", "theta_without_movement"],
        ),
        "volatility_compression": StrategyGreekProfile(
            strategy_family="volatility_compression",
            preferred_delta_range=(-0.20, 0.20),
            preferred_gamma_bias="controlled_or_negative",
            preferred_theta_bias="positive",
            preferred_vega_bias="negative",
            preferred_iv_regime="crush_potential",
            preferred_term_structure="flat_or_contango",
            preferred_skew_context="stable_skew",
            avoid_conditions=["macro_shock", "event_vol_expansion", "excessive_gamma_risk"],
        ),
        "short_duration_defined_risk": StrategyGreekProfile(
            strategy_family="short_duration_defined_risk",
            preferred_delta_range=(0.05, 0.55),
            preferred_gamma_bias="useful_positive",
            preferred_theta_bias="tight_window",
            preferred_vega_bias="low",
            preferred_iv_regime="low_to_normal",
            preferred_term_structure="flat",
            preferred_skew_context="stable_skew",
            avoid_conditions=["bad_spreads", "low_liquidity_decay", "theta_gamma_instability", "fakeout"],
        ),
    }
    return profiles.get(strategy_family, profiles["directional_convexity"])


def _expected_direction(regime_tag: str) -> str:
    if regime_tag in {"bearish_breakdown", "macro_shock_risk_off"}:
        return "bearish"
    if regime_tag in {"bullish_breakout", "trend_vol_expansion"}:
        return "bullish"
    return "neutral"


def _delta_fit(strategy_family: str, exposure: GreekExposureSummary, regime_tag: str) -> tuple[float, list[str]]:
    flags: list[str] = []
    expected = _expected_direction(regime_tag)
    profile = strategy_greek_profile(strategy_family)
    if strategy_family == "directional_convexity":
        if expected == "bullish":
            score = _fit_from_distance(exposure.net_delta, 0.15, 0.80, 0.60)
            if exposure.net_delta <= 0.0:
                flags.append("wrong_sign_delta")
        elif expected == "bearish":
            score = _fit_from_distance(exposure.net_delta, -0.80, -0.15, 0.60)
            if exposure.net_delta >= 0.0:
                flags.append("wrong_sign_delta")
        else:
            score = _fit_from_distance(abs(exposure.net_delta), 0.05, 0.45, 0.60)
    elif strategy_family in {"volatility_expansion", "volatility_compression"}:
        score = _fit_from_distance(exposure.net_delta, profile.preferred_delta_range[0],
                                   profile.preferred_delta_range[1], 0.60)
        if abs(exposure.net_delta) > 0.45:
            flags.append("excessive_directional_delta")
    else:
        if expected == "bullish":
            score = _fit_from_distance(exposure.net_delta, 0.05, 0.60, 0.55)
        elif expected == "bearish":
            score = _fit_from_distance(exposure.net_delta, -0.15, 0.25, 0.55)
        else:
            score = _fit_from_distance(abs(exposure.net_delta), 0.00, 0.45, 0.55)
    return round(score, 6), flags


def _gamma_fit(strategy_family: str, exposure: GreekExposureSummary, regime_tag: str) -> tuple[float, list[str]]:
    flags: list[str] = []
    if strategy_family in {"directional_convexity", "volatility_expansion"}:
        score = _clamp(exposure.convexity_score, 0.0, 1.0)
        if exposure.net_gamma < -0.005:
            flags.append("negative_gamma_for_convexity")
    elif strategy_family == "volatility_compression":
        score = _clamp(1.0 - exposure.absolute_gamma * 18.0, 0.0, 1.0)
        if exposure.absolute_gamma > 0.05:
            flags.append("excessive_gamma_risk")
    else:
        clean = regime_tag in {"bullish_breakout", "trend_vol_expansion", "bearish_breakdown"}
        useful = exposure.convexity_score if clean else 1.0 - exposure.theta_decay_pressure * 0.50
        score = _clamp(useful, 0.0, 1.0)
        if not clean and exposure.absolute_gamma > 0.05:
            flags.append("gamma_instability")
    return round(score, 6), flags


def _theta_fit(strategy_family: str, exposure: GreekExposureSummary, regime_tag: str,
               liquidity_score: float) -> tuple[float, list[str]]:
    flags: list[str] = []
    if strategy_family == "volatility_compression":
        score = _clamp(0.65 + max(0.0, exposure.net_theta) * 2.0, 0.0, 1.0)
        if exposure.net_theta < -0.05:
            flags.append("compression_negative_theta")
    elif strategy_family == "short_duration_defined_risk":
        pressure = exposure.theta_decay_pressure
        if regime_tag in {"high_spread_bad_fill", "low_liquidity_decay", "gap_reversal"}:
            pressure = min(1.0, pressure + (1.0 - liquidity_score) * 0.65 + 0.25)
        score = _clamp(1.0 - pressure, 0.0, 1.0)
        if score < 0.45:
            flags.append("theta_gamma_liquidity_combo")
    elif strategy_family == "volatility_expansion":
        score = _clamp(1.0 - exposure.theta_decay_pressure * 0.70, 0.0, 1.0)
        if exposure.theta_decay_pressure > 0.75:
            flags.append("theta_without_movement")
    else:
        score = _clamp(1.0 - exposure.theta_decay_pressure * 0.65, 0.0, 1.0)
        if regime_tag in {"chop_vol_compression", "range_bound_pin"} and exposure.theta_decay_pressure > 0.55:
            flags.append("range_bound_theta_bleed")
    return round(score, 6), flags


def _vega_fit(strategy_family: str, exposure: GreekExposureSummary, iv_context: IVContext,
              regime_tag: str) -> tuple[float, list[str]]:
    flags: list[str] = []
    if strategy_family == "volatility_expansion":
        score = _clamp(
            0.50 * exposure.volatility_exposure_score
            + 0.35 * iv_context.iv_expansion_potential
            + 0.15 * (1.0 - iv_context.iv_crush_risk),
            0.0,
            1.0,
        )
        if iv_context.iv_crush_risk > 0.65:
            flags.append("iv_crush_risk_against_long_vega")
            score = min(score, 0.45)
    elif strategy_family == "volatility_compression":
        negative_vega_score = _clamp(max(0.0, -exposure.net_vega) / 0.55, 0.0, 1.0)
        score = _clamp(0.45 * negative_vega_score + 0.45 * iv_context.iv_crush_risk
                       + 0.10 * (1.0 - iv_context.iv_expansion_potential), 0.0, 1.0)
        if regime_tag in {"event_vol_expansion", "macro_shock_risk_off"}:
            flags.append("compression_exposed_to_expansion")
            score = min(score, 0.40)
    elif strategy_family == "short_duration_defined_risk":
        score = _clamp(1.0 - exposure.vega_sensitivity * 0.75 - iv_context.iv_crush_risk * 0.15, 0.0, 1.0)
        if exposure.vega_sensitivity > 0.55:
            flags.append("short_duration_vega_noise")
    else:
        score = _clamp(1.0 - abs(exposure.net_vega) * 0.65, 0.0, 1.0)
        if regime_tag == "post_event_iv_crush" and exposure.net_vega > 0.20:
            flags.append("iv_crush_with_high_vega")
            score = min(score, 0.45)
    return round(score, 6), flags


def iv_surface_family_score(
    strategy_family: str,
    iv_context: IVContext,
    surface: IVSurfaceSummary,
    skew: SkewSummary,
    term: TermStructureSummary,
    regime_tag: str,
) -> dict[str, float]:
    if strategy_family == "volatility_expansion":
        iv_score = 0.45 * iv_context.iv_expansion_potential + 0.25 * surface.surface_opportunity_score + 0.30 * (1.0 - iv_context.iv_crush_risk)
        skew_score = 0.70 * surface.surface_opportunity_score + 0.30 * skew.skew_opportunity_score
        term_score = 0.65 * term.event_bump_score + 0.35 * term.term_opportunity_score
    elif strategy_family == "volatility_compression":
        iv_score = 0.55 * iv_context.iv_crush_risk + 0.25 * (1.0 - iv_context.iv_expansion_potential) + 0.20 * surface.surface_stability_score
        skew_score = 0.75 * (1.0 - skew.skew_risk_score) + 0.25 * surface.surface_stability_score
        term_score = 0.60 * (1.0 - term.term_risk_score) + 0.40 * (1.0 if term.contango_backwardation_state in {"flat", "contango"} else 0.4)
        if regime_tag in {"event_vol_expansion", "macro_shock_risk_off"}:
            iv_score *= 0.55
            term_score *= 0.65
    elif strategy_family == "short_duration_defined_risk":
        iv_score = 0.45 * (1.0 - iv_context.iv_crush_risk) + 0.35 * (1.0 - iv_context.iv_rank) + 0.20 * surface.surface_stability_score
        skew_score = 1.0 - skew.skew_risk_score * 0.75
        term_score = 1.0 - term.term_risk_score * 0.70
    else:
        iv_score = 0.45 * (1.0 - iv_context.iv_crush_risk) + 0.35 * iv_context.iv_expansion_potential + 0.20 * surface.surface_stability_score
        skew_score = 1.0 - skew.skew_risk_score * 0.45
        term_score = 1.0 - term.term_risk_score * 0.35
    return {
        "iv_context_score": round(_clamp(iv_score, 0.0, 1.0), 6),
        "skew_score": round(_clamp(skew_score, 0.0, 1.0), 6),
        "term_structure_score": round(_clamp(term_score, 0.0, 1.0), 6),
    }


def _verdict(score: float, flags: list[str]) -> str:
    if score < 0.20 or "wrong_sign_delta" in flags:
        return "reject" if score < 0.18 else "poor_fit"
    if score >= 0.85:
        return "excellent_fit"
    if score >= 0.70:
        return "good_fit"
    if score >= 0.55:
        return "acceptable_fit"
    if score >= 0.38:
        return "fragile_fit"
    return "poor_fit"


def evaluate_greek_risk(
    strategy_id: str,
    strategy_family: str,
    exposure: GreekExposureSummary,
    iv_context: IVContext,
    surface: IVSurfaceSummary,
    skew: SkewSummary,
    term: TermStructureSummary,
    regime_tag: str,
    liquidity_score: float,
) -> GreekRiskVerdict:
    delta_score, delta_flags = _delta_fit(strategy_family, exposure, regime_tag)
    gamma_score, gamma_flags = _gamma_fit(strategy_family, exposure, regime_tag)
    theta_score, theta_flags = _theta_fit(strategy_family, exposure, regime_tag, liquidity_score)
    vega_score, vega_flags = _vega_fit(strategy_family, exposure, iv_context, regime_tag)
    iv_scores = iv_surface_family_score(strategy_family, iv_context, surface, skew, term, regime_tag)
    flags = sorted(set(delta_flags + gamma_flags + theta_flags + vega_flags))
    greek_fit = round(_clamp(
        0.22 * delta_score
        + 0.20 * gamma_score
        + 0.18 * theta_score
        + 0.20 * vega_score
        + 0.10 * iv_scores["iv_context_score"]
        + 0.05 * iv_scores["skew_score"]
        + 0.05 * iv_scores["term_structure_score"],
        0.0,
        1.0,
    ), 6)
    if "wrong_sign_delta" in flags:
        greek_fit = min(greek_fit, 0.32)
    return GreekRiskVerdict(
        strategy_id=strategy_id,
        strategy_family=strategy_family,
        greek_fit_score=greek_fit,
        delta_fit_score=delta_score,
        gamma_fit_score=gamma_score,
        theta_fit_score=theta_score,
        vega_fit_score=vega_score,
        risk_flags=flags,
        verdict=_verdict(greek_fit, flags),
    )


def attribute_greek_outcome(
    strategy_id: str,
    window_id: str,
    strategy_family: str,
    exposure: GreekExposureSummary,
    paper_pnl: float,
    start_price: float,
    end_price: float,
    start_iv: float,
    end_iv: float,
    days_to_exit: int,
) -> GreekAttributionResult:
    price_move = end_price - start_price
    iv_move = end_iv - start_iv
    delta_contribution = exposure.net_delta * price_move
    gamma_contribution = 0.5 * exposure.net_gamma * (price_move ** 2)
    theta_contribution = exposure.net_theta * float(days_to_exit)
    vega_contribution = exposure.net_vega * iv_move * 100.0
    iv_contribution = iv_move * 10.0
    explained = delta_contribution + gamma_contribution + theta_contribution + vega_contribution + iv_contribution
    residual = paper_pnl - explained
    denominator = abs(paper_pnl) + abs(delta_contribution) + abs(gamma_contribution) + abs(theta_contribution) + abs(vega_contribution) + abs(iv_contribution) + 1.0
    quality = round(_clamp(1.0 - abs(residual) / denominator, 0.0, 1.0), 6)
    return GreekAttributionResult(
        strategy_id=strategy_id,
        window_id=window_id,
        strategy_family=strategy_family,
        delta_contribution=round(delta_contribution, 6),
        gamma_contribution=round(gamma_contribution, 6),
        theta_contribution=round(theta_contribution, 6),
        vega_contribution=round(vega_contribution, 6),
        iv_contribution=round(iv_contribution, 6),
        residual_fixture_effect=round(residual, 6),
        attribution_quality_score=quality,
        notes="deterministic fixture Greek attribution, not empirical PnL explanation",
    )


def summarize_profile_strengths(
    strategy_family: str,
    verdicts: list[GreekRiskVerdict],
) -> tuple[list[str], list[str]]:
    avg_delta = _mean([v.delta_fit_score for v in verdicts])
    avg_gamma = _mean([v.gamma_fit_score for v in verdicts])
    avg_theta = _mean([v.theta_fit_score for v in verdicts])
    avg_vega = _mean([v.vega_fit_score for v in verdicts])
    strengths: list[str] = []
    weaknesses: list[str] = []
    if avg_delta >= 0.65:
        strengths.append("delta exposure fits family/regime")
    else:
        weaknesses.append("delta exposure mismatch")
    if avg_gamma >= 0.65:
        strengths.append("gamma profile useful or controlled")
    else:
        weaknesses.append("gamma profile fragile")
    if avg_theta >= 0.65:
        strengths.append("theta profile controlled")
    else:
        weaknesses.append("theta decay pressure")
    if avg_vega >= 0.65:
        strengths.append("vega exposure fits IV context")
    else:
        weaknesses.append("vega exposure conflicts with IV context")
    if not strengths:
        strengths.append(f"{strategy_family} has no dominant Greek strength in this corpus")
    if not weaknesses:
        weaknesses.append(f"{strategy_family} has no dominant Greek weakness in this corpus")
    return strengths, weaknesses
