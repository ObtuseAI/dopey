"""Typed vocabulary for autonomous threshold decisions."""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


class GateComparator(StrEnum):
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    EQUAL = "EQUAL"


class GateAction(StrEnum):
    CONTINUE = "CONTINUE"
    EXPAND_EVIDENCE = "EXPAND_EVIDENCE"
    ADD_ADVERSARY = "ADD_ADVERSARY"
    CHANGE_STRATEGY = "CHANGE_STRATEGY"
    REPLAY_HISTORY = "REPLAY_HISTORY"
    NARROW_SCOPE = "NARROW_SCOPE"
    SHADOW_ONLY = "SHADOW_ONLY"
    ABSTAIN = "ABSTAIN"
    QUARANTINE = "QUARANTINE"
    TERMINATE = "TERMINATE"
    RETIRE = "RETIRE"


class GateAuthority(StrEnum):
    AUTONOMOUS_RESEARCH_CONTROL = "AUTONOMOUS_RESEARCH_CONTROL"
    PROTECTED_EVALUATOR = "PROTECTED_EVALUATOR"
    OPERATOR_PROMOTION = "OPERATOR_PROMOTION"


class ThresholdRule(TypedDict):
    rule_id: str
    metric: str
    comparator: GateComparator
    threshold: float | bool | str
    protected_boundary: float | bool | str
    critical: bool
    source_ids: tuple[str, ...]


class GatePolicy(TypedDict):
    policy_id: str
    policy_version: str
    scope: str
    authority: GateAuthority
    pass_action: GateAction
    fail_action: GateAction
    missing_action: GateAction
    rules: tuple[ThresholdRule, ...]
    positive_promotion_allowed: bool
    execution_effect: str
    paper_only: bool
    live_blocked: bool


class GateRuleResult(TypedDict):
    rule_id: str
    metric: str
    comparator: str
    threshold: float | bool | str
    observed: object
    observed_available: bool
    passed: bool
    critical: bool
    source_ids: tuple[str, ...]


class GateDecision(TypedDict):
    artifact_type: str
    gate_version: str
    policy_id: str
    policy_version: str
    subject_id: str
    scope: str
    authority: str
    decision: str
    passed: bool
    missing_metrics: tuple[str, ...]
    failed_rules: tuple[str, ...]
    rule_results: tuple[GateRuleResult, ...]
    causal_parent_ids: tuple[str, ...]
    positive_promotion_allowed: bool
    readiness_effect: str
    execution_effect: str
    paper_only: bool
    live_blocked: bool
    decision_hash: str
