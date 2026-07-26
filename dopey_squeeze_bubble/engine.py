"""Pure scoring and decision functions for squeeze and bubble research."""

from __future__ import annotations

import math
from dataclasses import asdict
from statistics import fmean
from typing import Any, Final

from dopey.protocols.identity import canonical_hash

from .models import IntelligencePolicy, SymbolEvidence


SQUEEZE_PRESSURE_WEIGHTS: Final[dict[str, float]] = {
    "short_percent_float": 0.34,
    "days_to_cover": 0.16,
    "short_growth": 0.10,
    "float_scarcity": 0.08,
    "borrow_fee": 0.10,
    "borrow_utilization": 0.08,
    "fails_to_float": 0.07,
    "threshold_stress": 0.07,
}
SQUEEZE_IGNITION_WEIGHTS: Final[dict[str, float]] = {
    "return_5d": 0.14,
    "return_20d": 0.10,
    "breakout": 0.14,
    "volume_expansion": 0.12,
    "rsi_pressure": 0.07,
    "daily_short_flow": 0.05,
    "call_flow": 0.08,
    "negative_gamma": 0.08,
    "liquidity": 0.07,
    "observed_liquidity_stress": 0.15,
}
BUBBLE_FRAGILITY_WEIGHTS: Final[dict[str, float]] = {
    "extreme_pe": 0.14,
    "revenue_valuation_excess": 0.11,
    "ipo_reflexivity": 0.11,
    "cash_burn": 0.09,
    "balance_sheet_leverage": 0.07,
    "price_extension": 0.11,
    "price_acceleration": 0.07,
    "call_crowding": 0.05,
    "implied_volatility": 0.035,
    "market_margin_leverage": 0.075,
    "attention_liquidity_reflexivity": 0.04,
    "options_turnover": 0.045,
    "valuation_breadth": 0.055,
}
UNWIND_TRIGGER_WEIGHTS: Final[dict[str, float]] = {
    "return_5d_break": 0.18,
    "sma20_break": 0.18,
    "sma50_break": 0.10,
    "twenty_day_breakdown": 0.16,
    "volume_confirmation": 0.10,
    "put_flow": 0.09,
    "negative_gamma": 0.07,
    "observed_liquidity_air_pocket": 0.12,
}
LIQUIDITY_STRESS_WEIGHTS: Final[dict[str, float]] = {
    "float_turnover": 0.20,
    "borrow_availability_scarcity": 0.20,
    "persistent_short_flow": 0.20,
    "call_turnover": 0.15,
    "negative_gamma": 0.15,
    "signed_volume_pressure": 0.10,
}
LIQUIDITY_AIR_POCKET_WEIGHTS: Final[dict[str, float]] = {
    "put_turnover": 0.25,
    "negative_signed_volume_pressure": 0.20,
    "dollar_volume_acceleration": 0.20,
    "negative_gamma": 0.20,
    "put_flow": 0.15,
}


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _scale(value: float | None, lower: float, upper: float) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError(f"score input must be finite: value={value}")
    if upper <= lower:
        raise ValueError(
            f"score bounds must be increasing: lower={lower}, upper={upper}"
        )
    return _clamp((value - lower) / (upper - lower))


def _inverse_scale(value: float | None, lower: float, upper: float) -> float | None:
    scaled = _scale(value, lower, upper)
    return None if scaled is None else 1.0 - scaled


def _weighted_score(
    components: dict[str, float | None],
    weights: dict[str, float],
) -> tuple[float, float, tuple[str, ...]]:
    unknown = sorted(set(components) - set(weights))
    missing = tuple(sorted(key for key, value in components.items() if value is None))
    if unknown:
        raise ValueError(f"score contains unweighted components: components={unknown}")
    total_weight = sum(weights.values())
    available_weight = sum(
        weights[key] for key, value in components.items() if value is not None
    )
    score = sum(
        weights[key] * _clamp(float(value))
        for key, value in components.items()
        if value is not None
    )
    return (
        round(score / total_weight, 6),
        round(available_weight / total_weight, 6),
        missing,
    )


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _short_growth(evidence: SymbolEvidence) -> float | None:
    current = evidence.short_crowding.shares_short
    prior = evidence.short_crowding.shares_short_prior_month
    if current is None or prior is None or prior <= 0.0:
        return None
    return current / prior - 1.0


def _pressure_components(evidence: SymbolEvidence) -> dict[str, float | None]:
    short = evidence.short_crowding
    settlement = evidence.settlement
    threshold_stress: float | None
    if settlement.official_threshold_listed is True:
        threshold_stress = 1.0
    elif settlement.official_threshold_listed is False:
        threshold_stress = 0.0
    elif settlement.threshold_condition_proxy:
        threshold_stress = 0.65
    elif settlement.latest_fails is not None:
        threshold_stress = 0.0
    else:
        threshold_stress = None
    return {
        "short_percent_float": _scale(short.short_percent_float, 0.08, 0.35),
        "days_to_cover": _scale(short.days_to_cover, 2.0, 10.0),
        "short_growth": _scale(_short_growth(evidence), 0.0, 0.30),
        "float_scarcity": _inverse_scale(
            short.float_shares, 10_000_000.0, 150_000_000.0
        ),
        "borrow_fee": _scale(short.borrow_fee_percent, 3.0, 50.0),
        "borrow_utilization": _scale(short.borrow_utilization, 0.70, 0.98),
        "fails_to_float": _scale(settlement.fails_to_float, 0.0005, 0.01),
        "threshold_stress": threshold_stress,
    }


