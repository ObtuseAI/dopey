"""Active long-premium equity-options policy kernel for DOPEY.

The kernel converts the active trading canon into deterministic, offline,
paper-only checks. It does not place orders, fetch market data, connect to a
broker, weaken live gates, or claim performance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ACTIVE_TRADING_POLICY_VERSION = "dopey-active-long-premium-options-policy-v1"

ALLOWED_UNDERLYING_TYPES: frozenset[str] = frozenset({"equity", "etf"})

ALLOWED_STRATEGY_SLEEVES: frozenset[str] = frozenset({
    "directional_continuation_rotation",
    "volatility_surface_relative_value",
    "event_convexity",
    "flow_fundamental_asymmetry",
})

LONG_PREMIUM_STRUCTURE_TYPES: frozenset[str] = frozenset({
    "long_call",
    "long_put",
    "long_straddle",
    "long_strangle",
    "vertical",
    "debit_vertical",
    "call_debit_spread",
    "put_debit_spread",
    "long_call_butterfly",
    "long_put_butterfly",
    "long_iron_condor",
    "long_iron_butterfly",
})

FORBIDDEN_STRUCTURE_TYPES: frozenset[str] = frozenset({
    "naked_call",
    "naked_put",
    "naked_short_call",
    "naked_short_put",
    "short_straddle",
    "short_strangle",
    "short_call_vertical",
    "short_put_vertical",
    "call_credit_spread",
    "put_credit_spread",
    "short_iron_condor",
    "short_iron_butterfly",
    "undefined_risk_short_vol",
})

ALLOWED_0DTE_LIFECYCLE_STATES: frozenset[str] = frozenset({
    "hold_to_expiration_worthless_tolerant",
    "exercise_capable",
    "forced_broker_liquidation_tolerant",
})

ALLOWED_SWING_LIFECYCLE_STATES: frozenset[str] = frozenset({
    "swing_hold",
    "planned_exit",
    "planned_roll",
})

ALLOWED_ORDER_ACTIONS: frozenset[str] = frozenset({"open", "close", "roll"})
ALLOWED_OPEN_ORDER_TYPES: frozenset[str] = frozenset({"limit"})
ALLOWED_CLOSE_ORDER_TYPES: frozenset[str] = frozenset({"limit", "stop_limit"})
EMERGENCY_CLOSE_ORDER_TYPES: frozenset[str] = frozenset({"market", "stop_market"})

ADAPTIVE_RECURSIVE_LAYERS: frozenset[str] = frozenset({
    "signal_ranking",
    "regime_weighting",
    "execution_threshold",
    "ensemble_allocation",
    "surface_model_calibration",
})

HARD_SAFETY_RULES: tuple[str, ...] = (
    "paper_only_until_explicit_future_live_enablement",
    "no_uncovered_or_undefined_risk_options",
    "long_premium_or_net_debit_only",
    "limit_orders_for_opening_trades",
    "no_default_same_day_round_trip_churn",
    "0dte_requires_declared_lifecycle_state",
    "recursive_improvement_cannot_weaken_safety_layer",
)


@dataclass(frozen=True)
class ActiveTradingThresholds:
    min_forecast_move_score: float
    min_convexity_value_score: float
    min_surface_quality_score: float
    min_liquidity_score: float
    min_confirmation_score: float
    min_confirmation_count: int
    max_bid_ask_spread_pct: float
    max_0dte_bid_ask_spread_pct: float
    min_open_interest: int
    min_volume: int
    max_default_position_fraction: float
    max_0dte_position_fraction: float
    max_forced_liquidation_fraction: float
    drawdown_throttle_score: float
    failure_cluster_throttle_score: float
    min_recursive_oos_score: float
    min_recursive_cpcv_score: float
    min_recursive_deflated_sharpe: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ActiveTradingCandidate:
    candidate_id: str
    underlying_symbol: str
    underlying_type: str
    strategy_sleeve: str
    structure_type: str
    option_type: str
    order_action: str
    order_type: str
    position_intent: str
    dte: int
    same_day_round_trip: bool
    lifecycle_state: str
    net_debit: bool
    defined_risk: bool
    uncovered_short_option: bool
    spread_pct: float
    open_interest: int
    volume: int
    liquidity_score: float
    forecast_move_score: float
    convexity_value_score: float
    surface_quality_score: float
    catalyst_score: float
    flow_score: float
    fundamental_score: float
    technical_score: float
    drawdown_pressure_score: float
    failure_cluster_score: float
    requested_position_fraction: float
    can_accept_exercise: bool
    can_accept_short_stock_from_put_exercise: bool
    forced_broker_liquidation_tolerant: bool
    live_allowed: bool
    paper_only: bool
    source_freshness: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyImprovementProposal:
    proposal_id: str
    layer: str
    changes: dict[str, object]
    oos_score: float
    cpcv_score: float
    deflated_sharpe_ratio: float
    multiple_testing_penalty: float
    weakens_safety_layer: bool
    touches_hard_rules: bool
    live_enablement_requested: bool
    paper_only: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDecision:
    subject_id: str
    allowed: bool
    verdict: str
    reasons: list[str]
    warnings: list[str]
    max_position_fraction: float
    policy_version: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_active_trading_thresholds() -> ActiveTradingThresholds:
    return ActiveTradingThresholds(
        min_forecast_move_score=0.62,
        min_convexity_value_score=0.62,
        min_surface_quality_score=0.55,
        min_liquidity_score=0.60,
        min_confirmation_score=0.60,
        min_confirmation_count=3,
        max_bid_ask_spread_pct=0.10,
        max_0dte_bid_ask_spread_pct=0.04,
        min_open_interest=1_000,
        min_volume=500,
        max_default_position_fraction=0.05,
        max_0dte_position_fraction=0.005,
        max_forced_liquidation_fraction=0.001,
        drawdown_throttle_score=0.65,
        failure_cluster_throttle_score=0.65,
        min_recursive_oos_score=0.60,
        min_recursive_cpcv_score=0.58,
        min_recursive_deflated_sharpe=0.30,
    )


def active_trading_canon_record() -> dict[str, object]:
    return {
        "policy_version": ACTIVE_TRADING_POLICY_VERSION,
        "product": "long-premium equity and ETF options",
        "objective": "maximize expected geometric growth under hard ruin controls",
        "default_posture": "swing-first, selective, liquid underliers only",
        "0dte_posture": "special catalyst sleeve with declared lifecycle state",
        "alpha_posture": "forecast move and convexity price must both be favorable",
        "execution_posture": "limit orders by default; market orders only for emergency sell-to-close",
        "risk_posture": "throttle size when volatility, spread, drawdown, or failures cluster",
        "learning_posture": "adapt alpha weights and thresholds; never weaken safety rules",
        "strategy_sleeves": sorted(ALLOWED_STRATEGY_SLEEVES),
        "allowed_structures": sorted(LONG_PREMIUM_STRUCTURE_TYPES),
        "forbidden_structures": sorted(FORBIDDEN_STRUCTURE_TYPES),
        "hard_safety_rules": list(HARD_SAFETY_RULES),
    }


def active_trading_candidate_from_dict(data: dict[str, object]) -> ActiveTradingCandidate:
    return ActiveTradingCandidate(
        candidate_id=_string_value(data, "candidate_id"),
        underlying_symbol=_string_value(data, "underlying_symbol"),
        underlying_type=_string_value(data, "underlying_type"),
        strategy_sleeve=_string_value(data, "strategy_sleeve"),
        structure_type=_string_value(data, "structure_type"),
        option_type=_string_value(data, "option_type"),
        order_action=_string_value(data, "order_action"),
        order_type=_string_value(data, "order_type"),
        position_intent=_string_value(data, "position_intent"),
        dte=_int_value(data, "dte"),
        same_day_round_trip=_bool_value(data, "same_day_round_trip"),
        lifecycle_state=_string_value(data, "lifecycle_state"),
        net_debit=_bool_value(data, "net_debit"),
        defined_risk=_bool_value(data, "defined_risk"),
        uncovered_short_option=_bool_value(data, "uncovered_short_option"),
        spread_pct=_float_value(data, "spread_pct"),
        open_interest=_int_value(data, "open_interest"),
        volume=_int_value(data, "volume"),
        liquidity_score=_float_value(data, "liquidity_score"),
        forecast_move_score=_float_value(data, "forecast_move_score"),
        convexity_value_score=_float_value(data, "convexity_value_score"),
        surface_quality_score=_float_value(data, "surface_quality_score"),
        catalyst_score=_float_value(data, "catalyst_score"),
        flow_score=_float_value(data, "flow_score"),
        fundamental_score=_float_value(data, "fundamental_score"),
        technical_score=_float_value(data, "technical_score"),
        drawdown_pressure_score=_float_value(data, "drawdown_pressure_score"),
        failure_cluster_score=_float_value(data, "failure_cluster_score"),
        requested_position_fraction=_float_value(data, "requested_position_fraction"),
        can_accept_exercise=_bool_value(data, "can_accept_exercise"),
        can_accept_short_stock_from_put_exercise=_bool_value(data, "can_accept_short_stock_from_put_exercise"),
        forced_broker_liquidation_tolerant=_bool_value(data, "forced_broker_liquidation_tolerant"),
        live_allowed=_bool_value(data, "live_allowed"),
        paper_only=_bool_value(data, "paper_only"),
        source_freshness=_string_value(data, "source_freshness"),
    )


def policy_improvement_proposal_from_dict(data: dict[str, object]) -> PolicyImprovementProposal:
    return PolicyImprovementProposal(
        proposal_id=_string_value(data, "proposal_id"),
        layer=_string_value(data, "layer"),
        changes=_dict_value(data, "changes"),
        oos_score=_float_value(data, "oos_score"),
        cpcv_score=_float_value(data, "cpcv_score"),
        deflated_sharpe_ratio=_float_value(data, "deflated_sharpe_ratio"),
        multiple_testing_penalty=_float_value(data, "multiple_testing_penalty"),
        weakens_safety_layer=_bool_value(data, "weakens_safety_layer"),
        touches_hard_rules=_bool_value(data, "touches_hard_rules"),
        live_enablement_requested=_bool_value(data, "live_enablement_requested"),
        paper_only=_bool_value(data, "paper_only"),
    )


def evaluate_strategy_universe(
    candidate: ActiveTradingCandidate,
    thresholds: ActiveTradingThresholds,
) -> PolicyDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    if candidate.underlying_type not in ALLOWED_UNDERLYING_TYPES:
        reasons.append(f"underlying_type {candidate.underlying_type!r} is outside equity/ETF universe")
    if candidate.strategy_sleeve not in ALLOWED_STRATEGY_SLEEVES:
        reasons.append(f"strategy_sleeve {candidate.strategy_sleeve!r} is not canon-approved")
    if candidate.structure_type in FORBIDDEN_STRUCTURE_TYPES:
        reasons.append(f"structure_type {candidate.structure_type!r} is forbidden")
    if candidate.structure_type not in LONG_PREMIUM_STRUCTURE_TYPES:
        reasons.append(f"structure_type {candidate.structure_type!r} is not long-premium approved")
    if not candidate.defined_risk:
        reasons.append("defined_risk=false is forbidden")
    if not candidate.net_debit:
        reasons.append("net_debit=false violates long-premium-only doctrine")
    if candidate.uncovered_short_option:
        reasons.append("uncovered_short_option=true is forbidden")
    if candidate.live_allowed:
        reasons.append("live_allowed=true is blocked by current research-only policy")
    if not candidate.paper_only:
        reasons.append("paper_only=false is blocked by current research-only policy")

    max_spread_pct = _max_spread_pct(candidate, thresholds)
    if candidate.spread_pct > max_spread_pct:
        reasons.append(
            f"spread_pct {candidate.spread_pct:.6f} exceeds max {max_spread_pct:.6f}"
        )
    if candidate.open_interest < thresholds.min_open_interest:
        reasons.append(
            f"open_interest {candidate.open_interest} below min {thresholds.min_open_interest}"
        )
    if candidate.volume < thresholds.min_volume:
        reasons.append(f"volume {candidate.volume} below min {thresholds.min_volume}")
    if candidate.liquidity_score < thresholds.min_liquidity_score:
        reasons.append(
            f"liquidity_score {candidate.liquidity_score:.6f} below min "
            f"{thresholds.min_liquidity_score:.6f}"
        )
    if candidate.forecast_move_score < thresholds.min_forecast_move_score:
        reasons.append(
            f"forecast_move_score {candidate.forecast_move_score:.6f} below min "
            f"{thresholds.min_forecast_move_score:.6f}"
        )
    if candidate.convexity_value_score < thresholds.min_convexity_value_score:
        reasons.append(
            f"convexity_value_score {candidate.convexity_value_score:.6f} below min "
            f"{thresholds.min_convexity_value_score:.6f}"
        )
    if candidate.surface_quality_score < thresholds.min_surface_quality_score:
        reasons.append(
            f"surface_quality_score {candidate.surface_quality_score:.6f} below min "
            f"{thresholds.min_surface_quality_score:.6f}"
        )

    confirmation_count = _confirmation_count(candidate, thresholds)
    if confirmation_count < thresholds.min_confirmation_count:
        reasons.append(
            f"confirmation_count {confirmation_count} below min {thresholds.min_confirmation_count}"
        )

    max_position_fraction = recommended_position_fraction(candidate, thresholds)
    if candidate.requested_position_fraction > max_position_fraction:
        warnings.append(
            f"requested_position_fraction capped from {candidate.requested_position_fraction:.6f} "
            f"to {max_position_fraction:.6f}"
        )

    return _decision(candidate.candidate_id, reasons, warnings, max_position_fraction)


def evaluate_lifecycle_rules(
    candidate: ActiveTradingCandidate,
    thresholds: ActiveTradingThresholds,
) -> PolicyDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    if candidate.dte < 0:
        reasons.append("dte must not be negative")
    if candidate.lifecycle_state not in ALLOWED_SWING_LIFECYCLE_STATES.union(ALLOWED_0DTE_LIFECYCLE_STATES):
        reasons.append(f"lifecycle_state {candidate.lifecycle_state!r} is not recognized")
    if candidate.dte == 0 and candidate.lifecycle_state not in ALLOWED_0DTE_LIFECYCLE_STATES:
        reasons.append("0DTE candidate requires a declared 0DTE lifecycle state")
    if candidate.dte > 0 and candidate.lifecycle_state in ALLOWED_0DTE_LIFECYCLE_STATES:
        warnings.append("0DTE lifecycle state used on non-0DTE candidate")

    if candidate.same_day_round_trip and not _allowed_same_day_completion(candidate):
        reasons.append("same_day_round_trip violates swing-first anti-churn doctrine")

    if candidate.lifecycle_state == "exercise_capable" and not candidate.can_accept_exercise:
        reasons.append("exercise_capable lifecycle requires exercise capacity")
    if (
        candidate.lifecycle_state == "exercise_capable"
        and candidate.option_type == "put"
        and not candidate.can_accept_short_stock_from_put_exercise
    ):
        reasons.append("0DTE long-put exercise path is blocked without short-stock capacity")
    if (
        candidate.lifecycle_state == "forced_broker_liquidation_tolerant"
        and not candidate.forced_broker_liquidation_tolerant
    ):
        reasons.append("forced broker liquidation lifecycle requires explicit tolerance")
    if (
        candidate.lifecycle_state == "forced_broker_liquidation_tolerant"
        and candidate.requested_position_fraction > thresholds.max_forced_liquidation_fraction
    ):
        reasons.append(
            "forced broker liquidation tolerance exceeds max forced-liquidation budget"
        )

    max_position_fraction = recommended_position_fraction(candidate, thresholds)
    return _decision(candidate.candidate_id, reasons, warnings, max_position_fraction)


def evaluate_execution_rules(
    candidate: ActiveTradingCandidate,
    thresholds: ActiveTradingThresholds,
) -> PolicyDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    if candidate.order_action not in ALLOWED_ORDER_ACTIONS:
        reasons.append(f"order_action {candidate.order_action!r} is not supported")
    if candidate.order_action == "open" and candidate.order_type not in ALLOWED_OPEN_ORDER_TYPES:
        reasons.append("opening trades require limit orders")
    if candidate.order_action == "roll" and candidate.order_type not in ALLOWED_OPEN_ORDER_TYPES:
        reasons.append("roll orders require explicit limit pricing")
    if candidate.order_action == "close" and candidate.order_type not in ALLOWED_CLOSE_ORDER_TYPES:
        if candidate.order_type in EMERGENCY_CLOSE_ORDER_TYPES and candidate.position_intent == "emergency_exit":
            warnings.append("emergency market-style sell-to-close allowed only as a fail-safe")
        else:
            reasons.append("closing trades require limit or stop_limit unless emergency_exit")

    max_position_fraction = recommended_position_fraction(candidate, thresholds)
    return _decision(candidate.candidate_id, reasons, warnings, max_position_fraction)


def evaluate_active_trading_policy(
    candidate: ActiveTradingCandidate,
    thresholds: ActiveTradingThresholds,
) -> PolicyDecision:
    decisions = [
        evaluate_strategy_universe(candidate, thresholds),
        evaluate_lifecycle_rules(candidate, thresholds),
        evaluate_execution_rules(candidate, thresholds),
    ]
    reasons = _merge_strings([item.reasons for item in decisions])
    warnings = _merge_strings([item.warnings for item in decisions])
    max_position_fraction = recommended_position_fraction(candidate, thresholds)
    return _decision(candidate.candidate_id, reasons, warnings, max_position_fraction)


def recommended_position_fraction(
    candidate: ActiveTradingCandidate,
    thresholds: ActiveTradingThresholds,
) -> float:
    cap = thresholds.max_default_position_fraction
    if candidate.dte == 0:
        cap = min(cap, thresholds.max_0dte_position_fraction)
    if candidate.lifecycle_state == "forced_broker_liquidation_tolerant":
        cap = min(cap, thresholds.max_forced_liquidation_fraction)
    if candidate.drawdown_pressure_score >= thresholds.drawdown_throttle_score:
        cap = cap * 0.5
    if candidate.failure_cluster_score >= thresholds.failure_cluster_throttle_score:
        cap = cap * 0.5
    return round(max(0.0, min(candidate.requested_position_fraction, cap)), 6)


def evaluate_recursive_improvement(
    proposal: PolicyImprovementProposal,
    thresholds: ActiveTradingThresholds,
) -> PolicyDecision:
    reasons: list[str] = []
    warnings: list[str] = []
    adjusted_oos_score = round(proposal.oos_score - proposal.multiple_testing_penalty, 6)

    if proposal.layer not in ADAPTIVE_RECURSIVE_LAYERS:
        reasons.append(f"layer {proposal.layer!r} is not an adaptive recursive layer")
    if proposal.weakens_safety_layer:
        reasons.append("weakens_safety_layer=true is forbidden")
    if proposal.touches_hard_rules:
        reasons.append("touches_hard_rules=true is forbidden")
    if proposal.live_enablement_requested:
        reasons.append("live_enablement_requested=true is forbidden")
    if not proposal.paper_only:
        reasons.append("paper_only=false is forbidden")
    if adjusted_oos_score < thresholds.min_recursive_oos_score:
        reasons.append(
            f"adjusted_oos_score {adjusted_oos_score:.6f} below min "
            f"{thresholds.min_recursive_oos_score:.6f}"
        )
    if proposal.cpcv_score < thresholds.min_recursive_cpcv_score:
        reasons.append(
            f"cpcv_score {proposal.cpcv_score:.6f} below min "
            f"{thresholds.min_recursive_cpcv_score:.6f}"
        )
    if proposal.deflated_sharpe_ratio < thresholds.min_recursive_deflated_sharpe:
        reasons.append(
            f"deflated_sharpe_ratio {proposal.deflated_sharpe_ratio:.6f} below min "
            f"{thresholds.min_recursive_deflated_sharpe:.6f}"
        )

    if not reasons:
        warnings.append("accepted only for offline paper tournament evaluation")
    return PolicyDecision(
        subject_id=proposal.proposal_id,
        allowed=not reasons,
        verdict="approved_offline_recursive_improvement" if not reasons else "rejected_by_recursive_safety_policy",
        reasons=reasons,
        warnings=warnings,
        max_position_fraction=0.0,
        policy_version=ACTIVE_TRADING_POLICY_VERSION,
    )


def _decision(
    subject_id: str,
    reasons: list[str],
    warnings: list[str],
    max_position_fraction: float,
) -> PolicyDecision:
    return PolicyDecision(
        subject_id=subject_id,
        allowed=not reasons,
        verdict="approved_paper_policy_candidate" if not reasons else "rejected_by_active_trading_policy",
        reasons=reasons,
        warnings=warnings,
        max_position_fraction=max_position_fraction,
        policy_version=ACTIVE_TRADING_POLICY_VERSION,
    )


def _allowed_same_day_completion(candidate: ActiveTradingCandidate) -> bool:
    if candidate.dte != 0:
        return False
    return (
        candidate.lifecycle_state == "forced_broker_liquidation_tolerant"
        and candidate.forced_broker_liquidation_tolerant
    )


def _max_spread_pct(
    candidate: ActiveTradingCandidate,
    thresholds: ActiveTradingThresholds,
) -> float:
    if candidate.dte == 0:
        return thresholds.max_0dte_bid_ask_spread_pct
    return thresholds.max_bid_ask_spread_pct


def _confirmation_count(
    candidate: ActiveTradingCandidate,
    thresholds: ActiveTradingThresholds,
) -> int:
    confirmations = [
        candidate.catalyst_score,
        candidate.flow_score,
        candidate.fundamental_score,
        candidate.technical_score,
    ]
    return sum(1 for score in confirmations if score >= thresholds.min_confirmation_score)


def _merge_strings(groups: list[list[str]]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            if value not in seen:
                output.append(value)
                seen.add(value)
    return output


def _string_value(data: dict[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    if not value:
        raise ValueError(f"{key} must not be empty")
    return value


def _bool_value(data: dict[str, object], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _int_value(data: dict[str, object], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _float_value(data: dict[str, object], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _dict_value(data: dict[str, object], key: str) -> dict[str, object]:
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be dict")
    return _copy_dict(value)


def _copy_dict(value: dict[Any, Any]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("changes keys must be str")
        output[key] = item
    return output
