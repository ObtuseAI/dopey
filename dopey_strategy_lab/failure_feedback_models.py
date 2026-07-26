"""Typed feedback models for deterministic DOPEY failure-mode optimization."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


FAILURE_FEEDBACK_MODEL_VERSION = "dopey-failure-feedback-model-v1"


@dataclass(frozen=True)
class FailureModeAggregate:
    failure_mode_id: str
    strategy_family: str
    structure_type: str
    regime_tag: str
    pattern_type: str
    greek_risk_verdict: str
    iv_context: str
    liquidity_verdict: str
    slippage_verdict: str
    overfit_level: str
    mutation_type: str
    failure_category: str
    recurrence_count: int
    evidence_score: float
    severity: str
    severity_score: float
    affected_strategy_ids: list[str] = field(default_factory=list)
    mitigation_hints: list[str] = field(default_factory=list)
    constraint_updates: list[str] = field(default_factory=list)
    version: str = FAILURE_FEEDBACK_MODEL_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["affected_strategy_ids"] = sorted(self.affected_strategy_ids)
        data["mitigation_hints"] = sorted(self.mitigation_hints)
        data["constraint_updates"] = sorted(self.constraint_updates)
        return data


@dataclass(frozen=True)
class RegimeFailureProfile:
    strategy_family: str
    regime_tag: str
    recurrence_count: int
    failure_mode_ids: list[str]
    failure_categories: list[str]
    severity_score: float
    version: str = FAILURE_FEEDBACK_MODEL_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["failure_mode_ids"] = sorted(self.failure_mode_ids)
        data["failure_categories"] = sorted(self.failure_categories)
        return data


@dataclass(frozen=True)
class FamilyFailureProfile:
    strategy_family: str
    total_failure_modes: int
    total_recurrence_count: int
    top_failure_modes: list[str]
    worst_regimes: list[str]
    failure_categories: list[str]
    structure_types: list[str]
    greek_risk_verdicts: list[str]
    liquidity_verdicts: list[str]
    slippage_verdicts: list[str]
    overfit_level: str
    recommendation_pressure: dict[str, float]
    blocked_mutation_types: list[str] = field(default_factory=list)
    version: str = FAILURE_FEEDBACK_MODEL_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["top_failure_modes"] = list(self.top_failure_modes)
        data["worst_regimes"] = list(self.worst_regimes)
        data["failure_categories"] = sorted(self.failure_categories)
        data["structure_types"] = sorted(self.structure_types)
        data["greek_risk_verdicts"] = sorted(self.greek_risk_verdicts)
        data["liquidity_verdicts"] = sorted(self.liquidity_verdicts)
        data["slippage_verdicts"] = sorted(self.slippage_verdicts)
        data["blocked_mutation_types"] = sorted(self.blocked_mutation_types)
        data["recommendation_pressure"] = {
            key: self.recommendation_pressure[key]
            for key in sorted(self.recommendation_pressure)
        }
        return data


@dataclass(frozen=True)
class ConstraintTuningRecommendation:
    recommendation_id: str
    strategy_family: str
    failure_mode_id: str
    tuning_key: str
    recommendation: str
    bounded_action: str
    target_scope: str
    replay_only: bool
    advisory: bool
    safety_rules: list[str]
    rationale: str
    version: str = FAILURE_FEEDBACK_MODEL_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["safety_rules"] = sorted(self.safety_rules)
        return data


@dataclass(frozen=True)
class FailureFeedbackDecision:
    decision_id: str
    strategy_family: str
    recommendation_ids: list[str]
    candidate_strategy_id: str
    status: str
    score_delta: float
    overfit_delta: int
    failure_regression_delta: float
    reasons: list[str]
    version: str = FAILURE_FEEDBACK_MODEL_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["recommendation_ids"] = sorted(self.recommendation_ids)
        data["reasons"] = sorted(self.reasons)
        return data


@dataclass(frozen=True)
class FeedbackOptimizerResult:
    feedback_run_id: str
    optimizer_status: str
    families_analyzed: list[str]
    failure_modes_loaded: int
    recommendations_generated: int
    recommendations_accepted: int
    recommendations_rejected: int
    feedback_mutations_generated: int
    feedback_mutations_valid: int
    best_previous_mutation: str
    best_feedback_mutation: str
    score_delta: float
    overfit_delta: int
    live_blocked: bool
    feedback_registry_path: str
    proof_record_path: str
    reproducibility_hash: str
    safety_state: dict
    family_failure_profiles: list[dict]
    regime_failure_profiles: list[dict]
    recommendations: list[dict]
    decisions: list[dict]
    comparison: dict
    version: str = FAILURE_FEEDBACK_MODEL_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["families_analyzed"] = sorted(self.families_analyzed)
        return data