def _call_pressure(evidence: SymbolEvidence) -> float | None:
    ratio = evidence.options.put_call_volume_ratio
    if ratio is None:
        return None
    return _inverse_scale(ratio, 0.35, 1.25)


def _put_pressure(evidence: SymbolEvidence) -> float | None:
    return _scale(evidence.options.put_call_volume_ratio, 0.8, 2.0)


def _negative_gamma(evidence: SymbolEvidence) -> float | None:
    gex = evidence.options.total_gex_dollar_per_pct
    if gex is None:
        return None
    market_cap = evidence.fundamentals.market_cap
    normalizer = (
        max(market_cap * 0.00005, 1_000_000.0)
        if market_cap is not None and market_cap > 0.0
        else 10_000_000.0
    )
    return _scale(-gex / normalizer, 0.0, 2.0)


def _turnover(
    volume: float | None,
    open_interest: float | None,
) -> float | None:
    if volume is None or open_interest is None or open_interest <= 0.0:
        return None
    return volume / open_interest


def _persistent_short_flow(evidence: SymbolEvidence) -> float | None:
    short = evidence.short_crowding
    if short.daily_short_volume_observations < 3:
        return None
    elevated_fraction = (
        short.daily_short_volume_elevated_sessions
        / short.daily_short_volume_observations
    )
    dispersion = short.daily_short_volume_ratio_dispersion
    stability = (
        1.0 - float(_scale(dispersion, 0.03, 0.20) or 0.0)
        if dispersion is not None
        else 0.0
    )
    level = _scale(short.daily_short_volume_median_ratio, 0.40, 0.65)
    return _clamp(float(level or 0.0) * elevated_fraction * stability)


def _liquidity_stress_diagnostics(
    evidence: SymbolEvidence,
) -> tuple[float, float, tuple[str, ...], dict[str, float | None]]:
    short = evidence.short_crowding
    float_turnover = _ratio(short.average_volume, short.float_shares)
    availability_ratio = _ratio(
        short.borrow_available_shares,
        short.float_shares,
    )
    components = {
        "float_turnover": _scale(float_turnover, 0.01, 0.20),
        "borrow_availability_scarcity": (
            _inverse_scale(availability_ratio, 0.001, 0.10)
            if availability_ratio is not None
            else None
        ),
        "persistent_short_flow": _persistent_short_flow(evidence),
        "call_turnover": _scale(
            _turnover(
                evidence.options.call_volume,
                evidence.options.call_open_interest,
            ),
            0.05,
            0.75,
        ),
        "negative_gamma": _negative_gamma(evidence),
        "signed_volume_pressure": _scale(
            evidence.technical.signed_volume_pressure_20d,
            0.05,
            0.60,
        ),
    }
    score, completeness, missing = _weighted_score(
        components,
        LIQUIDITY_STRESS_WEIGHTS,
    )
    return score, completeness, missing, components


def _liquidity_air_pocket_diagnostics(
    evidence: SymbolEvidence,
) -> tuple[float, float, tuple[str, ...], dict[str, float | None]]:
    components = {
        "put_turnover": _scale(
            _turnover(
                evidence.options.put_volume,
                evidence.options.put_open_interest,
            ),
            0.05,
            0.75,
        ),
        "negative_signed_volume_pressure": _scale(
            -evidence.technical.signed_volume_pressure_20d,
            0.05,
            0.60,
        ),
        "dollar_volume_acceleration": _scale(
            evidence.technical.dollar_volume_ratio_5d_20d,
            1.0,
            2.5,
        ),
        "negative_gamma": _negative_gamma(evidence),
        "put_flow": _put_pressure(evidence),
    }
    score, completeness, missing = _weighted_score(
        components,
        LIQUIDITY_AIR_POCKET_WEIGHTS,
    )
    return score, completeness, missing, components


def _ignition_components(evidence: SymbolEvidence) -> dict[str, float | None]:
    technical = evidence.technical
    short_flow = evidence.short_crowding.daily_short_volume_ratio
    return {
        "return_5d": _scale(technical.return_5d, 0.01, 0.20),
        "return_20d": _scale(technical.return_20d, 0.03, 0.40),
        "breakout": 1.0 if technical.breakout_20d else 0.0,
        "volume_expansion": _scale(technical.volume_ratio_20d, 1.0, 3.0),
        "rsi_pressure": _scale(technical.rsi14, 55.0, 82.0),
        "daily_short_flow": _scale(short_flow, 0.45, 0.70),
        "call_flow": _call_pressure(evidence),
        "negative_gamma": _negative_gamma(evidence),
        "liquidity": _scale(
            technical.average_dollar_volume_20d,
            10_000_000.0,
            250_000_000.0,
        ),
        "observed_liquidity_stress": _liquidity_stress_diagnostics(evidence)[0],
    }


