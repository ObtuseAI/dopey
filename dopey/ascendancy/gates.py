"""Conjunctive Greek, tail, concentration, drawdown, and behavioral gates."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class GateDecision:
    passed: bool
    reason_codes: tuple[str, ...]
    automatic_effect: str


@dataclass(frozen=True, slots=True)
class CandidateExposure:
    defined_risk: bool
    days_to_expiration: int
    maximum_loss_fraction: float
    margin_fraction: float
    expected_shortfall_fraction: float
    ruin_probability: float
    delta: float
    gamma: float
    theta: float
    vega: float
    vanna: float
    charm: float
    vomma: float
    skew: float
    correlation: float
    event: float
    liquidity: float
    gap: float


@dataclass(frozen=True, slots=True)
class PortfolioState:
    daily_loss_fraction: float
    drawdown_fraction: float
    delta: float
    gamma: float
    theta: float
    vega: float
    vanna: float
    charm: float
    vomma: float
    skew: float
    correlation: float
    event: float
    liquidity: float
    gap: float


@dataclass(frozen=True, slots=True)
class RiskLimits:
    maximum_position_loss_fraction: float
    maximum_margin_fraction: float
    maximum_expected_shortfall_fraction: float
    maximum_ruin_probability: float
    maximum_daily_loss_fraction: float
    maximum_drawdown_fraction: float
    maximum_absolute_delta: float
    maximum_absolute_gamma: float
    maximum_absolute_theta: float
    maximum_absolute_vega: float
    maximum_absolute_vanna: float
    maximum_absolute_charm: float
    maximum_absolute_vomma: float
    maximum_absolute_skew: float
    maximum_absolute_correlation: float
    maximum_absolute_event: float
    maximum_absolute_liquidity: float
    maximum_absolute_gap: float
    zero_dte_authorized_for_dedicated_research: bool


@dataclass(frozen=True, slots=True)
class BehavioralState:
    size_after_loss_ratio: float
    frequency_after_loss_ratio: float
    abstention_overrides: int
    fomo_entry: bool
    loss_limit_changed: bool
    invalidated_position_held: bool
    cooldown_active: bool


def _exceeds_absolute(total: float, limit: float) -> bool:
    return abs(total) > limit


def evaluate_risk_gate(
    candidate: CandidateExposure,
    portfolio: PortfolioState,
    limits: RiskLimits,
) -> GateDecision:
    reasons: list[str] = []
    if not isinstance(candidate.days_to_expiration, int) or isinstance(candidate.days_to_expiration, bool):
        reasons.append("days_to_expiration_invalid")
    candidate_values = tuple(
        float(getattr(candidate, field))
        for field in (
            "maximum_loss_fraction", "margin_fraction", "expected_shortfall_fraction",
            "ruin_probability", "delta", "gamma", "theta", "vega", "vanna", "charm",
            "vomma", "skew", "correlation", "event", "liquidity", "gap",
        )
    )
    portfolio_values = tuple(
        float(getattr(portfolio, field))
        for field in (
            "daily_loss_fraction", "drawdown_fraction", "delta", "gamma", "theta", "vega",
            "vanna", "charm", "vomma", "skew", "correlation", "event", "liquidity", "gap",
        )
    )
    limit_values = tuple(
        float(getattr(limits, field.name))
        for field in fields(limits)
        if field.name != "zero_dte_authorized_for_dedicated_research"
    )
    if not all(math.isfinite(value) for value in candidate_values):
        reasons.append("candidate_exposure_uncomputable")
    if not all(math.isfinite(value) for value in portfolio_values):
        reasons.append("portfolio_exposure_uncomputable")
    if not all(math.isfinite(value) and value >= 0.0 for value in limit_values):
        raise ValueError("risk limits must be finite and nonnegative")
    if any(
        value < 0.0
        for value in (
            candidate.maximum_loss_fraction,
            candidate.margin_fraction,
            candidate.expected_shortfall_fraction,
            candidate.ruin_probability,
        )
    ):
        reasons.append("candidate_risk_scalar_invalid")
    if any(
        value > 1.0
        for value in (
            candidate.maximum_loss_fraction,
            candidate.margin_fraction,
            candidate.expected_shortfall_fraction,
            candidate.ruin_probability,
        )
        if math.isfinite(value)
    ):
        reasons.append("candidate_risk_fraction_above_one")
    if portfolio.daily_loss_fraction < 0.0 or portfolio.drawdown_fraction < 0.0:
        reasons.append("portfolio_loss_state_invalid")
    if not candidate.defined_risk:
        reasons.append("undefined_risk_prohibited")
    if candidate.days_to_expiration < 0:
        reasons.append("expired_contract")
    if candidate.days_to_expiration == 0 and not limits.zero_dte_authorized_for_dedicated_research:
        reasons.append("zero_dte_requires_dedicated_intraday_evidence")
    scalar_checks = (
        (candidate.maximum_loss_fraction > limits.maximum_position_loss_fraction, "position_loss_limit"),
        (candidate.margin_fraction > limits.maximum_margin_fraction, "margin_limit"),
        (candidate.expected_shortfall_fraction > limits.maximum_expected_shortfall_fraction, "expected_shortfall_limit"),
        (candidate.ruin_probability > limits.maximum_ruin_probability, "ruin_probability_limit"),
        (portfolio.daily_loss_fraction >= limits.maximum_daily_loss_fraction, "daily_loss_circuit_breaker"),
        (portfolio.drawdown_fraction >= limits.maximum_drawdown_fraction, "drawdown_circuit_breaker"),
    )
    reasons.extend(reason for exceeded, reason in scalar_checks if exceeded)
    greek_checks = (
        (portfolio.delta + candidate.delta, limits.maximum_absolute_delta, "delta_limit"),
        (portfolio.gamma + candidate.gamma, limits.maximum_absolute_gamma, "gamma_limit"),
        (portfolio.theta + candidate.theta, limits.maximum_absolute_theta, "theta_limit"),
        (portfolio.vega + candidate.vega, limits.maximum_absolute_vega, "vega_limit"),
        (portfolio.vanna + candidate.vanna, limits.maximum_absolute_vanna, "vanna_limit"),
        (portfolio.charm + candidate.charm, limits.maximum_absolute_charm, "charm_limit"),
        (portfolio.vomma + candidate.vomma, limits.maximum_absolute_vomma, "vomma_limit"),
        (portfolio.skew + candidate.skew, limits.maximum_absolute_skew, "skew_limit"),
        (portfolio.correlation + candidate.correlation, limits.maximum_absolute_correlation, "correlation_limit"),
        (portfolio.event + candidate.event, limits.maximum_absolute_event, "event_limit"),
        (portfolio.liquidity + candidate.liquidity, limits.maximum_absolute_liquidity, "liquidity_limit"),
        (portfolio.gap + candidate.gap, limits.maximum_absolute_gap, "gap_limit"),
    )
    reasons.extend(reason for total, limit, reason in greek_checks if _exceeds_absolute(total, limit))
    return GateDecision(
        passed=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
        automatic_effect="paper_research_continue" if not reasons else "abstain_and_review",
    )


def evaluate_behavioral_gate(state: BehavioralState) -> GateDecision:
    reasons: list[str] = []
    if not math.isfinite(state.size_after_loss_ratio) or not math.isfinite(state.frequency_after_loss_ratio):
        reasons.append("behavioral_measurement_uncomputable")
    if state.size_after_loss_ratio < 0.0 or state.frequency_after_loss_ratio < 0.0:
        reasons.append("behavioral_measurement_negative")
    if not isinstance(state.abstention_overrides, int) or isinstance(state.abstention_overrides, bool) or state.abstention_overrides < 0:
        reasons.append("abstention_override_count_invalid")
    if state.size_after_loss_ratio > 1.0:
        reasons.append("post_loss_size_escalation")
    if state.frequency_after_loss_ratio > 1.0:
        reasons.append("post_loss_frequency_escalation")
    if state.abstention_overrides > 0:
        reasons.append("abstention_override_detected")
    if state.fomo_entry:
        reasons.append("fomo_entry_detected")
    if state.loss_limit_changed:
        reasons.append("loss_limit_rule_drift")
    if state.invalidated_position_held:
        reasons.append("invalidation_ignored")
    if state.cooldown_active:
        reasons.append("cooldown_active")
    return GateDecision(
        passed=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
        automatic_effect="paper_research_continue" if not reasons else "forced_cooldown_and_review",
    )
