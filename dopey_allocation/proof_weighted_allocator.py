"""Proof-weighted paper allocation engine."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .allocation_decision_models import PaperAllocationDecision
from .exposure_controls import build_constraint_summary, build_exposure_summary
from .paper_allocation_models import PaperAllocationPlan, paper_allocation_plan_hash
from .paper_allocation_policy import decide_paper_allocation, default_paper_allocation_policy
from .paper_risk_budget import PaperRiskBudget, default_paper_risk_budget
from .proof_evidence_aggregator import aggregate_proof_evidence
from .proof_weighted_allocation_models import ProofWeightedOpportunity


def build_proof_weighted_allocation_bundle() -> dict[str, Any]:
    evidence = aggregate_proof_evidence()
    opportunities = evidence["opportunities"]
    policy = default_paper_allocation_policy()
    budget = default_paper_risk_budget()
    decisions = [decide_paper_allocation(opportunity, policy, budget) for opportunity in opportunities]
    exposure_summary = build_exposure_summary(opportunities, decisions, budget)
    constraint_summary = build_constraint_summary(decisions)
    plan = build_paper_allocation_plan(evidence["source_run_ids"], opportunities, decisions, exposure_summary, constraint_summary, evidence["proof_summary"])
    proof_records = build_allocation_proof_records(opportunities, decisions, exposure_summary)
    return {
        "opportunities": opportunities,
        "policy": policy,
        "budget": budget,
        "decisions": decisions,
        "plan": plan,
        "rejections": [decision for decision in decisions if decision.decision.startswith("reject_")],
        "watchlist": [decision for decision in decisions if decision.decision in {"watchlist_only", "needs_more_fixture_coverage", "allocate_paper_shadow_only", "reserve_for_delayed_rotation"}],
        "exposure_summary": exposure_summary,
        "constraint_summary": constraint_summary,
        "proof_records": proof_records,
        "evidence": evidence,
    }


def build_paper_allocation_plan(
    source_run_ids: list[str],
    opportunities: list[ProofWeightedOpportunity],
    decisions: list[PaperAllocationDecision],
    exposure_summary: dict[str, Any],
    constraint_summary: dict[str, Any],
    proof_summary: dict[str, Any],
) -> PaperAllocationPlan:
    decision_counts = Counter(decision.decision for decision in decisions)
    allocated = [decision for decision in decisions if decision.decision == "allocate_paper"]
    throttled = [decision for decision in decisions if decision.decision == "allocate_paper_throttled"]
    shadow = [decision for decision in decisions if decision.decision == "allocate_paper_shadow_only"]
    delayed = [decision for decision in decisions if decision.decision == "reserve_for_delayed_rotation"]
    watchlist = [decision for decision in decisions if decision.decision in {"watchlist_only", "needs_more_fixture_coverage"}]
    rejected = [decision for decision in decisions if decision.decision.startswith("reject_")]
    plan_seed = PaperAllocationPlan(
        plan_id="dopey-proof-weighted-paper-allocation-plan-v1",
        source_run_ids=source_run_ids,
        opportunity_count=len(opportunities),
        allocated_count=len(allocated),
        throttled_count=len(throttled),
        shadow_only_count=len(shadow),
        delayed_rotation_count=len(delayed),
        watchlist_count=len(watchlist),
        rejected_count=len(rejected),
        total_paper_attention_weight=round(sum(decision.paper_attention_weight for decision in decisions), 6),
        total_paper_premium_risk_units=round(sum(decision.paper_premium_risk_units for decision in decisions), 6),
        allocation_by_strategy_type=exposure_summary["allocation_by_strategy_type"],
        allocation_by_underlying_family=exposure_summary["allocation_by_underlying_family"],
        allocation_by_regime_family=exposure_summary["allocation_by_regime_family"],
        allocation_by_option_type={key: float(value) for key, value in exposure_summary["allocation_by_option_type"].items()},
        allocation_by_lifecycle={key: float(value) for key, value in exposure_summary["allocation_by_lifecycle"].items()},
        constraint_summary={**constraint_summary, "decision_distribution": dict(sorted(decision_counts.items()))},
        risk_summary=exposure_summary,
        proof_summary=proof_summary,
        paper_only=True,
        live_blocked=True,
        plan_hash="",
    )
    return PaperAllocationPlan(**{**plan_seed.to_dict(), "plan_hash": paper_allocation_plan_hash(plan_seed)})


def build_allocation_proof_records(
    opportunities: list[ProofWeightedOpportunity],
    decisions: list[PaperAllocationDecision],
    exposure_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    opportunity_by_id = {opportunity.opportunity_id: opportunity for opportunity in opportunities}
    records: list[dict[str, Any]] = []
    for decision in decisions:
        opportunity = opportunity_by_id[decision.opportunity_id]
        record = {
            "artifact_type": "allocation_proof",
            "allocation_id": decision.allocation_id,
            "opportunity_id": opportunity.opportunity_id,
            "strategy_type": opportunity.strategy_type,
            "underlying_family": opportunity.underlying_family_id,
            "regime_family": opportunity.regime_family,
            "option_type": opportunity.option_type,
            "preferred_path": opportunity.preferred_path,
            "decision": decision.decision,
            "allocation_tier": decision.allocation_tier,
            "paper_attention_weight": decision.paper_attention_weight,
            "paper_premium_risk_units": decision.paper_premium_risk_units,
            "max_paper_contract_units": decision.max_paper_contract_units,
            "reason_codes": {
                "block": decision.block_reason_codes,
                "proof": decision.proof_reason_codes,
                "constraint": decision.constraint_reason_codes,
            },
            "exposure_effects": {
                "zero_dte_exposure_share": exposure_summary["zero_dte_exposure_share"],
                "strategy_units": exposure_summary["allocation_by_strategy_type"].get(opportunity.strategy_type, 0.0),
            },
            "constraint_checks": {
                "same_day_churn_allocation_allowed": False,
                "delayed_rotation_advisory_only": opportunity.delayed_rotation_required,
                "paper_broker_override_allowed": False,
                "paper_broker_role": "policy_executor_not_allocator",
                "account_ledger_context_recorded": True,
                "rotation_planner_priority_recorded": True,
            },
            "safety_status": "paper_only_live_blocked",
            "evidence_hash": reproducibility_hash(opportunity.to_dict()),
            "decision_hash": decision.decision_hash,
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
        }
        record["reproducibility_hash"] = reproducibility_hash(record)
        records.append(record)
    return records