def _positive_scale(
    value: float | None,
    lower: float,
    upper: float,
) -> float | None:
    if value is None or value <= 0.0:
        return None
    return _scale(value, lower, upper)


def _extreme_pe(evidence: SymbolEvidence) -> float | None:
    fundamental = evidence.fundamentals
    components = (
        _positive_scale(fundamental.trailing_pe, 40.0, 200.0),
        _positive_scale(fundamental.forward_pe, 35.0, 125.0),
    )
    available = [value for value in components if value is not None]
    return max(available) if available else None


def _revenue_valuation_excess(evidence: SymbolEvidence) -> float | None:
    fundamental = evidence.fundamentals
    enterprise_to_revenue = _ratio(
        fundamental.enterprise_value,
        fundamental.total_revenue,
    )
    components = (
        _positive_scale(fundamental.price_to_sales, 5.0, 60.0),
        _positive_scale(enterprise_to_revenue, 5.0, 60.0),
        _positive_scale(fundamental.price_to_book, 5.0, 30.0),
    )
    available = [value for value in components if value is not None]
    return max(available) if available else None


def _valuation_breadth(evidence: SymbolEvidence) -> float | None:
    fundamental = evidence.fundamentals
    enterprise_to_revenue = _ratio(
        fundamental.enterprise_value,
        fundamental.total_revenue,
    )
    metrics = (
        _positive_scale(fundamental.trailing_pe, 40.0, 200.0),
        _positive_scale(fundamental.forward_pe, 35.0, 125.0),
        _positive_scale(fundamental.price_to_sales, 5.0, 60.0),
        _positive_scale(enterprise_to_revenue, 5.0, 60.0),
        _positive_scale(fundamental.price_to_book, 5.0, 30.0),
    )
    available = [value for value in metrics if value is not None]
    if len(available) < 2:
        return None
    return sum(available) / len(metrics)


def _ipo_reflexivity(evidence: SymbolEvidence) -> float | None:
    fundamental = evidence.fundamentals
    age_days = fundamental.days_since_first_trade
    if age_days is None or age_days > 730:
        return None
    recency = _inverse_scale(float(age_days), 90.0, 730.0)
    appreciation = (
        _scale(
            evidence.technical.close / fundamental.ipo_offer_price - 1.0,
            0.25,
            4.0,
        )
        if fundamental.ipo_offer_price is not None and fundamental.ipo_offer_price > 0.0
        else None
    )
    small_deal = _inverse_scale(
        fundamental.ipo_offer_amount,
        50_000_000.0,
        1_000_000_000.0,
    )
    return _clamp(
        0.50 * float(recency or 0.0)
        + 0.35 * float(appreciation or 0.0)
        + 0.15 * float(small_deal or 0.0)
    )


def _cash_burn(evidence: SymbolEvidence) -> float | None:
    fundamental = evidence.fundamentals
    market_cap = fundamental.market_cap
    if fundamental.free_cashflow is None or market_cap is None or market_cap <= 0.0:
        return None
    return _scale(-fundamental.free_cashflow / market_cap, 0.0, 0.12)


def _balance_sheet_leverage(evidence: SymbolEvidence) -> float | None:
    fundamental = evidence.fundamentals
    if fundamental.theme == "financials":
        return None
    market_cap = fundamental.market_cap
    debt = fundamental.total_debt
    cash = fundamental.total_cash
    if market_cap is None or market_cap <= 0.0 or debt is None:
        return None
    net_debt = debt - (cash or 0.0)
    return _scale(net_debt / market_cap, 0.10, 1.25)


def _market_margin_leverage(evidence: SymbolEvidence) -> float | None:
    leverage = evidence.market_leverage
    components = (
        _scale(leverage.debit_growth_3m, 0.03, 0.20),
        _scale(leverage.debit_growth_12m, 0.10, 0.50),
        _scale(leverage.debit_to_free_credit_ratio, 2.0, 4.5),
    )
    available = [value for value in components if value is not None]
    return sum(available) / len(available) if available else None


