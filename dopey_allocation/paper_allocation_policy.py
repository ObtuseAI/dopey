"""Strict deterministic paper allocation policy."""
from __future__ import annotations

from typing import Any

from .allocation_decision_models import PaperAllocationDecision, paper_allocation_decision_hash
from .paper_risk_budget import PaperRiskBudget
from .proof_weighted_allocation_models import ProofWeightedOpportunity


def default_paper_allocation_policy() -> dict[str, Any]:
    return {
        "policy_id": "dopey-proof-weighted-paper-allocation-policy-v1",
        "allowed_strategy_types": [
            "zero_dte_long_call",
            "zero_dte_long_put",
            "swing_long_call",
            "swing_long_put",
            "delayed_rotation_long_call",
            "delayed_rotation_long_put",
            "no_trade",
        ],
        "blocked_actions": ["sell_to_open", "naked_sale", "unsupported_spread", "same_day_churn", "live_path"],
        "paper_only": True,
        "live_blocked": True,
        "real_capital_sizing_allowed": False,
        "broker_override_allowed": False,
        "paper_broker_override_allowed": False,
    }


def decide_paper_allocation(
    opportunity: ProofWeightedOpportunity,
    policy: dict[str, Any],
    budget: PaperRiskBudget,
) -> PaperAllocationDecision:
    block_reasons = _block_reasons(opportunity)
    proof_reasons = _proof_reasons(opportunity)
    constraint_reasons = _constraint_reasons(opportunity, budget)
    decision, tier, attention, risk_units, contract_units, throttle, more_coverage = _decision_shape(opportunity, block_reasons, constraint_reasons)
    if risk_units > budget.max_paper_premium_risk_units_per_opportunity:
        risk_units = budget.max_paper_premium_risk_units_per_opportunity
        throttle = "opportunity_budget_cap"
        constraint_reasons = [*constraint_reasons, "paper_premium_risk_units_capped_per_opportunity"]
        if decision == "allocate_paper":
            decision = "allocate_paper_throttled"
            tier = "small_paper"
    if attention > budget.max_paper_attention_per_opportunity:
        attention = budget.max_paper_attention_per_opportunity
        constraint_reasons = [*constraint_reasons, "paper_attention_capped_per_opportunity"]
    draft = PaperAllocationDecision(
        allocation_id=f"paper-allocation-{opportunity.opportunity_id}",
        opportunity_id=opportunity.opportunity_id,
        decision=decision,
        paper_attention_weight=round(attention, 6),
        paper_premium_risk_units=round(risk_units, 6),
        max_paper_contract_units=contract_units,
        allocation_tier=tier,
        risk_throttle=throttle,
        block_reason_codes=_dedupe(block_reasons),
        proof_reason_codes=_dedupe(proof_reasons),
        constraint_reason_codes=_dedupe(constraint_reasons),
        allocator_tags=_allocator_tags(opportunity, decision, tier),
        requires_more_fixture_coverage=more_coverage,
        paper_only=True,
        live_blocked=True,
        decision_hash="",
    )
    return PaperAllocationDecision(**{**draft.to_dict(), "decision_hash": paper_allocation_decision_hash(draft)})


def _block_reasons(opportunity: ProofWeightedOpportunity) -> list[str]:
    reasons: list[str] = []
    if opportunity.live_blocked is not True or opportunity.risk_tier == "live_path":
        reasons.append("live_path_rejected")
    if "sell_to_open" in opportunity.risk_tier:
        reasons.append("sell_to_open_rejected")
    if "unsupported" in opportunity.risk_tier:
        reasons.append("unsupported_spread_rejected")
    if "naked" in opportunity.risk_tier or "undefined" in opportunity.risk_tier:
        reasons.append("undefined_risk_rejected")
    if opportunity.no_day_trade_constraint == "same_day_churn_attempt":
        reasons.append("same_day_churn_rejected")
    if "missing_thesis" in opportunity.risk_tier:
        reasons.append("missing_explicit_thesis")
    if "missing_exit_plan" in opportunity.risk_tier:
        reasons.append("missing_explicit_exit_plan")
    if opportunity.strategy_type == "no_trade" or opportunity.preferred_path == "no_trade":
        reasons.append("no_trade_preferred")
    if opportunity.liquidity_score < 0.35:
        reasons.append("liquidity_below_allocator_floor")
    if opportunity.spread_pct > 0.18:
        reasons.append("spread_exceeds_allocator_limit")
    if opportunity.contradiction_score >= 0.72:
        reasons.append("contradictory_evidence_requires_more_fixture_coverage")
    return reasons


def _proof_reasons(opportunity: ProofWeightedOpportunity) -> list[str]:
    reasons = [
        f"threshold:{opportunity.threshold_survival_status}",
        f"preferred_path:{opportunity.preferred_path}",
        f"coverage:{opportunity.coverage_score:.2f}",
    ]
    if opportunity.proof_score >= 0.82 and opportunity.signal_confidence >= 0.78:
        reasons.append("strong_proof_and_signal")
    if opportunity.strategy_type.startswith("swing") and opportunity.preferred_path == "swing":
        reasons.append("hybrid_prefers_swing")
    if opportunity.strategy_type.startswith("zero_dte") and opportunity.preferred_path == "zero_dte":
        reasons.append("hybrid_prefers_zero_dte")
    if opportunity.delayed_rotation_required:
        reasons.append("delayed_rotation_advisory_reserve")
    return reasons


