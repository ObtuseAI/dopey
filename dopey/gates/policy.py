"""Sealed default policies for autonomous research control."""

from __future__ import annotations

from typing import Final

from .schema import GateAction, GateAuthority, GateComparator, GatePolicy


AUTONOMOUS_GATE_POLICIES: Final[tuple[GatePolicy, ...]] = (
    {
        "policy_id": "data_admission",
        "policy_version": "dopey-threshold-fabric-v1",
        "scope": "point_in_time_evidence",
        "authority": GateAuthority.PROTECTED_EVALUATOR,
        "pass_action": GateAction.CONTINUE,
        "fail_action": GateAction.QUARANTINE,
        "missing_action": GateAction.QUARANTINE,
        "rules": (
            {"rule_id": "point_in_time_complete", "metric": "point_in_time_complete", "comparator": GateComparator.EQUAL, "threshold": True, "protected_boundary": True, "critical": True, "source_ids": ("dopey-constitution",)},
            {"rule_id": "provenance_complete", "metric": "provenance_complete", "comparator": GateComparator.EQUAL, "threshold": True, "protected_boundary": True, "critical": True, "source_ids": ("dopey-constitution",)},
            {"rule_id": "schema_valid", "metric": "schema_valid", "comparator": GateComparator.EQUAL, "threshold": True, "protected_boundary": True, "critical": True, "source_ids": ("dopey-constitution",)},
            {"rule_id": "freshness", "metric": "freshness", "comparator": GateComparator.GREATER_THAN_OR_EQUAL, "threshold": 0.95, "protected_boundary": 0.95, "critical": True, "source_ids": ("dopey-constitution",)},
            {"rule_id": "missing_fraction", "metric": "missing_fraction", "comparator": GateComparator.LESS_THAN_OR_EQUAL, "threshold": 0.05, "protected_boundary": 0.05, "critical": True, "source_ids": ("dopey-constitution",)},
        ),
        "positive_promotion_allowed": False,
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    },
    {
        "policy_id": "experiment_admission",
        "policy_version": "dopey-threshold-fabric-v1",
        "scope": "research_candidate",
        "authority": GateAuthority.PROTECTED_EVALUATOR,
        "pass_action": GateAction.SHADOW_ONLY,
        "fail_action": GateAction.QUARANTINE,
        "missing_action": GateAction.EXPAND_EVIDENCE,
        "rules": (
            {"rule_id": "leakage_absent", "metric": "leakage_detected", "comparator": GateComparator.EQUAL, "threshold": False, "protected_boundary": False, "critical": True, "source_ids": ("pbo", "deflated-sharpe")},
            {"rule_id": "revised_data_absent", "metric": "revised_data_contamination", "comparator": GateComparator.EQUAL, "threshold": False, "protected_boundary": False, "critical": True, "source_ids": ("dopey-constitution",)},
            {"rule_id": "candidate_self_grade_absent", "metric": "candidate_may_grade_itself", "comparator": GateComparator.EQUAL, "threshold": False, "protected_boundary": False, "critical": True, "source_ids": ("dopey-constitution",)},
            {"rule_id": "interpretable", "metric": "interpretable", "comparator": GateComparator.EQUAL, "threshold": True, "protected_boundary": True, "critical": True, "source_ids": ("alphaforge", "alphaformer")},
            {"rule_id": "complexity", "metric": "complexity_score", "comparator": GateComparator.LESS_THAN_OR_EQUAL, "threshold": 0.35, "protected_boundary": 0.35, "critical": True, "source_ids": ("alphaforge", "pbo")},
        ),
        "positive_promotion_allowed": False,
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    },
    {
        "policy_id": "research_continuation",
        "policy_version": "dopey-threshold-fabric-v1",
        "scope": "marginal_research_utility",
        "authority": GateAuthority.AUTONOMOUS_RESEARCH_CONTROL,
        "pass_action": GateAction.CONTINUE,
        "fail_action": GateAction.TERMINATE,
        "missing_action": GateAction.NARROW_SCOPE,
        "rules": (
            {"rule_id": "information_gain", "metric": "information_gain", "comparator": GateComparator.GREATER_THAN_OR_EQUAL, "threshold": 0.05, "protected_boundary": 0.05, "critical": True, "source_ids": ("rd-agent-quant",)},
            {"rule_id": "duplication", "metric": "duplication_score", "comparator": GateComparator.LESS_THAN_OR_EQUAL, "threshold": 0.35, "protected_boundary": 0.35, "critical": True, "source_ids": ("alphaforge", "autoalpha")},
            {"rule_id": "resource_pressure", "metric": "resource_pressure", "comparator": GateComparator.LESS_THAN_OR_EQUAL, "threshold": 0.85, "protected_boundary": 0.85, "critical": True, "source_ids": ("dopey-metabolism",)},
        ),
        "positive_promotion_allowed": False,
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    },
    {
        "policy_id": "forward_recording",
        "policy_version": "dopey-threshold-fabric-v1",
        "scope": "forward_prediction_control",
        "authority": GateAuthority.PROTECTED_EVALUATOR,
        "pass_action": GateAction.SHADOW_ONLY,
        "fail_action": GateAction.ABSTAIN,
        "missing_action": GateAction.EXPAND_EVIDENCE,
        "rules": (
            {"rule_id": "point_in_time_complete", "metric": "point_in_time_complete", "comparator": GateComparator.EQUAL, "threshold": True, "protected_boundary": True, "critical": True, "source_ids": ("dopey-constitution",)},
            {"rule_id": "evidence_complete", "metric": "evidence_completeness", "comparator": GateComparator.GREATER_THAN_OR_EQUAL, "threshold": 0.60, "protected_boundary": 0.60, "critical": True, "source_ids": ("conformal-risk-control",)},
            {"rule_id": "regime_familiarity", "metric": "regime_familiarity", "comparator": GateComparator.GREATER_THAN_OR_EQUAL, "threshold": 0.40, "protected_boundary": 0.40, "critical": True, "source_ids": ("adaptive-conformal-risk-control",)},
            {"rule_id": "calibration_quality", "metric": "calibration_quality", "comparator": GateComparator.GREATER_THAN_OR_EQUAL, "threshold": 0.50, "protected_boundary": 0.50, "critical": True, "source_ids": ("confidence-sequences",)},
        ),
        "positive_promotion_allowed": False,
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    },
    {
        "policy_id": "settlement_admission",
        "policy_version": "dopey-threshold-fabric-v1",
        "scope": "forward_truth_settlement",
        "authority": GateAuthority.PROTECTED_EVALUATOR,
        "pass_action": GateAction.CONTINUE,
        "fail_action": GateAction.QUARANTINE,
        "missing_action": GateAction.EXPAND_EVIDENCE,
        "rules": (
            {"rule_id": "minimum_horizon_reached", "metric": "minimum_horizon_reached", "comparator": GateComparator.EQUAL, "threshold": True, "protected_boundary": True, "critical": True, "source_ids": ("dopey-settlement-law",)},
            {"rule_id": "verified_terminal_price", "metric": "verified_terminal_price", "comparator": GateComparator.EQUAL, "threshold": True, "protected_boundary": True, "critical": True, "source_ids": ("dopey-settlement-law",)},
            {"rule_id": "early_grading_absent", "metric": "early_grading_performed", "comparator": GateComparator.EQUAL, "threshold": False, "protected_boundary": False, "critical": True, "source_ids": ("dopey-settlement-law",)},
        ),
        "positive_promotion_allowed": False,
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    },
)


def policy_by_id(policy_id: str) -> GatePolicy:
    matches = tuple(policy for policy in AUTONOMOUS_GATE_POLICIES if policy["policy_id"] == policy_id)
    if len(matches) != 1:
        raise ValueError(f"autonomous gate policy must resolve exactly once: policy_id={policy_id}, matches={len(matches)}")
    return matches[0]
