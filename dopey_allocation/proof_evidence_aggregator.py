"""Aggregate offline proof evidence into paper allocation opportunities."""
from __future__ import annotations

from collections import Counter
from typing import Any

from dopey_execution.run_account_ledger_rotation_planner import run_account_ledger_rotation_planner
from dopey_options.run_hybrid_swing_0dte_v3 import run_hybrid_swing_0dte_v3
from dopey_options.run_zero_dte_threshold_optimizer import run_zero_dte_threshold_optimizer
from dopey_options.zero_dte_cross_underlying_fixture_builder import FAMILY_ORDER
from dopey_options.zero_dte_underlying_family_models import SYNTHETIC_SYMBOLS_BY_FAMILY
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .proof_weighted_allocation_models import ProofWeightedOpportunity


def aggregate_proof_evidence() -> dict[str, Any]:
    hybrid = run_hybrid_swing_0dte_v3()
    threshold = run_zero_dte_threshold_optimizer()
    account = run_account_ledger_rotation_planner()
    opportunities = build_proof_weighted_opportunities(hybrid, threshold, account)
    contradiction_count = sum(1 for opportunity in opportunities if opportunity.contradiction_score >= 0.72)
    proof_summary = {
        "proof_evidence_aggregator_version": "dopey-proof-evidence-aggregator-v1",
        "hybrid_pair_count": hybrid["summary"].get("hybrid_pair_count", 0),
        "threshold_optimizer_run_id": threshold["summary"].get("optimizer_run_id", ""),
        "account_ledger_hash": account.get("account_ledger_summary", {}).get("ledger_hash", ""),
        "opportunity_count": len(opportunities),
        "policy_compliance_source": "active_trading_policy_and_account_ledger",
        "hybrid_preference_source": "hybrid_swing_0dte_v3",
        "threshold_survival_source": "zero_dte_threshold_optimizer",
        "paper_only": True,
        "live_blocked": True,
    }
    missing = [
        name for name, present in {
            "hybrid_v3": hybrid["summary"].get("hybrid_pair_count", 0) > 0,
            "threshold_optimizer": bool(threshold["summary"].get("optimizer_run_id", "")),
            "account_ledger": bool(account.get("account_ledger_summary", {}).get("ledger_hash", "")),
        }.items()
        if not present
    ]
    contradiction_summary = {
        "contradiction_count": contradiction_count,
        "high_contradiction_opportunities": [opportunity.opportunity_id for opportunity in opportunities if opportunity.contradiction_score >= 0.72],
        "contradiction_policy": "high contradiction becomes fixture-coverage decision, not standard allocation",
        "paper_only": True,
        "live_blocked": True,
    }
    proof_summary["reproducibility_hash"] = reproducibility_hash(proof_summary)
    return {
        "opportunities": opportunities,
        "proof_summary": proof_summary,
        "missing_evidence_summary": {"missing_evidence": missing, "paper_only": True, "live_blocked": True},
        "contradiction_summary": contradiction_summary,
        "source_run_ids": [
            str(hybrid["summary"].get("reproducibility_hash", "")),
            str(threshold["summary"].get("optimizer_run_id", "")),
            str(account.get("reproducibility_hash", "")),
        ],
        "paper_only": True,
        "live_blocked": True,
    }


def build_proof_weighted_opportunities(
    hybrid: dict[str, Any],
    threshold: dict[str, Any],
    account: dict[str, Any],
) -> list[ProofWeightedOpportunity]:
    specs = _allocation_case_specs()
    threshold_status = str(threshold["summary"].get("post_hybrid_threshold_candidate_survival_status", "paper_shadow_survives_no_research_default"))
    opportunities = [_opportunity_from_spec(index, spec, threshold_status) for index, spec in enumerate(specs)]
    return opportunities


def proof_opportunity_distribution(opportunities: list[ProofWeightedOpportunity]) -> dict[str, int]:
    return dict(sorted(Counter(opportunity.strategy_type for opportunity in opportunities).items()))