def _bubble_components(evidence: SymbolEvidence) -> dict[str, float | None]:
    technical = evidence.technical
    momentum_acceleration = (
        technical.return_20d - technical.return_63d / 3.0
        if technical.return_63d is not None
        else None
    )
    price_extensions = [
        value
        for value in (
            technical.distance_sma20,
            technical.distance_sma50,
            technical.distance_sma200,
        )
        if value is not None
    ]
    oi_call_crowding = (
        _inverse_scale(evidence.options.put_call_open_interest_ratio, 0.40, 1.20)
        if evidence.options.quote_derived
        else None
    )
    return {
        "extreme_pe": _extreme_pe(evidence),
        "revenue_valuation_excess": _revenue_valuation_excess(evidence),
        "ipo_reflexivity": _ipo_reflexivity(evidence),
        "cash_burn": _cash_burn(evidence),
        "balance_sheet_leverage": _balance_sheet_leverage(evidence),
        "price_extension": _scale(
            max(price_extensions) if price_extensions else None,
            0.10,
            0.75,
        ),
        "price_acceleration": _scale(momentum_acceleration, 0.03, 0.30),
        "call_crowding": oi_call_crowding,
        "implied_volatility": _scale(
            evidence.options.atm_implied_vol
            if evidence.options.quote_derived
            else None,
            0.35,
            1.10,
        ),
        "market_margin_leverage": _market_margin_leverage(evidence),
        "attention_liquidity_reflexivity": _scale(
            technical.volume_ratio_20d * max(technical.return_20d, 0.0),
            0.05,
            0.60,
        ),
        "options_turnover": _scale(
            max(
                (
                    value
                    for value in (
                        _turnover(
                            evidence.options.call_volume,
                            evidence.options.call_open_interest,
                        ),
                        _turnover(
                            evidence.options.put_volume,
                            evidence.options.put_open_interest,
                        ),
                    )
                    if value is not None
                ),
                default=None,
            ),
            0.05,
            0.75,
        ),
        "valuation_breadth": _valuation_breadth(evidence),
    }


def _unwind_components(evidence: SymbolEvidence) -> dict[str, float | None]:
    technical = evidence.technical
    return {
        "return_5d_break": _scale(-technical.return_5d, 0.01, 0.15),
        "sma20_break": _scale(-technical.distance_sma20, 0.0, 0.12),
        "sma50_break": (
            _scale(-technical.distance_sma50, 0.0, 0.18)
            if technical.distance_sma50 is not None
            else None
        ),
        "twenty_day_breakdown": 1.0 if technical.breakdown_20d else 0.0,
        "volume_confirmation": _scale(technical.volume_ratio_20d, 1.0, 3.0),
        "put_flow": _put_pressure(evidence),
        "negative_gamma": _negative_gamma(evidence),
        "observed_liquidity_air_pocket": (
            _liquidity_air_pocket_diagnostics(evidence)[0]
        ),
    }


def _squeeze_persistence(
    evidence: SymbolEvidence,
) -> tuple[float, float, tuple[str, ...], dict[str, float | None]]:
    short = evidence.short_crowding
    prior_short_percent = _ratio(
        short.shares_short_prior_month,
        short.float_shares,
    )
    current_short = _scale(short.short_percent_float, 0.08, 0.35)
    prior_short = _scale(prior_short_percent, 0.08, 0.35)
    short_interest_persistence = (
        min(current_short, prior_short)
        if current_short is not None and prior_short is not None
        else None
    )
    return_5d = _scale(evidence.technical.return_5d, 0.01, 0.20)
    return_20d = _scale(evidence.technical.return_20d, 0.03, 0.40)
    components = {
        "two_period_short_interest": short_interest_persistence,
        "multi_session_short_flow": _persistent_short_flow(evidence),
        "consecutive_settlement_stress": _scale(
            float(evidence.settlement.elevated_fail_sessions),
            2.0,
            5.0,
        ),
        "multi_horizon_price_ignition": (
            min(return_5d, return_20d)
            if return_5d is not None and return_20d is not None
            else None
        ),
    }
    weights = {
        "two_period_short_interest": 0.40,
        "multi_session_short_flow": 0.20,
        "consecutive_settlement_stress": 0.20,
        "multi_horizon_price_ignition": 0.20,
    }
    score, completeness, missing = _weighted_score(components, weights)
    return score, completeness, missing, components


def _bubble_persistence(
    evidence: SymbolEvidence,
) -> tuple[float, float, tuple[str, ...], dict[str, float | None]]:
    technical = evidence.technical
    extension_values = [
        value
        for value in (
            _scale(technical.distance_sma20, 0.10, 0.75),
            _scale(technical.distance_sma50, 0.10, 0.90),
            _scale(technical.distance_sma200, 0.20, 2.00),
        )
        if value is not None
    ]
    fundamental_stress = [
        value
        for value in (
            _cash_burn(evidence),
            _balance_sheet_leverage(evidence),
        )
        if value is not None
    ]
    components = {
        "valuation_breadth": _valuation_breadth(evidence),
        "multi_horizon_price_extension": (
            sum(extension_values) / len(extension_values)
            if len(extension_values) >= 2
            else None
        ),
        "multi_month_market_leverage": _market_margin_leverage(evidence),
        "persistent_fundamental_fragility": (
            sum(fundamental_stress) / len(fundamental_stress)
            if fundamental_stress
            else None
        ),
        "recent_listing_reflexivity": _ipo_reflexivity(evidence),
    }
    weights = {
        "valuation_breadth": 0.30,
        "multi_horizon_price_extension": 0.20,
        "multi_month_market_leverage": 0.20,
        "persistent_fundamental_fragility": 0.20,
        "recent_listing_reflexivity": 0.10,
    }
    score, completeness, missing = _weighted_score(components, weights)
    return score, completeness, missing, components


