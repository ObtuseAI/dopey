"""Typed scientific records for research on intelligence itself."""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


class KnowledgeSignalType(StrEnum):
    BOTTLENECK = "BOTTLENECK"
    CONTRADICTION = "CONTRADICTION"
    UNKNOWN = "UNKNOWN"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    CAPABILITY_GAP = "CAPABILITY_GAP"
    OPPORTUNITY = "OPPORTUNITY"


class CognitivePromotionState(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    QUARANTINED = "QUARANTINED"
    REPLAY_VALIDATED = "REPLAY_VALIDATED"
    PRIVATE_VALIDATED = "PRIVATE_VALIDATED"
    EXTERNAL_VALIDATED = "EXTERNAL_VALIDATED"
    REAL_TASK_VALIDATED = "REAL_TASK_VALIDATED"
    THEORY_CANDIDATE = "THEORY_CANDIDATE"
    GENERAL_LAW_CANDIDATE = "GENERAL_LAW_CANDIDATE"
    DEGRADED = "DEGRADED"
    RETIRED = "RETIRED"


class KnowledgeSignal(TypedDict):
    signal_id: str
    signal_type: KnowledgeSignalType
    domain_id: str
    statement: str
    severity: float
    novelty: float
    expected_reuse: float
    evidence_ids: tuple[str, ...]


class CognitiveKnowledgeState(TypedDict):
    state_id: str
    observed_at: str
    signals: tuple[KnowledgeSignal, ...]
    protected_constraints: tuple[str, ...]
    experimental_domain_ids: tuple[str, ...]


class DiscoveryQuestion(TypedDict):
    question_id: str
    source_signal_id: str
    signal_type: str
    domain_id: str
    question: str
    priority: float
    evidence_ids: tuple[str, ...]


class CognitiveHypothesis(TypedDict):
    method_id: str
    question_id: str
    cognitive_level: int
    creativity_operator: str
    method_statement: str
    prediction: str
    independent_variable: str
    dependent_metrics: tuple[str, ...]
    falsification_conditions: tuple[str, ...]
    evidence_parent_ids: tuple[str, ...]
    promotion_state: str
    candidate_may_grade_itself: bool


class EvaluationPartition(TypedDict):
    partition: str
    item_level_feedback_visible: bool
    selection_authority: bool
    required_checks: tuple[str, ...]


class CognitiveExperiment(TypedDict):
    experiment_id: str
    method_id: str
    baseline_method: str
    experimental_domain_ids: tuple[str, ...]
    partitions: tuple[EvaluationPartition, ...]
    primary_metrics: tuple[str, ...]
    replication_required: bool
    cross_domain_promotion_blocked: bool


class CognitivePartitionEvidence(TypedDict):
    partition: str
    sample_count: int
    domain_count: int
    replication_count: int
    effect_size: float
    effect_interval_lower: float
    calibration_improvement: float
    transfer_score: float
    efficiency_score: float
    complexity_score: float
    deterministic: bool
    evaluator_independent: bool


class CognitiveMethodEvidence(TypedDict):
    method_id: str
    source_discovery_cycle_hash: str
    source_task_store_content_hash: str
    promotion_metrics_source: str
    hidden_partition_metrics: dict[str, CognitivePartitionEvidence]
    visible_samples: int
    private_samples: int
    external_samples: int
    real_task_samples: int
    domain_count: int
    replication_count: int
    effect_size: float
    effect_interval_lower: float
    calibration_improvement: float
    transfer_score: float
    efficiency_score: float
    complexity_score: float
    deterministic: bool
    evaluator_independent: bool
    reward_hacking_detected: bool
    constitutional_violation: bool


class CognitiveMethodThresholds(TypedDict):
    threshold_version: str
    min_visible_samples: int
    min_private_samples: int
    min_external_samples: int
    min_real_task_samples: int
    min_domains: int
    min_replications: int
    min_effect_size: float
    min_transfer_score: float
    min_efficiency_score: float
    max_complexity_score: float


class CognitiveTaskCandidate(TypedDict):
    candidate_id: str
    support: float
    counterevidence: float
    reliability: float
    transfer: float
    novelty: float
    simplicity: float
    coverage: float
    constraint_safety: float
    falsifiability: float


class CognitiveBenchmarkTask(TypedDict):
    task_id: str
    domain_id: str
    partition: str
    task_family: str
    expected_candidate_id: str
    candidates: tuple[CognitiveTaskCandidate, ...]
    source_provenance: str
    evaluator_version: str


class CognitiveTaskStoreAudit(TypedDict):
    store_status: str
    task_count: int
    partition_counts: dict[str, int]
    task_store_hash: str
    task_store_content_hash: str
    task_store_semantic_hash: str
    visible_suite_hash: str
    semantic_fingerprint_count: int
    partition_fingerprint_hashes: dict[str, str]
    cross_partition_overlap_count: int
    evaluator_independent: bool
    activation_eligible: bool
    raw_answers_accessible_to_local_process: bool
    signature_verification_status: str
    os_isolation_status: str


class CognitiveTrialResult(TypedDict):
    trial_id: str
    experiment_id: str
    method_id: str
    task_id: str
    domain_id: str
    partition: str
    baseline_candidate_id: str
    challenger_candidate_id: str
    expected_candidate_id: str
    baseline_correct: bool
    challenger_correct: bool
    quality_delta: float
    calibration_delta: float
    cost_delta: float
    deterministic: bool
    evaluator_independent: bool


class BoundCognitiveTrialResult(CognitiveTrialResult):
    execution_trial_id: str
    source_discovery_cycle_hash: str
    source_task_store_content_hash: str