def _constraint_reasons(opportunity: ProofWeightedOpportunity, budget: PaperRiskBudget) -> list[str]:
    reasons: list[str] = []
    if opportunity.strategy_type.startswith("zero_dte"):
        reasons.append("zero_dte_special_lifecycle_cap")
    if opportunity.theta_pressure > 0.62:
        reasons.append("theta_pressure_allocation_reduced")
    if opportunity.gamma_instability > 0.62:
        reasons.append("gamma_instability_allocation_capped")
    if opportunity.iv_overpayment_risk > 0.68:
        reasons.append("iv_crush_exposure_capped")
    if max(opportunity.event_risk, opportunity.macro_risk) > 0.72:
        reasons.append("event_macro_exposure_capped")
    if opportunity.underlying_family_id == "underlying-family-05":
        reasons.append("low_liquidity_family_starved")
    if opportunity.underlying_family_id == "underlying-family-09" and opportunity.strategy_type.startswith("swing"):
        reasons.append("trend_persistence_swing_favored")
    if opportunity.underlying_family_id == "underlying-family-12" and opportunity.strategy_type.startswith("zero_dte"):
        reasons.append("pin_risk_zero_dte_reduced")
    if opportunity.regime_family == "macro_shock" and opportunity.delayed_rotation_required:
        reasons.append("macro_sensitive_delayed_rotation_preferred")
    if opportunity.risk_tier == "call_put_imbalance":
        reasons.append("call_put_imbalance_monitor_throttle")
    if opportunity.risk_tier == "zero_dte_share_cap_probe":
        reasons.append("zero_dte_exposure_share_cap_throttle")
    if budget.max_zero_dte_paper_exposure_share < 0.40:
        reasons.append("zero_dte_budget_share_strict")
    return _dedupe(reasons)


def _decision_shape(
    opportunity: ProofWeightedOpportunity,
    block_reasons: list[str],
    constraint_reasons: list[str],
) -> tuple[str, str, float, float, int, str, list[str]]:
    if "live_path_rejected" in block_reasons:
        return "reject_live_path", "none", 0.0, 0.0, 0, "blocked", []
    if any(reason in block_reasons for reason in ["sell_to_open_rejected", "unsupported_spread_rejected", "undefined_risk_rejected", "missing_explicit_thesis", "missing_explicit_exit_plan"]):
        return "reject_policy_violation", "none", 0.0, 0.0, 0, "blocked", []
    if "same_day_churn_rejected" in block_reasons:
        return "reject_no_day_trade_constraint", "none", 0.0, 0.0, 0, "blocked", []
    if "liquidity_below_allocator_floor" in block_reasons or "spread_exceeds_allocator_limit" in block_reasons:
        return "reject_liquidity", "none", 0.0, 0.0, 0, "blocked", []
    if "no_trade_preferred" in block_reasons:
        return "reject_no_trade", "none", 0.0, 0.0, 0, "blocked", []
    if "contradictory_evidence_requires_more_fixture_coverage" in block_reasons:
        return "needs_more_fixture_coverage", "watchlist", 0.1, 0.0, 0, "coverage_needed", ["contradictory_hybrid_evidence"]
    if opportunity.coverage_score < 0.70:
        return "allocate_paper_shadow_only", "paper_shadow", 0.18, 0.35, 0, "shadow_only", ["allocation_shadow_needs_more_fixture_coverage"]
    if opportunity.delayed_rotation_required or opportunity.strategy_type.startswith("delayed_rotation"):
        return "reserve_for_delayed_rotation", "watchlist", 0.25, 0.25, 0, "reserve_only", []
    if any(reason in constraint_reasons for reason in ["theta_pressure_allocation_reduced", "gamma_instability_allocation_capped", "call_put_imbalance_monitor_throttle", "zero_dte_exposure_share_cap_throttle", "pin_risk_zero_dte_reduced"]):
        return "allocate_paper_throttled", "small_paper", 0.32, 0.75, 1, "risk_reduced", []
    if any(reason in constraint_reasons for reason in ["event_macro_exposure_capped", "iv_crush_exposure_capped"]) and opportunity.strategy_type.startswith("zero_dte"):
        return "allocate_paper_throttled", "small_paper", 0.30, 0.70, 1, "event_or_iv_capped", []
    if opportunity.strategy_type.startswith("swing") and opportunity.proof_score >= 0.78 and opportunity.hybrid_preference_score >= 0.62:
        return "allocate_paper", "standard_paper", 0.72, 2.4, 2, "none", []
    if opportunity.strategy_type.startswith("zero_dte") and opportunity.proof_score >= 0.84 and opportunity.hybrid_preference_score >= 0.62:
        return "allocate_paper", "aggressive_paper_capped", 0.55, 1.15, 1, "zero_dte_capped", []
    if opportunity.proof_score >= 0.60:
        return "allocate_paper_throttled", "small_paper", 0.34, 0.8, 1, "moderate_evidence", []
    return "watchlist_only", "watchlist", 0.08, 0.0, 0, "weak_evidence", []


def _allocator_tags(opportunity: ProofWeightedOpportunity, decision: str, tier: str) -> list[str]:
    tags = [f"decision:{decision}", f"tier:{tier}", f"strategy:{opportunity.strategy_type}"]
    if opportunity.strategy_type.startswith("zero_dte"):
        tags.append("zero_dte_strict_cap")
    if opportunity.strategy_type.startswith("swing"):
        tags.append("swing_can_exceed_zero_dte_when_supported")
    if opportunity.delayed_rotation_required:
        tags.append("delayed_rotation_advisory_only")
    if opportunity.coverage_score < 0.70:
        tags.append("paper_shadow_not_standard")
    return sorted(set(tags))


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