def _lane_quality(
    evidence: SymbolEvidence,
    lane: str,
    completeness: float,
    policy: IntelligencePolicy,
) -> dict[str, Any]:
    ages = dict(evidence.integrity.lane_age_days)
    counts = dict(evidence.integrity.lane_observation_counts)
    if lane == "squeeze":
        sources = {
            evidence.integrity.technical_source_id,
            *evidence.short_crowding.source_ids,
            *evidence.settlement.source_ids,
            *evidence.options.source_ids,
        }
        relevant_ages = (
            ("technical", policy.maximum_technical_age_days),
            ("short_crowding", policy.maximum_source_age_days),
            ("short_flow", policy.maximum_source_age_days),
            ("borrow", policy.maximum_source_age_days),
            ("fails_to_deliver", policy.maximum_source_age_days),
            ("options", policy.maximum_source_age_days),
        )
        observation_strength = fmean(
            (
                min(counts.get("short_crowding", 0) / 2.0, 1.0),
                min(counts.get("short_flow", 0) / 3.0, 1.0),
                min(counts.get("fails_to_deliver", 0) / 5.0, 1.0),
                min(counts.get("options", 0), 1),
            )
        )
        contradiction_flags = tuple(
            flag
            for flag in evidence.integrity.contradiction_flags
            if flag.startswith(("squeeze:", "shared:"))
        )
    else:
        sources = {
            evidence.integrity.technical_source_id,
            *evidence.fundamentals.source_ids,
            *evidence.options.source_ids,
            *evidence.market_leverage.source_ids,
        }
        relevant_ages = (
            ("technical", policy.maximum_technical_age_days),
            ("fundamentals", policy.maximum_source_age_days),
            ("options", policy.maximum_source_age_days),
            ("market_leverage", policy.maximum_source_age_days),
        )
        observation_strength = fmean(
            (
                min(counts.get("technical", 0) / 63.0, 1.0),
                min(counts.get("fundamentals", 0), 1),
                min(counts.get("options", 0), 1),
                min(counts.get("market_leverage", 0) / 4.0, 1.0),
            )
        )
        contradiction_flags = tuple(
            flag
            for flag in evidence.integrity.contradiction_flags
            if flag.startswith(("bubble:", "shared:"))
        )
    sources.discard("")
    freshness_values = []
    for lane_name, maximum_age in relevant_ages:
        age = ages.get(lane_name)
        freshness_values.append(
            _clamp(1.0 - age / maximum_age) if age is not None and age >= 0 else 0.0
        )
    freshness = fmean(freshness_values)
    source_diversity = _clamp(len(sources) / max(policy.minimum_independent_sources, 1))
    contradiction_penalty = min(len(contradiction_flags) * 0.35, 1.0)
    robustness = _clamp(
        0.45 * completeness
        + 0.20 * source_diversity
        + 0.20 * freshness
        + 0.15 * observation_strength
        - contradiction_penalty
    )
    return {
        "robustness_score": round(robustness, 6),
        "freshness_score": round(freshness, 6),
        "source_diversity_score": round(source_diversity, 6),
        "observation_strength_score": round(observation_strength, 6),
        "contradiction_penalty": round(contradiction_penalty, 6),
        "contradiction_flags": contradiction_flags,
        "independent_source_count": len(sources),
        "minimum_independent_sources": policy.minimum_independent_sources,
        "lane_age_days": dict(sorted(ages.items())),
        "lane_observation_counts": dict(sorted(counts.items())),
        "stale_lanes": evidence.integrity.stale_lanes,
        "future_dated_lanes": evidence.integrity.future_dated_lanes,
        "path_containment_verified": (evidence.integrity.path_containment_verified),
        "stale_or_future_evidence_consumed": False,
    }


def _measurement_geometry(evidence: SymbolEvidence) -> dict[str, Any]:
    entry = evidence.technical.close
    return {
        "entry_reference_price": round(entry, 4),
        "invalidation_price": None,
        "target_price": None,
        "expected_hold_trading_days": None,
        "reference_is_observed_close": True,
        "forecast_price_generated": False,
        "speculative_price_forecast_allowed": False,
        "same_session_round_trip_allowed": False,
        "limit_entry_required": False,
    }


