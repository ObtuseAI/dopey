"""Decision engine for the DOPEY offline 0DTE special lifecycle risk model."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .zero_dte_risk_model import (
    ZERO_DTE_RISK_MODEL_VERSION,
    ZeroDTERiskDecision,
    ZeroDTERiskInput,
    stable_zero_dte_hash,
    zero_dte_decision_hash,
)
from .zero_dte_risk_thresholds import ZeroDTERiskThresholds


APPROVED_ZERO_DTE_DECISIONS: frozenset[str] = frozenset({
    "approved_for_paper_open",
    "approved_with_throttle",
})

REQUIRED_ZERO_DTE_CONTROLS: tuple[str, ...] = (
    "paper_only_live_blocked",
    "long_call_or_long_put_buy_to_open",
    "strict_liquidity",
    "strict_spread",
    "strict_slippage",
    "greeks_stable_enough",
    "iv_not_overpaid",
    "event_macro_regime_acceptable",
    "proof_and_signal_present",
    "explicit_thesis",
    "explicit_exit_or_expiry_plan",
    "risk_cap",
    "special_lifecycle",
)


def evaluate_zero_dte_candidate(
    candidate: ZeroDTERiskInput,
    thresholds: ZeroDTERiskThresholds,
) -> ZeroDTERiskDecision:
    components = score_zero_dte_candidate(candidate)
    failed = failed_controls(candidate, thresholds, components)
    decision = choose_decision(candidate, thresholds, components, failed)
    risk_score = aggregate_risk_score(components)
    risk_tier = risk_tier_for(risk_score, failed, thresholds)
    approval_status = approval_status_for(decision)
    premium_cap = premium_cap_for(decision, thresholds)
    contracts_cap = contracts_cap_for(decision, thresholds)
    reason_codes = reason_codes_for(candidate, decision, failed, components)
    expiry_plan = expiry_handling_plan_for(candidate, decision)
    seed = ZeroDTERiskDecision(
        candidate_id=candidate.candidate_id,
        decision=decision,
        approval_status=approval_status,
        risk_score=risk_score,
        risk_tier=risk_tier,
        required_controls=list(REQUIRED_ZERO_DTE_CONTROLS),
        failed_controls=failed,
        max_paper_premium_at_risk=premium_cap,
        max_contracts_paper=contracts_cap,
        expiry_handling_plan=expiry_plan,
        special_close_allowed=decision in APPROVED_ZERO_DTE_DECISIONS,
        special_close_reason_required=decision in APPROVED_ZERO_DTE_DECISIONS,
        audit_required=True,
        reason_codes=reason_codes,
        paper_only=True,
        live_blocked=True,
        decision_hash="",
        threshold_version=thresholds.threshold_version,
        score_components=components,
        candidate_input=candidate.to_dict(),
        model_version=ZERO_DTE_RISK_MODEL_VERSION,
    )
    return ZeroDTERiskDecision(
        candidate_id=seed.candidate_id,
        decision=seed.decision,
        approval_status=seed.approval_status,
        risk_score=seed.risk_score,
        risk_tier=seed.risk_tier,
        required_controls=seed.required_controls,
        failed_controls=seed.failed_controls,
        max_paper_premium_at_risk=seed.max_paper_premium_at_risk,
        max_contracts_paper=seed.max_contracts_paper,
        expiry_handling_plan=seed.expiry_handling_plan,
        special_close_allowed=seed.special_close_allowed,
        special_close_reason_required=seed.special_close_reason_required,
        audit_required=seed.audit_required,
        reason_codes=seed.reason_codes,
        paper_only=True,
        live_blocked=True,
        decision_hash=zero_dte_decision_hash(seed),
        threshold_version=seed.threshold_version,
        score_components=seed.score_components,
        candidate_input=seed.candidate_input,
        model_version=seed.model_version,
    )


def score_zero_dte_candidate(candidate: ZeroDTERiskInput) -> dict[str, float]:
    spread_penalty = _spread_adjusted_entry_penalty(candidate)
    liquidity_risk = _clamp(
        (1.0 - candidate.liquidity_score) * 0.55
        + _gap_ratio(candidate.volume, 1_000) * 0.20
        + _gap_ratio(candidate.open_interest, 2_000) * 0.15
        + min(1.0, candidate.spread_pct / 0.08) * 0.10,
        0.0,
        1.0,
    )
    gamma_instability = _clamp(abs(candidate.gamma) * 8.5, 0.0, 1.0)
    theta_decay = _clamp(max(0.0, -candidate.theta) / 0.32, 0.0, 1.0)
    iv_shock = _clamp(
        candidate.iv_rank_fixture * 0.58
        + candidate.implied_volatility * 0.32
        + candidate.event_risk_score * 0.10,
        0.0,
        1.0,
    )
    premium_overpayment = _clamp(
        candidate.iv_rank_fixture * 0.50
        + spread_penalty * 1.80
        + max(0.0, candidate.implied_volatility - 0.45) * 0.60,
        0.0,
        1.0,
    )
    event_macro = _clamp(max(candidate.event_risk_score, candidate.macro_risk_score), 0.0, 1.0)
    regime_misalignment = _clamp(1.0 - candidate.regime_score, 0.0, 1.0)
    proof_gap = _clamp(1.0 - min(candidate.proof_score, candidate.signal_confidence), 0.0, 1.0)
    direction_gap = _direction_gap(candidate)
    return {
        "liquidity_risk": round(liquidity_risk, 6),
        "spread_risk": round(_clamp(candidate.spread_pct / 0.08, 0.0, 1.0), 6),
        "slippage_risk": round(_clamp(candidate.slippage_score, 0.0, 1.0), 6),
        "spread_adjusted_entry_penalty": round(spread_penalty, 6),
        "gamma_instability_score": round(gamma_instability, 6),
        "theta_decay_pressure": round(theta_decay, 6),
        "iv_shock_score": round(iv_shock, 6),
        "premium_overpayment_score": round(premium_overpayment, 6),
        "event_macro_risk": round(event_macro, 6),
        "regime_misalignment": round(regime_misalignment, 6),
        "proof_gap": round(proof_gap, 6),
        "direction_gap": round(direction_gap, 6),
    }


def failed_controls(
    candidate: ZeroDTERiskInput,
    thresholds: ZeroDTERiskThresholds,
    components: dict[str, float],
) -> list[str]:
    failed: list[str] = []
    if not candidate.paper_only or not candidate.live_blocked:
        failed.append("paper_only_live_blocked")
    if candidate.option_type not in {"call", "put"}:
        failed.append("long_call_or_long_put_buy_to_open")
    if candidate.order_action != "buy_to_open":
        failed.append("long_call_or_long_put_buy_to_open")
    if candidate.structure_type not in {"long_call", "long_put", "single"}:
        failed.append("long_call_or_long_put_buy_to_open")
    if not candidate.defined_risk:
        failed.append("long_call_or_long_put_buy_to_open")
    if candidate.spread_pct > thresholds.max_spread_pct:
        failed.append("strict_spread")
    if candidate.volume < thresholds.minimum_volume:
        failed.append("strict_liquidity")
    if candidate.open_interest < thresholds.minimum_open_interest:
        failed.append("strict_liquidity")
    if candidate.liquidity_score < thresholds.minimum_liquidity_score:
        failed.append("strict_liquidity")
    if candidate.slippage_score > thresholds.max_slippage_score:
        failed.append("strict_slippage")
    if components["spread_adjusted_entry_penalty"] > thresholds.max_spread_adjusted_entry_penalty:
        failed.append("strict_slippage")
    if components["gamma_instability_score"] > thresholds.max_gamma_instability_score:
        failed.append("greeks_stable_enough")
    if components["theta_decay_pressure"] > thresholds.max_theta_decay_pressure:
        failed.append("greeks_stable_enough")
    abs_delta = abs(candidate.delta)
    if abs_delta < thresholds.minimum_abs_delta or abs_delta > thresholds.maximum_abs_delta:
        failed.append("greeks_stable_enough")
    if components["iv_shock_score"] > thresholds.max_iv_shock_score:
        failed.append("iv_not_overpaid")
    if components["premium_overpayment_score"] > thresholds.max_premium_overpayment_score:
        failed.append("iv_not_overpaid")
    if candidate.iv_rank_fixture < thresholds.min_iv_rank_fixture or candidate.iv_rank_fixture > thresholds.max_iv_rank_fixture:
        failed.append("iv_not_overpaid")
    if candidate.implied_volatility > thresholds.max_implied_volatility:
        failed.append("iv_not_overpaid")
    if candidate.event_risk_score > thresholds.max_event_risk_score:
        failed.append("event_macro_regime_acceptable")
    if candidate.macro_risk_score > thresholds.max_macro_risk_score:
        failed.append("event_macro_regime_acceptable")
    if candidate.regime_score < thresholds.minimum_regime_score:
        failed.append("event_macro_regime_acceptable")
    if candidate.proof_score < thresholds.minimum_proof_score:
        failed.append("proof_and_signal_present")
    if candidate.signal_confidence < thresholds.minimum_signal_confidence:
        failed.append("proof_and_signal_present")
    if thresholds.explicit_thesis_required and not candidate.explicit_thesis.strip():
        failed.append("explicit_thesis")
    if thresholds.explicit_exit_plan_required and not candidate.explicit_exit_or_expiry_plan.strip():
        failed.append("explicit_exit_or_expiry_plan")
    if thresholds.max_paper_premium_at_risk_per_trade <= 0.0:
        failed.append("risk_cap")
    if thresholds.max_zero_dte_candidates_approved_per_day <= 0:
        failed.append("risk_cap")
    if thresholds.special_lifecycle_required and candidate.expected_hold_minutes <= 0:
        failed.append("special_lifecycle")
    if candidate.special_close_requested and thresholds.explicit_same_day_special_close_reason_required and not candidate.special_close_reason.strip():
        failed.append("special_lifecycle")
    return _dedupe(failed)


def choose_decision(
    candidate: ZeroDTERiskInput,
    thresholds: ZeroDTERiskThresholds,
    components: dict[str, float],
    failed: list[str],
) -> str:
    if not candidate.live_blocked:
        return "blocked_live_path"
    if not candidate.paper_only:
        return "blocked_policy_violation"
    if "long_call_or_long_put_buy_to_open" in failed:
        if candidate.order_action == "sell_to_open":
            return "blocked_policy_violation"
        return "blocked_policy_violation"
    if "explicit_thesis" in failed:
        return "blocked_weak_thesis"
    if "explicit_exit_or_expiry_plan" in failed:
        return "blocked_missing_exit_plan"
    if "proof_and_signal_present" in failed:
        return "blocked_missing_proof"
    if "strict_spread" in failed:
        return "blocked_spread"
    if "strict_liquidity" in failed:
        return "blocked_liquidity"
    if "strict_slippage" in failed:
        return "blocked_slippage"
    if "greeks_stable_enough" in failed and components["gamma_instability_score"] > thresholds.max_gamma_instability_score:
        return "blocked_gamma_instability"
    if "greeks_stable_enough" in failed:
        return "blocked_theta_decay"
    if "iv_not_overpaid" in failed:
        return "blocked_iv_shock"
    if "event_macro_regime_acceptable" in failed:
        return "blocked_event_risk"
    if "risk_cap" in failed or "special_lifecycle" in failed:
        return "blocked_policy_violation"
    if candidate.later_expiry_alternative_available:
        return "prefer_non_zero_dte_alternative"
    if candidate.expiry_managed_only_requested:
        return "expiry_managed_only"
    risk_score = aggregate_risk_score(components)
    if risk_score >= thresholds.block_risk_score:
        return "rejected"
    if risk_score >= thresholds.throttle_risk_score:
        return "approved_with_throttle"
    return "approved_for_paper_open"


def aggregate_risk_score(components: dict[str, float]) -> float:
    risk_score = (
        components["liquidity_risk"] * 0.13
        + components["spread_risk"] * 0.10
        + components["slippage_risk"] * 0.10
        + components["gamma_instability_score"] * 0.12
        + components["theta_decay_pressure"] * 0.12
        + components["iv_shock_score"] * 0.10
        + components["premium_overpayment_score"] * 0.10
        + components["event_macro_risk"] * 0.09
        + components["regime_misalignment"] * 0.07
        + components["proof_gap"] * 0.05
        + components["direction_gap"] * 0.02
    )
    return round(_clamp(risk_score, 0.0, 1.0), 6)


def risk_tier_for(
    risk_score: float,
    failed: list[str],
    thresholds: ZeroDTERiskThresholds,
) -> str:
    if failed:
        return "blocked_fixture_risk"
    if risk_score >= thresholds.block_risk_score:
        return "blocked_fixture_risk"
    if risk_score >= thresholds.throttle_risk_score:
        return "high_fixture_risk"
    if risk_score >= 0.22:
        return "moderate_fixture_risk"
    return "low_fixture_risk"


def approval_status_for(decision: str) -> str:
    if decision == "approved_for_paper_open":
        return "approved"
    if decision == "approved_with_throttle":
        return "throttled"
    if decision == "prefer_non_zero_dte_alternative":
        return "alternative_recommended"
    if decision == "expiry_managed_only":
        return "expiry_managed_only"
    return "blocked"


def reason_codes_for(
    candidate: ZeroDTERiskInput,
    decision: str,
    failed: list[str],
    components: dict[str, float],
) -> list[str]:
    reasons: list[str] = []
    for control in failed:
        reasons.append(reason_code_for_failed_control(candidate, control, components))
    if decision == "approved_for_paper_open":
        reasons.append("zero_dte_risk_model_approved_strict_controls")
    elif decision == "approved_with_throttle":
        reasons.append("zero_dte_risk_model_approved_with_throttle")
    elif decision == "prefer_non_zero_dte_alternative":
        reasons.append("later_expiry_alternative_preferred")
    elif decision == "expiry_managed_only":
        reasons.append("expiry_managed_only_no_discretionary_intraday_close")
    elif decision == "rejected":
        reasons.append("zero_dte_risk_score_rejected")
    elif not reasons:
        reasons.append(f"{decision}_by_zero_dte_risk_model")
    return _dedupe(reasons)


def reason_code_for_failed_control(
    candidate: ZeroDTERiskInput,
    control: str,
    components: dict[str, float],
) -> str:
    if control == "paper_only_live_blocked":
        if not candidate.live_blocked:
            return "blocked_live_path"
        return "paper_only_required"
    if control == "long_call_or_long_put_buy_to_open":
        if candidate.order_action == "sell_to_open":
            return "sell_to_open_rejected"
        if candidate.structure_type not in {"long_call", "long_put", "single"}:
            return "unsupported_spread_or_structure_rejected"
        if not candidate.defined_risk:
            return "undefined_risk_structure_rejected"
        return "non_call_put_option_type_rejected"
    if control == "explicit_thesis":
        return "missing_explicit_thesis"
    if control == "explicit_exit_or_expiry_plan":
        return "missing_explicit_exit_or_expiry_plan"
    if control == "proof_and_signal_present":
        return "insufficient_proof_or_signal_confidence"
    if control == "strict_spread":
        return "spread_pct_exceeds_zero_dte_limit"
    if control == "strict_liquidity":
        return "liquidity_below_zero_dte_floor"
    if control == "strict_slippage":
        return "slippage_or_entry_penalty_exceeds_limit"
    if control == "greeks_stable_enough" and components["gamma_instability_score"] >= components["theta_decay_pressure"]:
        return "gamma_instability_exceeds_limit"
    if control == "greeks_stable_enough":
        return "theta_decay_pressure_exceeds_limit"
    if control == "iv_not_overpaid":
        return "iv_or_premium_overpayment_exceeds_limit"
    if control == "event_macro_regime_acceptable":
        return "event_macro_or_regime_risk_exceeds_limit"
    if control == "risk_cap":
        return "zero_dte_risk_cap_missing_or_invalid"
    if control == "special_lifecycle":
        return "zero_dte_special_lifecycle_control_missing"
    return f"{control}_failed"


def premium_cap_for(decision: str, thresholds: ZeroDTERiskThresholds) -> float:
    if decision == "approved_with_throttle":
        return round(thresholds.max_paper_premium_at_risk_per_trade * thresholds.throttle_premium_factor, 6)
    if decision == "approved_for_paper_open":
        return round(thresholds.max_paper_premium_at_risk_per_trade, 6)
    return 0.0


def contracts_cap_for(decision: str, thresholds: ZeroDTERiskThresholds) -> int:
    if decision == "approved_with_throttle":
        return thresholds.throttle_max_contracts_paper
    if decision == "approved_for_paper_open":
        return thresholds.default_max_contracts_paper
    return 0


def expiry_handling_plan_for(candidate: ZeroDTERiskInput, decision: str) -> str:
    if decision == "expiry_managed_only":
        return "expiry_managed_only_no_discretionary_same_day_close"
    if decision in APPROVED_ZERO_DTE_DECISIONS:
        return candidate.explicit_exit_or_expiry_plan
    if decision == "prefer_non_zero_dte_alternative":
        return "use_later_expiry_alternative_instead_of_0dte"
    return "blocked_no_expiry_handling_authority"


def _spread_adjusted_entry_penalty(candidate: ZeroDTERiskInput) -> float:
    mid = max(candidate.mid, 0.01)
    ask_over_mid = max(0.0, candidate.ask - candidate.mid) / mid
    return round(_clamp(candidate.spread_pct + candidate.slippage_score * 0.18 + ask_over_mid, 0.0, 1.0), 6)


def _direction_gap(candidate: ZeroDTERiskInput) -> float:
    if candidate.option_type == "call":
        return _clamp(0.70 - max(candidate.trend_score, candidate.regime_score), 0.0, 1.0)
    if candidate.option_type == "put":
        return _clamp(0.70 - max(candidate.reversal_score, candidate.regime_score), 0.0, 1.0)
    return 1.0


def _gap_ratio(value: int, required: int) -> float:
    if value >= required:
        return 0.0
    return _clamp((required - value) / max(required, 1), 0.0, 1.0)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output


def decision_reproducibility_hash(decision: ZeroDTERiskDecision) -> str:
    payload = asdict(decision)
    payload["decision_hash"] = ""
    return stable_zero_dte_hash(payload)
