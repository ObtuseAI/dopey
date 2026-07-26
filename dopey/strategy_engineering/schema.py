"""Typed artifacts for governed strategy engineering."""

from __future__ import annotations

from typing import TypedDict


class PrimitiveSpec(TypedDict):
    primitive_id: str
    family: str
    expression: str
    output_domain: str
    leakage_risk: str
    source_ids: tuple[str, ...]


class MechanismSpec(TypedDict):
    mechanism_id: str
    thesis: str
    primitive_ids: tuple[str, ...]
    regime_guards: tuple[str, ...]
    failure_conditions: tuple[str, ...]
    horizons: tuple[int, ...]
    source_ids: tuple[str, ...]


class ReverseCase(TypedDict):
    case_id: str
    prediction_id: str
    symbol: str
    era: str
    regime: str
    feature_values: dict[str, float]
    dominant_correct: float
    contested_truth: bool
    evidence_ids: tuple[str, ...]
    point_in_time_proof_id: str


class StrategyCandidate(TypedDict):
    candidate_id: str
    mechanism_id: str
    horizon_trading_days: int
    primitive_ids: tuple[str, ...]
    research_expression: str
    regime_guards: tuple[str, ...]
    abstention_conditions: tuple[str, ...]
    failure_conditions: tuple[str, ...]
    complexity_score: float
    source_ids: tuple[str, ...]
    evidence_parent_ids: tuple[str, ...]
    factor_program: dict[str, object]
    activation_state: str
    candidate_may_grade_itself: bool
    positive_promotion_allowed: bool
    order_construction_allowed: bool
    paper_only: bool
    live_blocked: bool


class EvaluationManifest(TypedDict):
    candidate_id: str
    partition_sequence: tuple[str, ...]
    required_checks: tuple[str, ...]
    sequential_inference: tuple[str, ...]
    minimum_independent_evidence_groups: int
    required_counterfactuals: tuple[str, ...]
    institutional_council_required: bool
    promotion_authority: str
    candidate_may_grade_itself: bool
    paper_only: bool
    live_blocked: bool


class SourceRecord(TypedDict):
    source_id: str
    title: str
    url: str
    source_type: str
    adopted_capability: str
    evidence_restriction: str


class InstitutionalSourceRecord(SourceRecord):
    published_at: str


class DoctrineSpec(TypedDict):
    doctrine_id: str
    lens_id: str
    principle: str
    applicable_instruments: tuple[str, ...]
    required_checks: tuple[str, ...]
    failure_modes: tuple[str, ...]
    source_ids: tuple[str, ...]
    prohibited_inferences: tuple[str, ...]


class ThesisEscrow(TypedDict):
    candidate_id: str
    instrument_class: str
    economic_mechanism: str
    base_rate_evidence_id: str
    opposed_thesis_id: str
    kill_condition_ids: tuple[str, ...]
    cost_model_id: str
    capacity_model_id: str
    forward_plan_id: str
    counterfactual_ids: tuple[str, ...]
    required_lens_ids: tuple[str, ...]
    required_doctrine_ids: tuple[str, ...]


class CouncilObservation(TypedDict):
    observation_id: str
    lens_id: str
    doctrine_ids: tuple[str, ...]
    evidence_family: str
    independence_group: str
    direction: float
    data_quality: float
    calibration_quality: float
    uncertainty: float
    implementation_relevance: float
    evidence_ids: tuple[str, ...]
    falsifier_id: str


class ResearchGap(TypedDict):
    gap_id: str
    domain_id: str
    statement: str
    current_status: str
    dependency_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    information_gain: float
    falsifiability: float
    uncertainty_reduction: float
    orthogonality: float
    implementation_readiness: float
    edge_relevance: float
    safety_relevance: float
    reuse_potential: float
    selection_risk: float
    evaluation_cost: float
    max_budget_units: int