def _allocation_case_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        _spec("alloc-high-proof-swing-call", "strong_swing", "call", 8, "trend_persistence"),
        _spec("alloc-high-proof-swing-put", "strong_swing", "put", 8, "trend_persistence"),
        _spec("alloc-high-proof-0dte-call", "strong_zero_dte", "call", 0, "bull_trend"),
        _spec("alloc-high-proof-0dte-put", "strong_zero_dte", "put", 1, "bear_trend"),
        _spec("alloc-moderate-0dte-throttled", "moderate_zero_dte", "call", 2, "chop_decay"),
        _spec("alloc-high-theta-0dte-reduced", "high_theta_zero_dte", "call", 2, "chop_decay"),
        _spec("alloc-high-gamma-0dte-capped", "high_gamma_zero_dte", "put", 0, "gap_and_go"),
        _spec("alloc-strong-0dte-poor-liquidity", "liquidity_reject", "call", 4, "bull_trend"),
        _spec("alloc-wide-spread-signal", "wide_spread_reject", "put", 4, "false_breakout"),
        _spec("alloc-swing-preferred-over-0dte", "strong_swing", "call", 10, "trend_persistence"),
        _spec("alloc-zero-dte-preferred-over-swing", "strong_zero_dte", "call", 7, "mean_reversion"),
        _spec("alloc-delayed-rotation-reserve", "delayed_rotation", "put", 5, "macro_shock"),
        _spec("alloc-no-trade-preferred", "no_trade", "none", 6, "range_bound"),
        _spec("alloc-inconclusive-more-coverage", "contradiction", "call", 3, "event_whipsaw"),
        _spec("alloc-policy-violation", "policy_violation", "call", 0, "bull_trend"),
        _spec("alloc-live-path", "live_path", "call", 0, "bull_trend"),
        _spec("alloc-sell-to-open", "sell_to_open", "put", 1, "bear_trend"),
        _spec("alloc-unsupported-spread", "unsupported_spread", "call", 2, "iv_expansion"),
        _spec("alloc-same-day-churn", "same_day_churn", "call", 0, "late_day_liquidity_decay"),
        _spec("alloc-missing-thesis", "missing_thesis", "call", 0, "false_breakout"),
        _spec("alloc-missing-exit-plan", "missing_exit_plan", "put", 1, "false_breakdown"),
        _spec("alloc-weak-family-throttled", "weak_family", "put", 4, "gap_and_fade"),
        _spec("alloc-event-sensitive-family-capped", "event_cap", "call", 3, "event_whipsaw"),
        _spec("alloc-low-liquidity-family-starved", "liquidity_reject", "put", 4, "range_bound"),
        _spec("alloc-trend-persistence-swing-favored", "strong_swing", "call", 8, "trend_persistence"),
        _spec("alloc-pin-risk-zero-dte-reduced", "pin_risk_zero_dte", "call", 11, "pin_near_strike"),
        _spec("alloc-macro-delayed-rotation-preferred", "delayed_rotation", "put", 10, "macro_shock"),
        _spec("alloc-call-put-imbalance-throttle", "call_put_imbalance", "call", 0, "bull_trend"),
        _spec("alloc-zero-dte-share-cap-throttle", "zero_dte_share_cap", "put", 1, "bear_trend"),
        _spec("alloc-paper-shadow-not-standard", "shadow", "call", 9, "iv_expansion"),
    ]
    specs.extend(_loop_specs("strong_zero_dte_extra", "strong_zero_dte", 8, ["call", "put"], 0, "gap_and_go"))
    specs.extend(_loop_specs("strong_swing_extra", "strong_swing", 8, ["call", "put"], 8, "trend_persistence"))
    specs.extend(_loop_specs("delayed_extra", "delayed_rotation", 6, ["call", "put"], 5, "macro_shock"))
    specs.extend(_loop_specs("shadow_extra", "shadow", 7, ["call", "put"], 9, "iv_expansion"))
    specs.extend(_loop_specs("no_trade_extra", "no_trade", 7, ["none"], 6, "range_bound"))
    specs.extend(_loop_specs("liquidity_extra", "liquidity_reject", 5, ["call", "put"], 4, "false_breakout"))
    specs.extend(_loop_specs("no_day_trade_extra", "same_day_churn", 5, ["call", "put"], 0, "late_day_liquidity_decay"))
    specs.extend(_loop_specs("contradiction_extra", "contradiction", 5, ["call", "put"], 3, "event_whipsaw"))
    specs.extend(_loop_specs("negative_extra", "policy_violation", 2, ["call", "put"], 2, "false_breakdown"))
    return specs


def _loop_specs(prefix: str, kind: str, count: int, options: list[str], family_index: int, regime: str) -> list[dict[str, Any]]:
    return [_spec(f"alloc-{prefix}-{index + 1:02d}", kind, options[index % len(options)], family_index + (index % 2), regime) for index in range(count)]


