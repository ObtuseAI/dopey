"""Executable, evidence-gated mutations for paper-research configuration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Final, TypedDict

from dopey.protocols.status_semantics import classify_operational_status

from .common import stable_hash


class ResearchMutationState(StrEnum):
    PENDING_SHADOW_EVIDENCE = "PENDING_SHADOW_EVIDENCE"
    SHADOW_APPROVED = "SHADOW_APPROVED"
    SHADOW_REJECTED = "SHADOW_REJECTED"


class ResearchMutationProposal(TypedDict):
    proposal_id: str
    source_lane_id: str
    source_status: str
    surface: str
    target: str
    baseline_value: int
    challenger_value: int
    primary_metric: str
    minimum_samples: int
    maximum_cost_ratio: float
    rollback_conditions: tuple[str, ...]
    protected_surface: bool
    paper_only: bool
    live_blocked: bool


class ResearchMutationEvidence(TypedDict):
    proposal_id: str
    sample_count: int
    effect_interval_lower: float
    cost_ratio: float
    evaluator_independent: bool
    deterministic: bool
    invariant_violations: tuple[str, ...]


class ResearchMutationDecision(TypedDict):
    proposal_id: str
    state: ResearchMutationState
    failed_checks: tuple[str, ...]
    target: str
    effective_value: int
    paper_only: bool
    live_blocked: bool


_TARGET_LIMITS: Final[dict[str, tuple[int, int]]] = {
    "autonomous_strategy_research.candidate_budget": (8, 48),
    "intelligence_discovery_research.hypothesis_budget": (8, 32),
}
_PROTECTED_TARGET_TOKENS: Final[tuple[str, ...]] = (
    "truth",
    "settlement",
    "verification",
    "authority",
    "permission",
    "execution",
    "broker",
    "credential",
    "live",
    "readiness_threshold",
)


def _proposal(
    source_lane_id: str,
    source_status: str,
    surface: str,
    target: str,
    baseline_value: int,
    challenger_value: int,
) -> ResearchMutationProposal:
    protected_surface = any(
        token in target.lower() for token in _PROTECTED_TARGET_TOKENS
    )
    if protected_surface:
        raise ValueError(
            f"research mutation targets a protected surface: target={target}"
        )
    minimum, maximum = _TARGET_LIMITS[target]
    if not minimum <= challenger_value <= maximum:
        raise ValueError(
            "research mutation value is outside its sealed range: "
            f"target={target}, value={challenger_value}, range=({minimum}, {maximum})"
        )
    body = {
        "source_lane_id": source_lane_id,
        "source_status": source_status,
        "surface": surface,
        "target": target,
        "baseline_value": baseline_value,
        "challenger_value": challenger_value,
        "primary_metric": "validated_evidence_per_compute_minute",
        "minimum_samples": 30,
        "maximum_cost_ratio": 1.25,
        "rollback_conditions": (
            "effect_interval_lower_not_positive",
            "cost_ratio_above_sealed_limit",
            "determinism_failure",
            "evaluator_independence_failure",
            "protected_invariant_violation",
        ),
        "protected_surface": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {
        "proposal_id": f"research-mutation:{stable_hash(body)[:24]}",
        **body,
    }


def propose_research_mutations(
    lane_statuses: Mapping[str, Any],
) -> tuple[ResearchMutationProposal, ...]:
    proposal_specs: tuple[tuple[str, str, str, int, int], ...] = (
        (
            "autonomous_strategy_research",
            "shadow_candidate_generation",
            "autonomous_strategy_research.candidate_budget",
            24,
            16,
        ),
        (
            "intelligence_discovery_research",
            "hypothesis_generation",
            "intelligence_discovery_research.hypothesis_budget",
            16,
            8,
        ),
    )
    proposals: list[ResearchMutationProposal] = []
    for lane_id, surface, target, baseline, challenger in proposal_specs:
        raw_record = lane_statuses.get(lane_id)
        if not isinstance(raw_record, Mapping):
            continue
        raw_status = str(raw_record.get("status", "unknown"))
        assessment = classify_operational_status(raw_status)
        if not assessment["failure_signal"]:
            continue
        proposals.append(
            _proposal(
                lane_id,
                raw_status,
                surface,
                target,
                baseline,
                challenger,
            )
        )
    return tuple(proposals)


def evaluate_research_mutation(
    proposal: ResearchMutationProposal,
    evidence: ResearchMutationEvidence | None,
) -> ResearchMutationDecision:
    failed_checks: list[str] = []
    if evidence is None:
        state = ResearchMutationState.PENDING_SHADOW_EVIDENCE
    else:
        if evidence["proposal_id"] != proposal["proposal_id"]:
            raise ValueError(
                "research mutation evidence identity mismatch: "
                f"expected={proposal['proposal_id']}, actual={evidence['proposal_id']}"
            )
        if evidence["sample_count"] < proposal["minimum_samples"]:
            failed_checks.append("minimum_samples")
        if evidence["effect_interval_lower"] <= 0.0:
            failed_checks.append("effect_interval_lower")
        if evidence["cost_ratio"] > proposal["maximum_cost_ratio"]:
            failed_checks.append("maximum_cost_ratio")
        if evidence["evaluator_independent"] is not True:
            failed_checks.append("evaluator_independent")
        if evidence["deterministic"] is not True:
            failed_checks.append("deterministic")
        if evidence["invariant_violations"]:
            failed_checks.append("protected_invariants")
        state = (
            ResearchMutationState.SHADOW_APPROVED
            if not failed_checks
            else ResearchMutationState.SHADOW_REJECTED
        )
    return {
        "proposal_id": proposal["proposal_id"],
        "state": state,
        "failed_checks": tuple(failed_checks),
        "target": proposal["target"],
        "effective_value": (
            proposal["challenger_value"]
            if state is ResearchMutationState.SHADOW_APPROVED
            else proposal["baseline_value"]
        ),
        "paper_only": True,
        "live_blocked": True,
    }


def activated_research_overrides(
    decisions: Sequence[ResearchMutationDecision],
) -> dict[str, int]:
    return {
        decision["target"]: decision["effective_value"]
        for decision in decisions
        if decision["state"] is ResearchMutationState.SHADOW_APPROVED
    }


def load_research_overrides(policy: Mapping[str, Any]) -> dict[str, int]:
    if (
        policy.get("policy_status") != "active_threshold_gated"
        or policy.get("paper_only") is not True
        or policy.get("live_blocked") is not True
        or policy.get("evidence_thresholds_lowered") is not False
    ):
        return {}
    raw_overrides = policy.get("research_overrides")
    if not isinstance(raw_overrides, Mapping):
        return {}
    overrides: dict[str, int] = {}
    for raw_target, raw_value in raw_overrides.items():
        target = str(raw_target)
        if target not in _TARGET_LIMITS:
            raise ValueError(
                f"active research policy contains an unknown target: target={target}"
            )
        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            raise TypeError(
                f"active research policy value must be an integer: target={target}"
            )
        minimum, maximum = _TARGET_LIMITS[target]
        if not minimum <= raw_value <= maximum:
            raise ValueError(
                "active research policy value is outside its sealed range: "
                f"target={target}, value={raw_value}, range=({minimum}, {maximum})"
            )
        overrides[target] = raw_value
    return overrides