def evaluate_symbol(
    evidence: SymbolEvidence,
    policy: IntelligencePolicy,
) -> dict[str, Any]:
    """Score independent squeeze and bubble paths without collapsing them."""

    if evidence.technical.average_dollar_volume_20d < 0.0:
        raise ValueError(
            "average dollar volume cannot be negative: "
            f"symbol={evidence.symbol}, value={evidence.technical.average_dollar_volume_20d}"
        )
    pressure, pressure_completeness, pressure_missing = _weighted_score(
        _pressure_components(evidence),
        SQUEEZE_PRESSURE_WEIGHTS,
    )
    ignition, ignition_completeness, ignition_missing = _weighted_score(
        _ignition_components(evidence),
        SQUEEZE_IGNITION_WEIGHTS,
    )
    squeeze_completeness = round(
        0.65 * pressure_completeness + 0.35 * ignition_completeness,
        6,
    )
    squeeze_score = round(
        math.sqrt(max(pressure * ignition, 0.0)) * squeeze_completeness,
        6,
    )
    (
        squeeze_persistence,
        squeeze_persistence_completeness,
        squeeze_persistence_missing,
        squeeze_persistence_components,
    ) = _squeeze_persistence(evidence)
    squeeze_quality = _lane_quality(
        evidence,
        "squeeze",
        squeeze_completeness,
        policy,
    )
    (
        liquidity_stress,
        liquidity_stress_completeness,
        liquidity_stress_missing,
        liquidity_stress_components,
    ) = _liquidity_stress_diagnostics(evidence)
    actual_short_interest_present = (
        evidence.short_crowding.short_percent_float is not None
        and evidence.short_crowding.shares_short is not None
    )
    liquid = (
        evidence.technical.average_dollar_volume_20d
        >= policy.minimum_average_dollar_volume
    )
    squeeze_gate_reasons: list[str] = []
    if not actual_short_interest_present:
        squeeze_gate_reasons.append("missing_actual_open_short_interest")
    if not liquid:
        squeeze_gate_reasons.append("average_dollar_volume_below_floor")
    if pressure < policy.minimum_squeeze_pressure:
        squeeze_gate_reasons.append("squeeze_pressure_below_threshold")
    if ignition < policy.minimum_squeeze_ignition:
        squeeze_gate_reasons.append("squeeze_ignition_below_threshold")
    if squeeze_completeness < policy.minimum_squeeze_completeness:
        squeeze_gate_reasons.append("squeeze_evidence_completeness_below_threshold")
    if squeeze_persistence < policy.minimum_squeeze_persistence:
        squeeze_gate_reasons.append("squeeze_persistence_below_threshold")
    if float(squeeze_quality["robustness_score"]) < policy.minimum_lane_robustness:
        squeeze_gate_reasons.append("squeeze_evidence_robustness_below_threshold")
    if (
        int(squeeze_quality["independent_source_count"])
        < policy.minimum_independent_sources
    ):
        squeeze_gate_reasons.append("insufficient_independent_squeeze_sources")
    if len(squeeze_quality["contradiction_flags"]) > policy.maximum_contradiction_count:
        squeeze_gate_reasons.append("contradictory_squeeze_evidence")
    if not evidence.integrity.path_containment_verified:
        squeeze_gate_reasons.append("evidence_path_containment_unverified")
    if evidence.integrity.stale_lanes:
        squeeze_gate_reasons.append("stale_evidence_detected_and_excluded")
    if evidence.integrity.future_dated_lanes:
        squeeze_gate_reasons.append("future_dated_evidence_detected_and_excluded")
    technical_age = dict(evidence.integrity.lane_age_days).get("technical")
    if technical_age is None or technical_age > policy.maximum_technical_age_days:
        squeeze_gate_reasons.append("technical_evidence_stale_or_missing")
    if (
        evidence.options.quote_derived
        and evidence.options.contract_rows < policy.minimum_options_contract_rows
    ):
        squeeze_gate_reasons.append("sparse_quote_derived_option_chain")
    squeeze_status = (
        "squeeze_candidate_requires_existing_execution_gates"
        if not squeeze_gate_reasons
        else "squeeze_watch_or_blocked"
    )

    bubble_components = _bubble_components(evidence)
    fragility, bubble_completeness, bubble_missing = _weighted_score(
        bubble_components,
        BUBBLE_FRAGILITY_WEIGHTS,
    )
    unwind, unwind_completeness, unwind_missing = _weighted_score(
        _unwind_components(evidence),
        UNWIND_TRIGGER_WEIGHTS,
    )
    bubble_score = round(
        fragility
        * (0.65 + 0.35 * unwind)
        * min(bubble_completeness, unwind_completeness),
        6,
    )
    bubble_effective_completeness = round(
        min(bubble_completeness, unwind_completeness),
        6,
    )
    (
        bubble_persistence,
        bubble_persistence_completeness,
        bubble_persistence_missing,
        bubble_persistence_components,
    ) = _bubble_persistence(evidence)
    bubble_quality = _lane_quality(
        evidence,
        "bubble",
        bubble_effective_completeness,
        policy,
    )
    (
        liquidity_air_pocket,
        liquidity_air_pocket_completeness,
        liquidity_air_pocket_missing,
        liquidity_air_pocket_components,
    ) = _liquidity_air_pocket_diagnostics(evidence)
    bubble_gate_reasons: list[str] = []
    if not liquid:
        bubble_gate_reasons.append("average_dollar_volume_below_floor")
    if fragility < policy.minimum_bubble_fragility:
        bubble_gate_reasons.append("bubble_fragility_below_threshold")
    if bubble_completeness < policy.minimum_bubble_completeness:
        bubble_gate_reasons.append("bubble_evidence_completeness_below_threshold")
    if bubble_persistence < policy.minimum_bubble_persistence:
        bubble_gate_reasons.append("bubble_persistence_below_threshold")
    if float(bubble_quality["robustness_score"]) < policy.minimum_lane_robustness:
        bubble_gate_reasons.append("bubble_evidence_robustness_below_threshold")
    if (
        int(bubble_quality["independent_source_count"])
        < policy.minimum_independent_sources
    ):
        bubble_gate_reasons.append("insufficient_independent_bubble_sources")
    if len(bubble_quality["contradiction_flags"]) > policy.maximum_contradiction_count:
        bubble_gate_reasons.append("contradictory_bubble_evidence")
    if not evidence.integrity.path_containment_verified:
        bubble_gate_reasons.append("evidence_path_containment_unverified")
    if evidence.integrity.stale_lanes:
        bubble_gate_reasons.append("stale_evidence_detected_and_excluded")
    if evidence.integrity.future_dated_lanes:
        bubble_gate_reasons.append("future_dated_evidence_detected_and_excluded")
    if technical_age is None or technical_age > policy.maximum_technical_age_days:
        bubble_gate_reasons.append("technical_evidence_stale_or_missing")
    if unwind < policy.minimum_unwind_trigger:
        bubble_gate_reasons.append("unwind_trigger_not_confirmed")
    if not evidence.options.quote_derived:
        bubble_gate_reasons.append("missing_current_quote_derived_option_chain")
    elif evidence.options.contract_rows < policy.minimum_options_contract_rows:
        bubble_gate_reasons.append("sparse_quote_derived_option_chain")
    if (
        bubble_components["extreme_pe"] is None
        and bubble_components["revenue_valuation_excess"] is None
        and bubble_components["ipo_reflexivity"] is None
    ):
        bubble_gate_reasons.append("missing_empirical_valuation_or_ipo_anchor")
    bubble_monitor_blockers = {
        "bubble_persistence_below_threshold",
        "bubble_evidence_robustness_below_threshold",
        "insufficient_independent_bubble_sources",
        "contradictory_bubble_evidence",
        "evidence_path_containment_unverified",
        "stale_evidence_detected_and_excluded",
        "future_dated_evidence_detected_and_excluded",
        "missing_empirical_valuation_or_ipo_anchor",
        "technical_evidence_stale_or_missing",
    }
    if not bubble_gate_reasons:
        bubble_status = (
            "bubble_unwind_candidate_requires_options_control_and_existing_gates"
        )
    elif (
        fragility >= policy.minimum_bubble_fragility
        and bubble_completeness >= policy.minimum_bubble_completeness
        and not bubble_monitor_blockers.intersection(bubble_gate_reasons)
    ):
        bubble_status = "bubble_fragility_monitor_wait_for_unwind"
    elif fragility >= policy.minimum_bubble_watch_fragility:
        bubble_status = "bubble_watch_or_blocked"
    else:
        bubble_status = "bubble_low_fragility"

    squeeze_lane = {
        "status": squeeze_status,
        "score": squeeze_score,
        "pressure_score": pressure,
        "ignition_score": ignition,
        "persistence_score": squeeze_persistence,
        "persistence_completeness": squeeze_persistence_completeness,
        "persistence_missing_components": squeeze_persistence_missing,
        "persistence_components": squeeze_persistence_components,
        "robustness": squeeze_quality,
        "observed_liquidity_stress": {
            "score": liquidity_stress,
            "evidence_completeness": liquidity_stress_completeness,
            "missing_components": liquidity_stress_missing,
            "components": liquidity_stress_components,
            "direct_hidden_liquidity_observed": False,
            "observed_proxy_only": True,
        },
        "evidence_completeness": squeeze_completeness,
        "missing_components": tuple(
            sorted(set(pressure_missing) | set(ignition_missing))
        ),
        "gate_reasons": tuple(squeeze_gate_reasons),
        "direction": "bullish",
        "preferred_expression": (
            "long_equity_existing_live_gate_review"
            if squeeze_status == "squeeze_candidate_requires_existing_execution_gates"
            else "monitor_or_paper_only"
        ),
        "daily_short_volume_is_short_interest": False,
        "empirical_observations_only": True,
        "speculative_forecasting_allowed": False,
        "geometry": _measurement_geometry(evidence),
    }
    bubble_lane = {
        "status": bubble_status,
        "score": bubble_score,
        "fragility_score": fragility,
        "unwind_trigger_score": unwind,
        "extreme_pe_score": bubble_components["extreme_pe"],
        "revenue_valuation_excess_score": bubble_components["revenue_valuation_excess"],
        "ipo_reflexivity_score": bubble_components["ipo_reflexivity"],
        "valuation_breadth_score": bubble_components["valuation_breadth"],
        "persistence_score": bubble_persistence,
        "persistence_completeness": bubble_persistence_completeness,
        "persistence_missing_components": bubble_persistence_missing,
        "persistence_components": bubble_persistence_components,
        "robustness": bubble_quality,
        "observed_liquidity_air_pocket": {
            "score": liquidity_air_pocket,
            "evidence_completeness": liquidity_air_pocket_completeness,
            "missing_components": liquidity_air_pocket_missing,
            "components": liquidity_air_pocket_components,
            "direct_hidden_liquidity_observed": False,
            "observed_proxy_only": True,
        },
        "valuation_snapshot": {
            "trailing_pe": evidence.fundamentals.trailing_pe,
            "forward_pe": evidence.fundamentals.forward_pe,
            "price_to_sales": evidence.fundamentals.price_to_sales,
            "price_to_book": evidence.fundamentals.price_to_book,
            "enterprise_value": evidence.fundamentals.enterprise_value,
            "total_revenue": evidence.fundamentals.total_revenue,
        },
        "ipo_snapshot": {
            "first_trade_date": evidence.fundamentals.first_trade_date,
            "days_since_first_trade": (evidence.fundamentals.days_since_first_trade),
            "offer_price": evidence.fundamentals.ipo_offer_price,
            "offer_amount": evidence.fundamentals.ipo_offer_amount,
            "status": evidence.fundamentals.ipo_status,
        },
        "evidence_completeness": bubble_effective_completeness,
        "missing_components": tuple(sorted(set(bubble_missing) | set(unwind_missing))),
        "gate_reasons": tuple(bubble_gate_reasons),
        "direction": "bearish",
        "preferred_expression": (
            "long_put_or_bear_put_debit_spread_options_control_required"
            if bubble_status
            == "bubble_unwind_candidate_requires_options_control_and_existing_gates"
            else "avoid_monitor_or_paper_only"
        ),
        "naked_short_or_undefined_loss_allowed": False,
        "empirical_observations_only": True,
        "speculative_forecasting_allowed": False,
        "geometry": _measurement_geometry(evidence),
    }
    body: dict[str, Any] = {
        "artifact_type": "squeeze_bubble_symbol_assessment",
        "engine_version": "dopey-squeeze-bubble-intelligence-v2",
        "symbol": evidence.symbol,
        "as_of_date": evidence.technical.as_of_date,
        "squeeze": squeeze_lane,
        "bubble": bubble_lane,
        "evidence": asdict(evidence),
        "source_ids": tuple(
            sorted(
                {
                    *evidence.short_crowding.source_ids,
                    *evidence.settlement.source_ids,
                    *evidence.fundamentals.source_ids,
                    *evidence.options.source_ids,
                    *evidence.market_leverage.source_ids,
                    evidence.integrity.technical_source_id,
                }
            )
        ),
        "is_probability": False,
        "is_profit_claim": False,
        "empirical_observations_only": True,
        "speculative_forecasting_allowed": False,
        "direct_hidden_liquidity_claimed": False,
        "research_maturity_gate_bypassed": False,
        "order_construction_allowed": False,
        "paper_twin_required_for_any_live_review": True,
        "same_session_round_trip_allowed": False,
    }
    return {
        **body,
        "assessment_id": f"squeeze-bubble:{canonical_hash(body)[:24]}",
    }


