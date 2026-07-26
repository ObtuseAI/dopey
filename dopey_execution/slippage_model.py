"""Deterministic DOPEY fixture slippage model.

The model replaces the old fixed 0.2 percent paper slippage heuristic with a
regime-aware, contract-aware fixture calculation. It is deterministic paper
simulation only, not live execution quality or real market impact modeling.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


SLIPPAGE_MODEL_VERSION = "dopey-slippage-model-v1"
LEGACY_FIXED_SLIPPAGE_PCT_REFERENCE = 0.002


@dataclass(frozen=True)
class SlippageModelInput:
    mid: float
    spread_percentage: float
    liquidity_score: float
    regime_tag: str
    strategy_family: str
    structure_type: str
    leg_count: int
    volatility_regime_score: float = 0.5
    quote_stability_score: float = 0.5
    slippage_sensitivity_score: float = 0.2
    volume_open_interest_anomaly_score: float = 0.0
    high_spread_flag: bool = False
    low_liquidity_flag: bool = False
    event_vol_flag: bool = False
    macro_shock_flag: bool = False
    short_duration_flag: bool = False
    side: str = "buy"
    microstructure_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SlippageModelResult:
    expected_slippage_pct: float
    expected_slippage_amount: float
    worst_case_fixture_slippage_pct: float
    fill_price_adjustment: float
    fill_quality_score: float
    slippage_verdict: str
    model_version: str = SLIPPAGE_MODEL_VERSION
    legacy_fixed_slippage_pct_reference: float = LEGACY_FIXED_SLIPPAGE_PCT_REFERENCE

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _context_float(context: dict[str, Any], key: str, fallback: float) -> float:
    try:
        return float(context.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def _regime_slippage_penalty(regime_tag: str) -> float:
    penalties = {
        "high_spread_bad_fill": 0.018,
        "low_liquidity_decay": 0.015,
        "macro_shock_risk_off": 0.012,
        "event_vol_expansion": 0.010,
        "liquidity_decay": 0.009,
        "gap_reversal": 0.006,
        "post_event_iv_crush": 0.004,
    }
    return penalties.get(regime_tag, 0.0)


def _structure_penalty(structure_type: str, leg_count: int) -> float:
    structure_penalties = {
        "single": 0.000,
        "vertical": 0.002,
        "strangle": 0.005,
        "iron_condor": 0.007,
        "butterfly": 0.007,
    }
    leg_penalty = max(0, leg_count - 1) * 0.0025
    return structure_penalties.get(structure_type, 0.003) + leg_penalty


def _family_regime_penalty(
    strategy_family: str,
    regime_tag: str,
    structure_type: str,
    short_duration_flag: bool,
) -> float:
    penalty = 0.0
    if strategy_family == "short_duration_defined_risk" and regime_tag in {
        "high_spread_bad_fill", "low_liquidity_decay", "gap_reversal",
    }:
        penalty += 0.012
    if strategy_family == "directional_convexity" and regime_tag in {
        "high_spread_bad_fill", "gap_reversal",
    }:
        penalty += 0.009
    if strategy_family == "volatility_compression" and regime_tag in {
        "macro_shock_risk_off", "event_vol_expansion", "bullish_breakout", "bearish_breakdown",
    }:
        penalty += 0.010
    if strategy_family == "volatility_expansion" and regime_tag == "event_vol_expansion":
        penalty += 0.006
    if strategy_family == "volatility_expansion" and regime_tag in {
        "high_spread_bad_fill", "low_liquidity_decay",
    }:
        penalty += 0.007
    if short_duration_flag or structure_type == "butterfly":
        penalty += 0.004
    return penalty


def _slippage_verdict(expected_slippage_pct: float, fill_quality_score: float) -> str:
    if expected_slippage_pct >= 0.10 or fill_quality_score < 0.15:
        return "reject"
    if expected_slippage_pct <= 0.003 and fill_quality_score >= 0.85:
        return "excellent"
    if expected_slippage_pct <= 0.008 and fill_quality_score >= 0.72:
        return "good"
    if expected_slippage_pct <= 0.018 and fill_quality_score >= 0.55:
        return "acceptable"
    if expected_slippage_pct <= 0.040 and fill_quality_score >= 0.35:
        return "fragile"
    if expected_slippage_pct <= 0.080:
        return "poor"
    return "reject"


def build_slippage_input_from_leg(
    leg: dict[str, Any],
    liquidity_score: float,
    quote_stability_score: float,
    fill_context: dict[str, Any] | None,
) -> SlippageModelInput:
    context = fill_context or {}
    mid = float(leg.get("mid", 0.0))
    bid = float(leg.get("bid", mid))
    ask = float(leg.get("ask", mid))
    spread_width = max(0.0, ask - bid)
    spread_percentage = float(leg.get("spread_pct", 0.0))
    if spread_percentage <= 0.0 and mid > 0:
        spread_percentage = spread_width / mid
    regime_tag = str(context.get("regime_tag", leg.get("regime_tag", "")))
    strategy_family = str(context.get("strategy_family", leg.get("strategy_family", "")))
    structure_type = str(context.get("structure_type", leg.get("structure_type", "")))
    leg_count = int(context.get("leg_count", leg.get("leg_count", 1)))
    micro_ctx = context.get("microstructure_context", {})
    slippage_sensitivity = float(leg.get(
        "slippage_sensitivity_score",
        context.get(
            "slippage_sensitivity_score",
            _context_float(micro_ctx, "slippage_sensitivity_score", 0.2),
        ),
    ))
    anomaly = float(context.get(
        "volume_open_interest_anomaly_score",
        _context_float(micro_ctx, "volume_oi_anomaly_score", 0.0),
    ))
    volatility = float(context.get(
        "volatility_regime_score",
        _context_float(micro_ctx, "volatility_regime_score", 0.5),
    ))
    high_spread = bool(
        context.get("high_spread_flag", False)
        or leg.get("high_spread_flag", False)
        or spread_percentage >= 0.18
        or regime_tag == "high_spread_bad_fill"
    )
    low_liquidity = bool(
        context.get("low_liquidity_flag", False)
        or leg.get("low_liquidity_flag", False)
        or liquidity_score < 0.38
        or regime_tag in {"low_liquidity_decay", "liquidity_decay"}
    )
    event_vol = bool(context.get("event_vol_flag", regime_tag == "event_vol_expansion"))
    macro_shock = bool(context.get("macro_shock_flag", regime_tag == "macro_shock_risk_off"))
    short_duration = bool(
        context.get("short_duration_flag", False)
        or strategy_family == "short_duration_defined_risk"
        or context.get("dte_bucket", "") in {"0dte", "1dte", "short", "short_duration"}
    )
    return SlippageModelInput(
        mid=mid,
        spread_percentage=spread_percentage,
        liquidity_score=liquidity_score,
        regime_tag=regime_tag,
        strategy_family=strategy_family,
        structure_type=structure_type,
        leg_count=leg_count,
        volatility_regime_score=volatility,
        quote_stability_score=quote_stability_score,
        slippage_sensitivity_score=_clamp(slippage_sensitivity, 0.0, 1.0),
        volume_open_interest_anomaly_score=_clamp(anomaly, 0.0, 1.0),
        high_spread_flag=high_spread,
        low_liquidity_flag=low_liquidity,
        event_vol_flag=event_vol,
        macro_shock_flag=macro_shock,
        short_duration_flag=short_duration,
        side=str(leg.get("side", "buy")),
        microstructure_context=micro_ctx if isinstance(micro_ctx, dict) else {},
    )


def estimate_slippage(model_input: SlippageModelInput) -> SlippageModelResult:
    spread_component = _clamp(model_input.spread_percentage * 0.10, 0.0004, 0.045)
    liquidity_component = (1.0 - _clamp(model_input.liquidity_score, 0.0, 1.0)) * 0.012
    quote_component = (1.0 - _clamp(model_input.quote_stability_score, 0.0, 1.0)) * 0.009
    sensitivity_component = _clamp(model_input.slippage_sensitivity_score, 0.0, 1.0) * 0.009
    anomaly_component = _clamp(model_input.volume_open_interest_anomaly_score, 0.0, 1.0) * 0.004
    regime_component = _regime_slippage_penalty(model_input.regime_tag)
    structure_component = _structure_penalty(model_input.structure_type, model_input.leg_count)
    family_component = _family_regime_penalty(
        model_input.strategy_family,
        model_input.regime_tag,
        model_input.structure_type,
        model_input.short_duration_flag,
    )
    flag_component = 0.0
    if model_input.high_spread_flag:
        flag_component += 0.009
    if model_input.low_liquidity_flag:
        flag_component += 0.008
    if model_input.event_vol_flag:
        flag_component += 0.004
    if model_input.macro_shock_flag:
        flag_component += 0.006

    expected_pct = round(_clamp(
        spread_component
        + liquidity_component
        + quote_component
        + sensitivity_component
        + anomaly_component
        + regime_component
        + structure_component
        + family_component
        + flag_component,
        0.0004,
        0.1500,
    ), 6)
    amount = round(model_input.mid * expected_pct, 6)
    side_multiplier = -1.0 if model_input.side == "sell" else 1.0
    adjustment = round(side_multiplier * amount, 6)

    fill_quality = round(_clamp(
        1.0
        - expected_pct * 7.5
        - (1.0 - _clamp(model_input.liquidity_score, 0.0, 1.0)) * 0.22
        - (1.0 - _clamp(model_input.quote_stability_score, 0.0, 1.0)) * 0.16
        - (0.08 if model_input.high_spread_flag else 0.0)
        - (0.07 if model_input.low_liquidity_flag else 0.0),
        0.0,
        1.0,
    ), 6)
    worst_case_pct = round(_clamp(
        expected_pct
        + model_input.spread_percentage * 0.08
        + (1.0 - _clamp(model_input.liquidity_score, 0.0, 1.0)) * 0.015
        + (0.012 if model_input.high_spread_flag else 0.0),
        expected_pct,
        0.2000,
    ), 6)

    return SlippageModelResult(
        expected_slippage_pct=expected_pct,
        expected_slippage_amount=amount,
        worst_case_fixture_slippage_pct=worst_case_pct,
        fill_price_adjustment=adjustment,
        fill_quality_score=fill_quality,
        slippage_verdict=_slippage_verdict(expected_pct, fill_quality),
    )
