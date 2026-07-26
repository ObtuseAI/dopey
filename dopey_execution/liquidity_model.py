"""Deterministic DOPEY fixture liquidity model.

This model scores fixture option contracts and paper structures from only local,
deterministic fields. It is not market data, market impact, or queue modeling.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dopey_options.ontology import OptionContract


LIQUIDITY_MODEL_VERSION = "dopey-liquidity-model-v1"
REJECT_SPREAD_PERCENTAGE = 0.75
REJECT_FILLABILITY_SCORE = 0.15


@dataclass(frozen=True)
class LiquidityModelInput:
    bid: float
    ask: float
    mid: float
    spread_width: float
    spread_percentage: float
    volume: int
    open_interest: int
    regime_tag: str = ""
    microstructure_context: dict[str, Any] = field(default_factory=dict)
    quote_stability_score: float = 0.5
    contract_fillability_score: float = 0.5
    liquidity_decay_score: float = 0.0
    strategy_family: str = ""
    structure_type: str = ""
    dte_bucket: str = ""
    leg_count: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LiquidityModelResult:
    liquidity_score: float
    spread_quality_score: float
    depth_proxy_score: float
    quote_stability_score: float
    fillability_score: float
    liquidity_penalty: float
    liquidity_verdict: str
    model_version: str = LIQUIDITY_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _context_score(context: dict[str, Any], keys: tuple[str, ...], fallback: float) -> float:
    for key in keys:
        if key in context:
            return _clamp(_as_float(context.get(key), fallback), 0.0, 1.0)
    return _clamp(fallback, 0.0, 1.0)


def _spread_quality(spread_percentage: float) -> float:
    spread = max(0.0, spread_percentage)
    if spread <= 0.02:
        score = 1.0 - spread * 5.0
    elif spread <= 0.08:
        score = 0.90 - ((spread - 0.02) / 0.06) * 0.25
    elif spread <= 0.20:
        score = 0.65 - ((spread - 0.08) / 0.12) * 0.35
    elif spread <= 0.50:
        score = 0.30 - ((spread - 0.20) / 0.30) * 0.25
    else:
        score = max(0.0, 0.05 - (spread - 0.50) * 0.10)
    return round(_clamp(score, 0.0, 1.0), 6)


def _depth_proxy(volume: int, open_interest: int) -> float:
    volume_score = _clamp(float(max(volume, 0)) / 10000.0, 0.0, 1.0)
    oi_score = _clamp(float(max(open_interest, 0)) / 30000.0, 0.0, 1.0)
    return round(0.45 * volume_score + 0.55 * oi_score, 6)


def _regime_penalty(regime_tag: str) -> float:
    penalties = {
        "high_spread_bad_fill": 0.16,
        "low_liquidity_decay": 0.18,
        "liquidity_decay": 0.11,
        "macro_shock_risk_off": 0.08,
        "event_vol_expansion": 0.05,
        "gap_reversal": 0.04,
    }
    return penalties.get(regime_tag, 0.0)


def _dte_penalty(dte_bucket: str, liquidity_score: float) -> float:
    if dte_bucket in {"0dte", "1dte", "short", "short_duration"} and liquidity_score < 0.55:
        return 0.06
    return 0.0


def _strategy_structure_penalty(strategy_family: str, structure_type: str, regime_tag: str) -> float:
    penalty = 0.0
    if strategy_family == "short_duration_defined_risk" and regime_tag in {
        "high_spread_bad_fill", "low_liquidity_decay", "gap_reversal",
    }:
        penalty += 0.06
    if strategy_family == "volatility_compression" and regime_tag in {
        "event_vol_expansion", "macro_shock_risk_off", "bullish_breakout", "bearish_breakdown",
    }:
        penalty += 0.04
    if strategy_family == "directional_convexity" and regime_tag in {
        "high_spread_bad_fill", "gap_reversal",
    }:
        penalty += 0.04
    if structure_type in {"strangle", "iron_condor", "butterfly"}:
        penalty += 0.02
    return penalty


def _verdict(score: float, spread_percentage: float, fillability_score: float) -> str:
    if spread_percentage >= REJECT_SPREAD_PERCENTAGE or fillability_score < REJECT_FILLABILITY_SCORE:
        return "reject"
    if score >= 0.85:
        return "excellent"
    if score >= 0.70:
        return "good"
    if score >= 0.55:
        return "acceptable"
    if score >= 0.38:
        return "fragile"
    if score >= 0.20:
        return "poor"
    return "reject"


def build_liquidity_input_from_contract(
    contract: "OptionContract",
    regime_tag: str,
    microstructure_context: dict[str, Any] | None,
    strategy_family: str,
    structure_type: str,
    dte_bucket: str,
    leg_count: int,
) -> LiquidityModelInput:
    context = microstructure_context or {}
    mid = contract.mid()
    spread_width = max(0.0, contract.ask - contract.bid)
    spread_percentage = spread_width / mid if mid > 0 else 1.0
    quote_stability = _context_score(
        context,
        ("quote_stability_score", "quote_stability"),
        1.0 - _context_score(context, ("spread_penalty",), 0.35),
    )
    fillability = _context_score(
        context,
        ("contract_fillability_score", "fillability_score", "liquidity_quality", "liquidity_score"),
        0.5,
    )
    decay = _context_score(
        context,
        ("liquidity_decay_score", "liquidity_decay"),
        0.65 if regime_tag in {"liquidity_decay", "low_liquidity_decay"} else 0.0,
    )
    return LiquidityModelInput(
        bid=contract.bid,
        ask=contract.ask,
        mid=mid,
        spread_width=spread_width,
        spread_percentage=spread_percentage,
        volume=contract.volume,
        open_interest=contract.open_interest,
        regime_tag=regime_tag,
        microstructure_context=context,
        quote_stability_score=quote_stability,
        contract_fillability_score=fillability,
        liquidity_decay_score=decay,
        strategy_family=strategy_family,
        structure_type=structure_type,
        dte_bucket=dte_bucket,
        leg_count=leg_count,
    )


def evaluate_liquidity(model_input: LiquidityModelInput) -> LiquidityModelResult:
    if model_input.bid <= 0 or model_input.ask <= 0 or model_input.ask <= model_input.bid:
        return LiquidityModelResult(
            liquidity_score=0.0,
            spread_quality_score=0.0,
            depth_proxy_score=0.0,
            quote_stability_score=0.0,
            fillability_score=0.0,
            liquidity_penalty=1.0,
            liquidity_verdict="reject",
        )

    spread_quality = _spread_quality(model_input.spread_percentage)
    depth = _depth_proxy(model_input.volume, model_input.open_interest)
    quote_stability = _clamp(model_input.quote_stability_score, 0.0, 1.0)
    fillability = _clamp(model_input.contract_fillability_score, 0.0, 1.0)

    base_score = (
        0.34 * spread_quality
        + 0.28 * depth
        + 0.19 * quote_stability
        + 0.19 * fillability
    )
    leg_penalty = max(0, model_input.leg_count - 1) * 0.025
    decay_penalty = _clamp(model_input.liquidity_decay_score, 0.0, 1.0) * 0.15
    regime_penalty = _regime_penalty(model_input.regime_tag)
    strategy_penalty = _strategy_structure_penalty(
        model_input.strategy_family,
        model_input.structure_type,
        model_input.regime_tag,
    )
    dte_penalty = _dte_penalty(model_input.dte_bucket, base_score)

    penalty = round(_clamp(
        leg_penalty + decay_penalty + regime_penalty + strategy_penalty + dte_penalty,
        0.0,
        1.0,
    ), 6)
    score = round(_clamp(base_score - penalty, 0.0, 1.0), 6)
    verdict = _verdict(score, model_input.spread_percentage, fillability)

    return LiquidityModelResult(
        liquidity_score=score,
        spread_quality_score=round(spread_quality, 6),
        depth_proxy_score=round(depth, 6),
        quote_stability_score=round(quote_stability, 6),
        fillability_score=round(fillability, 6),
        liquidity_penalty=round(1.0 - score, 6),
        liquidity_verdict=verdict,
    )


def score_contract_liquidity(
    contract: "OptionContract",
    regime_tag: str,
    microstructure_context: dict[str, Any] | None,
    strategy_family: str,
    structure_type: str,
    dte_bucket: str,
    leg_count: int,
) -> LiquidityModelResult:
    model_input = build_liquidity_input_from_contract(
        contract,
        regime_tag,
        microstructure_context,
        strategy_family,
        structure_type,
        dte_bucket,
        leg_count,
    )
    return evaluate_liquidity(model_input)