def rank_candidates(
    assessments: tuple[dict[str, Any], ...],
) -> dict[str, tuple[str, ...]]:
    """Return deterministic IDs for candidate, monitor, and blocked queues."""

    squeeze = sorted(
        assessments,
        key=lambda item: (
            -float(item["squeeze"]["score"]),
            str(item["symbol"]),
        ),
    )
    bubble = sorted(
        assessments,
        key=lambda item: (
            -float(item["bubble"]["score"]),
            str(item["symbol"]),
        ),
    )
    return {
        "squeeze_candidates": tuple(
            str(item["assessment_id"])
            for item in squeeze
            if item["squeeze"]["status"]
            == "squeeze_candidate_requires_existing_execution_gates"
        ),
        "squeeze_watch": tuple(
            str(item["assessment_id"])
            for item in squeeze
            if item["squeeze"]["status"]
            != "squeeze_candidate_requires_existing_execution_gates"
            and float(item["squeeze"]["score"]) > 0.0
        ),
        "bubble_unwind_candidates": tuple(
            str(item["assessment_id"])
            for item in bubble
            if item["bubble"]["status"]
            == "bubble_unwind_candidate_requires_options_control_and_existing_gates"
        ),
        "bubble_fragility_monitors": tuple(
            str(item["assessment_id"])
            for item in bubble
            if item["bubble"]["status"] == "bubble_fragility_monitor_wait_for_unwind"
        ),
        "bubble_watch": tuple(
            str(item["assessment_id"])
            for item in bubble
            if item["bubble"]["status"] == "bubble_watch_or_blocked"
            and float(item["bubble"]["score"]) > 0.0
        ),
    }