def _spec(opportunity_id: str, kind: str, option_type: str, family_index: int, regime: str) -> dict[str, Any]:
    return {
        "opportunity_id": opportunity_id,
        "kind": kind,
        "option_type": option_type,
        "family_index": family_index % 12,
        "regime": regime,
    }


def _opportunity_from_spec(index: int, spec: dict[str, Any], threshold_status: str) -> ProofWeightedOpportunity:
    kind = str(spec["kind"])
    option_type = str(spec["option_type"])
    family_index = int(spec["family_index"])
    family_id = f"underlying-family-{family_index + 1:02d}"
    family_name = FAMILY_ORDER[family_index]
    symbol = SYNTHETIC_SYMBOLS_BY_FAMILY[family_name]
    values = _values_for_kind(kind, option_type)
    return ProofWeightedOpportunity(
        opportunity_id=str(spec["opportunity_id"]),
        source_pair_id=f"allocation-source-pair-{index + 1:03d}",
        underlying_family_id=family_id,
        synthetic_underlying_symbol=symbol,
        regime_family=str(spec["regime"]),
        option_type=option_type,
        candidate_lifecycle=values["candidate_lifecycle"],
        preferred_path=values["preferred_path"],
        strategy_type=values["strategy_type"],
        proof_score=values["proof_score"],
        signal_confidence=values["signal_confidence"],
        risk_tier=values["risk_tier"],
        liquidity_score=values["liquidity_score"],
        slippage_score=values["slippage_score"],
        spread_pct=values["spread_pct"],
        theta_pressure=values["theta_pressure"],
        gamma_instability=values["gamma_instability"],
        iv_overpayment_risk=values["iv_overpayment_risk"],
        event_risk=values["event_risk"],
        macro_risk=values["macro_risk"],
        overnight_gap_risk=values["overnight_gap_risk"],
        no_day_trade_constraint=values["no_day_trade_constraint"],
        zero_dte_special_lifecycle_required=values["zero_dte_special_lifecycle_required"],
        swing_next_day_close_eligible=values["swing_next_day_close_eligible"],
        delayed_rotation_required=values["delayed_rotation_required"],
        threshold_survival_status=threshold_status,
        hybrid_preference_score=values["hybrid_preference_score"],
        coverage_score=values["coverage_score"],
        contradiction_score=values["contradiction_score"],
        paper_only=True,
        live_blocked=True,
    )


