"""Deterministic IV surface, skew, and term-structure fixture models.

These models use only fixture option-chain fields and optional window regime context. They are
not real IV calibration, live pricing, or market-data integration.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .ontology import OptionChain, OptionContract


IV_FIXTURE_MODEL_VERSION = "dopey-iv-fixture-model-v1"


@dataclass(frozen=True)
class IVContext:
    iv_rank: float
    iv_percentile: float
    realized_volatility: float
    implied_vs_realized_gap: float
    iv_regime: str
    iv_event_risk: float
    iv_crush_risk: float
    iv_expansion_potential: float
    model_version: str = IV_FIXTURE_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IVSurfaceSummary:
    surface_shape: str
    atm_iv: float
    otm_call_iv: float
    otm_put_iv: float
    wings_elevated: bool
    surface_stability_score: float
    surface_opportunity_score: float
    model_version: str = IV_FIXTURE_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SkewSummary:
    put_skew_score: float
    call_skew_score: float
    skew_steepness: float
    skew_direction: str
    skew_opportunity_score: float
    skew_risk_score: float
    model_version: str = IV_FIXTURE_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TermStructureSummary:
    front_iv: float
    back_iv: float
    term_slope: float
    contango_backwardation_state: str
    event_bump_score: float
    term_opportunity_score: float
    term_risk_score: float
    model_version: str = IV_FIXTURE_MODEL_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _regime_iv_defaults(regime_tag: str) -> dict[str, float]:
    if regime_tag == "event_vol_expansion":
        return {"event": 0.85, "crush": 0.30, "expansion": 0.85}
    if regime_tag == "post_event_iv_crush":
        return {"event": 0.35, "crush": 0.90, "expansion": 0.15}
    if regime_tag == "macro_shock_risk_off":
        return {"event": 0.70, "crush": 0.25, "expansion": 0.75}
    if regime_tag == "chop_vol_compression":
        return {"event": 0.15, "crush": 0.65, "expansion": 0.20}
    if regime_tag == "range_bound_pin":
        return {"event": 0.10, "crush": 0.55, "expansion": 0.15}
    if regime_tag == "trend_vol_expansion":
        return {"event": 0.35, "crush": 0.20, "expansion": 0.65}
    return {"event": 0.20, "crush": 0.35, "expansion": 0.35}


def _option_ivs(chain: OptionChain) -> list[float]:
    return [float(c.iv) for c in chain.contracts if c.iv > 0.0]


def _spot(chain: OptionChain, underlying_snapshot: dict[str, Any] | None) -> float:
    if underlying_snapshot and "price" in underlying_snapshot:
        return float(underlying_snapshot["price"])
    return float(chain.underlying.price)


def _nearest_atm_contracts(chain: OptionChain, spot: float) -> list[OptionContract]:
    if not chain.contracts:
        return []
    distance = min(abs(c.strike - spot) for c in chain.contracts)
    return [c for c in chain.contracts if abs(c.strike - spot) == distance]


def build_iv_context(
    chain: OptionChain,
    regime_tag: str,
    underlying_snapshot: dict[str, Any] | None,
    regime_context: dict[str, Any] | None,
) -> IVContext:
    ivs = _option_ivs(chain)
    avg_iv = _mean(ivs)
    realized = float((underlying_snapshot or {}).get("realized_vol_20d", avg_iv))
    gap = round(avg_iv - realized, 6)
    iv_rank = round(_clamp((avg_iv - 0.10) / 0.25, 0.0, 1.0), 6)
    iv_percentile = round(_clamp((avg_iv - 0.08) / 0.30, 0.0, 1.0), 6)
    defaults = _regime_iv_defaults(regime_tag)
    context = regime_context or {}
    iv_effect = float(context.get("iv_effect", 0.0))
    event_risk = _clamp(float(context.get("iv_event_risk", defaults["event"])), 0.0, 1.0)
    crush_risk = _clamp(float(context.get("iv_crush_risk", defaults["crush"] + max(0.0, -iv_effect))), 0.0, 1.0)
    expansion = _clamp(
        float(context.get("iv_expansion_potential", defaults["expansion"] + max(0.0, iv_effect))),
        0.0,
        1.0,
    )
    if iv_rank >= 0.70:
        regime = "high"
    elif iv_rank <= 0.25:
        regime = "low"
    else:
        regime = "normal"
    if regime_tag == "event_vol_expansion":
        regime = "event_expansion"
    elif regime_tag == "post_event_iv_crush":
        regime = "post_event_crush"
    elif regime_tag == "macro_shock_risk_off":
        regime = "macro_shock"
    return IVContext(
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        realized_volatility=round(realized, 6),
        implied_vs_realized_gap=gap,
        iv_regime=regime,
        iv_event_risk=round(event_risk, 6),
        iv_crush_risk=round(crush_risk, 6),
        iv_expansion_potential=round(expansion, 6),
    )


def summarize_iv_surface(chain: OptionChain, underlying_snapshot: dict[str, Any] | None) -> IVSurfaceSummary:
    spot = _spot(chain, underlying_snapshot)
    atm = _mean([c.iv for c in _nearest_atm_contracts(chain, spot)])
    calls = [c.iv for c in chain.contracts if c.option_type == "call" and c.strike > spot]
    puts = [c.iv for c in chain.contracts if c.option_type == "put" and c.strike < spot]
    call_iv = _mean(calls)
    put_iv = _mean(puts)
    wing_avg = _mean(calls + puts)
    wings_elevated = bool(atm > 0.0 and wing_avg > atm + 0.015)
    skew_gap = put_iv - call_iv
    if wings_elevated:
        shape = "smile"
    elif skew_gap > 0.02:
        shape = "put_skewed"
    elif skew_gap < -0.02:
        shape = "call_skewed"
    else:
        shape = "flat"
    dispersion = max(_option_ivs(chain), default=0.0) - min(_option_ivs(chain), default=0.0)
    stability = round(_clamp(1.0 - dispersion * 4.0, 0.0, 1.0), 6)
    opportunity = round(_clamp(abs(skew_gap) * 6.0 + (0.18 if wings_elevated else 0.0), 0.0, 1.0), 6)
    return IVSurfaceSummary(
        surface_shape=shape,
        atm_iv=round(atm, 6),
        otm_call_iv=round(call_iv, 6),
        otm_put_iv=round(put_iv, 6),
        wings_elevated=wings_elevated,
        surface_stability_score=stability,
        surface_opportunity_score=opportunity,
    )


def summarize_skew(chain: OptionChain, underlying_snapshot: dict[str, Any] | None) -> SkewSummary:
    spot = _spot(chain, underlying_snapshot)
    otm_puts = [c.iv for c in chain.contracts if c.option_type == "put" and c.strike < spot]
    otm_calls = [c.iv for c in chain.contracts if c.option_type == "call" and c.strike > spot]
    put_iv = _mean(otm_puts)
    call_iv = _mean(otm_calls)
    steepness = round(abs(put_iv - call_iv), 6)
    if put_iv > call_iv + 0.01:
        direction = "put_skew"
    elif call_iv > put_iv + 0.01:
        direction = "call_skew"
    else:
        direction = "balanced"
    put_score = round(_clamp((put_iv - call_iv + 0.05) / 0.10, 0.0, 1.0), 6)
    call_score = round(_clamp((call_iv - put_iv + 0.05) / 0.10, 0.0, 1.0), 6)
    opportunity = round(_clamp(steepness * 8.0, 0.0, 1.0), 6)
    risk = round(_clamp(steepness * 10.0, 0.0, 1.0), 6)
    return SkewSummary(
        put_skew_score=put_score,
        call_skew_score=call_score,
        skew_steepness=steepness,
        skew_direction=direction,
        skew_opportunity_score=opportunity,
        skew_risk_score=risk,
    )


def summarize_term_structure(
    chain: OptionChain,
    underlying_snapshot: dict[str, Any] | None,
    regime_tag: str,
) -> TermStructureSummary:
    spot = _spot(chain, underlying_snapshot)
    by_expiry: dict[str, list[tuple[float, float]]] = {}
    for contract in chain.contracts:
        by_expiry.setdefault(contract.expiry, []).append((abs(contract.strike - spot), contract.iv))
    expiry_ivs: list[tuple[str, float]] = []
    for expiry, rows in by_expiry.items():
        rows.sort(key=lambda row: row[0])
        expiry_ivs.append((expiry, rows[0][1] if rows else 0.0))
    expiry_ivs.sort(key=lambda row: row[0])
    front = expiry_ivs[0][1] if expiry_ivs else 0.0
    back = expiry_ivs[-1][1] if expiry_ivs else front
    slope = round(back - front, 6)
    if slope > 0.01:
        state = "contango"
    elif slope < -0.01:
        state = "backwardation"
    else:
        state = "flat"
    event_bump = 0.0
    if regime_tag in {"event_vol_expansion", "macro_shock_risk_off"}:
        event_bump = 0.75
    elif state == "backwardation":
        event_bump = 0.55
    opportunity = round(_clamp((0.55 if state == "backwardation" else 0.25) + event_bump * 0.35, 0.0, 1.0), 6)
    risk = round(_clamp(abs(slope) * 8.0 + event_bump * 0.30, 0.0, 1.0), 6)
    return TermStructureSummary(
        front_iv=round(front, 6),
        back_iv=round(back, 6),
        term_slope=slope,
        contango_backwardation_state=state,
        event_bump_score=round(event_bump, 6),
        term_opportunity_score=opportunity,
        term_risk_score=risk,
    )


def build_iv_fixture_bundle(
    chain: OptionChain,
    regime_tag: str,
    underlying_snapshot: dict[str, Any] | None,
    regime_context: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        "iv_context": build_iv_context(chain, regime_tag, underlying_snapshot, regime_context),
        "surface": summarize_iv_surface(chain, underlying_snapshot),
        "skew": summarize_skew(chain, underlying_snapshot),
        "term": summarize_term_structure(chain, underlying_snapshot, regime_tag),
    }
