"""Exposure summaries for abstract paper allocation units."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .allocation_decision_models import PaperAllocationDecision
from .paper_risk_budget import PaperRiskBudget
from .proof_weighted_allocation_models import ProofWeightedOpportunity


def build_exposure_summary(
    opportunities: list[ProofWeightedOpportunity],
    decisions: list[PaperAllocationDecision],
    budget: PaperRiskBudget,
) -> dict[str, Any]:
    by_id = {opportunity.opportunity_id: opportunity for opportunity in opportunities}
    risk_by_strategy: dict[str, float] = defaultdict(float)
    risk_by_family: dict[str, float] = defaultdict(float)
    risk_by_regime: dict[str, float] = defaultdict(float)
    option_counts: Counter[str] = Counter()
    lifecycle_counts: Counter[str] = Counter()
    zero_dte_units = 0.0
    swing_units = 0.0
    for decision in decisions:
        opportunity = by_id[decision.opportunity_id]
        units = decision.paper_premium_risk_units
        risk_by_strategy[opportunity.strategy_type] += units
        risk_by_family[opportunity.underlying_family_id] += units
        risk_by_regime[opportunity.regime_family] += units
        option_counts[opportunity.option_type] += 1
        lifecycle_counts[opportunity.candidate_lifecycle] += 1
        if opportunity.strategy_type.startswith("zero_dte"):
            zero_dte_units += units
        if opportunity.strategy_type.startswith("swing"):
            swing_units += units
    total_units = sum(decision.paper_premium_risk_units for decision in decisions)
    zero_dte_share = round(zero_dte_units / total_units, 6) if total_units else 0.0
    return {
        "artifact_type": "allocation_exposure_summary",
        "total_paper_premium_risk_units": round(total_units, 6),
        "zero_dte_paper_premium_risk_units": round(zero_dte_units, 6),
        "swing_paper_premium_risk_units": round(swing_units, 6),
        "zero_dte_exposure_share": zero_dte_share,
        "zero_dte_share_cap": budget.max_zero_dte_paper_exposure_share,
        "zero_dte_share_status": "within_cap" if zero_dte_share <= budget.max_zero_dte_paper_exposure_share else "cap_pressure_recorded",
        "allocation_by_strategy_type": dict(sorted((key, round(value, 6)) for key, value in risk_by_strategy.items())),
        "allocation_by_underlying_family": dict(sorted((key, round(value, 6)) for key, value in risk_by_family.items())),
        "allocation_by_regime_family": dict(sorted((key, round(value, 6)) for key, value in risk_by_regime.items())),
        "allocation_by_option_type": dict(sorted(option_counts.items())),
        "allocation_by_lifecycle": dict(sorted(lifecycle_counts.items())),
        "call_put_balance_monitor": _call_put_balance(option_counts),
        "swing_zero_dte_balance_monitor": {"swing_units": round(swing_units, 6), "zero_dte_units": round(zero_dte_units, 6)},
        "paper_only": True,
        "live_blocked": True,
    }


def build_constraint_summary(decisions: list[PaperAllocationDecision]) -> dict[str, Any]:
    constraints = Counter(reason for decision in decisions for reason in decision.constraint_reason_codes)
    blocks = Counter(reason for decision in decisions for reason in decision.block_reason_codes)
    return {
        "artifact_type": "allocation_constraint_summary",
        "constraint_reason_distribution": dict(sorted(constraints.items())),
        "block_reason_distribution": dict(sorted(blocks.items())),
        "same_day_churn_allocation_allowed": False,
        "delayed_rotation_reserves_advisory_only": True,
        "paper_broker_override_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _call_put_balance(option_counts: Counter[str]) -> dict[str, Any]:
    calls = option_counts.get("call", 0)
    puts = option_counts.get("put", 0)
    total = calls + puts
    imbalance = abs(calls - puts) / total if total else 0.0
    return {
        "call_count": calls,
        "put_count": puts,
        "imbalance_ratio": round(imbalance, 6),
        "status": "balanced_or_monitored" if imbalance <= 0.20 else "imbalance_throttle_triggered",
    }