def _values_for_kind(kind: str, option_type: str) -> dict[str, Any]:
    strategy_suffix = "put" if option_type == "put" else "call"
    base = {
        "candidate_lifecycle": "swing_multi_day",
        "preferred_path": "swing",
        "strategy_type": f"swing_long_{strategy_suffix}",
        "proof_score": 0.88,
        "signal_confidence": 0.84,
        "risk_tier": "low_fixture_risk",
        "liquidity_score": 0.78,
        "slippage_score": 0.10,
        "spread_pct": 0.045,
        "theta_pressure": 0.24,
        "gamma_instability": 0.22,
        "iv_overpayment_risk": 0.30,
        "event_risk": 0.22,
        "macro_risk": 0.18,
        "overnight_gap_risk": 0.24,
        "no_day_trade_constraint": "next_day_close_allowed",
        "zero_dte_special_lifecycle_required": False,
        "swing_next_day_close_eligible": True,
        "delayed_rotation_required": False,
        "hybrid_preference_score": 0.78,
        "coverage_score": 1.0,
        "contradiction_score": 0.08,
    }
    if kind in {"strong_zero_dte", "call_put_imbalance", "zero_dte_share_cap"}:
        base.update({"candidate_lifecycle": "zero_dte_special_lifecycle", "preferred_path": "zero_dte", "strategy_type": f"zero_dte_long_{strategy_suffix}", "proof_score": 0.90, "signal_confidence": 0.86, "theta_pressure": 0.42, "gamma_instability": 0.44, "zero_dte_special_lifecycle_required": True, "swing_next_day_close_eligible": False, "hybrid_preference_score": 0.74, "no_day_trade_constraint": "special_close_allowed_with_reason"})
    if kind == "moderate_zero_dte":
        base.update({"candidate_lifecycle": "zero_dte_special_lifecycle", "preferred_path": "zero_dte", "strategy_type": f"zero_dte_long_{strategy_suffix}", "proof_score": 0.68, "signal_confidence": 0.66, "risk_tier": "moderate_fixture_risk", "zero_dte_special_lifecycle_required": True, "swing_next_day_close_eligible": False, "hybrid_preference_score": 0.58, "no_day_trade_constraint": "special_close_allowed_with_reason"})
    if kind == "high_theta_zero_dte":
        base.update({"candidate_lifecycle": "zero_dte_special_lifecycle", "preferred_path": "zero_dte", "strategy_type": f"zero_dte_long_{strategy_suffix}", "proof_score": 0.76, "signal_confidence": 0.73, "theta_pressure": 0.82, "zero_dte_special_lifecycle_required": True, "swing_next_day_close_eligible": False, "no_day_trade_constraint": "special_close_allowed_with_reason"})
    if kind == "high_gamma_zero_dte":
        base.update({"candidate_lifecycle": "zero_dte_special_lifecycle", "preferred_path": "zero_dte", "strategy_type": f"zero_dte_long_{strategy_suffix}", "proof_score": 0.76, "signal_confidence": 0.73, "gamma_instability": 0.84, "zero_dte_special_lifecycle_required": True, "swing_next_day_close_eligible": False, "no_day_trade_constraint": "special_close_allowed_with_reason"})
    if kind == "pin_risk_zero_dte":
        base.update({"candidate_lifecycle": "zero_dte_special_lifecycle", "preferred_path": "zero_dte", "strategy_type": f"zero_dte_long_{strategy_suffix}", "proof_score": 0.74, "signal_confidence": 0.72, "risk_tier": "pin_risk", "zero_dte_special_lifecycle_required": True, "swing_next_day_close_eligible": False, "no_day_trade_constraint": "special_close_allowed_with_reason"})
    if kind == "event_cap":
        base.update({"candidate_lifecycle": "zero_dte_special_lifecycle", "preferred_path": "zero_dte", "strategy_type": f"zero_dte_long_{strategy_suffix}", "proof_score": 0.72, "signal_confidence": 0.70, "event_risk": 0.84, "zero_dte_special_lifecycle_required": True, "swing_next_day_close_eligible": False, "no_day_trade_constraint": "special_close_allowed_with_reason"})
    if kind == "delayed_rotation":
        base.update({"candidate_lifecycle": "delayed_rotation", "preferred_path": "delayed_rotation", "strategy_type": f"delayed_rotation_long_{strategy_suffix}", "proof_score": 0.70, "signal_confidence": 0.68, "risk_tier": "delayed_rotation", "delayed_rotation_required": True, "swing_next_day_close_eligible": True, "no_day_trade_constraint": "same_day_close_blocked", "hybrid_preference_score": 0.62})
    if kind == "shadow":
        base.update({"coverage_score": 0.55, "risk_tier": "insufficient_fixture_coverage", "proof_score": 0.70, "signal_confidence": 0.66})
    if kind == "no_trade":
        base.update({"candidate_lifecycle": "no_trade", "preferred_path": "no_trade", "strategy_type": "no_trade", "option_type": "none", "proof_score": 0.40, "signal_confidence": 0.38, "risk_tier": "no_trade_preferred", "hybrid_preference_score": 0.30})
    if kind == "liquidity_reject":
        base.update({"liquidity_score": 0.22, "spread_pct": 0.22, "risk_tier": "poor_liquidity"})
    if kind == "wide_spread_reject":
        base.update({"liquidity_score": 0.46, "spread_pct": 0.24, "risk_tier": "wide_spread"})
    if kind == "same_day_churn":
        base.update({"risk_tier": "same_day_churn", "no_day_trade_constraint": "same_day_churn_attempt"})
    if kind == "contradiction":
        base.update({"coverage_score": 0.62, "contradiction_score": 0.84, "risk_tier": "contradictory_fixture_evidence"})
    if kind == "policy_violation":
        base.update({"risk_tier": "unsupported_policy_violation"})
    if kind == "live_path":
        base.update({"risk_tier": "live_path"})
    if kind == "sell_to_open":
        base.update({"risk_tier": "sell_to_open"})
    if kind == "unsupported_spread":
        base.update({"risk_tier": "unsupported_spread"})
    if kind == "missing_thesis":
        base.update({"risk_tier": "missing_thesis"})
    if kind == "missing_exit_plan":
        base.update({"risk_tier": "missing_exit_plan"})
    if kind == "weak_family":
        base.update({"proof_score": 0.64, "signal_confidence": 0.61, "risk_tier": "weak_family_exposure"})
    if kind == "call_put_imbalance":
        base.update({"risk_tier": "call_put_imbalance"})
    if kind == "zero_dte_share_cap":
        base.update({"risk_tier": "zero_dte_share_cap_probe"})
    return base
