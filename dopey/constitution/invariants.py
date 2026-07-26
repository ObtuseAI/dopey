"""Sealed constitutional invariants for every vNext component."""

from __future__ import annotations

from typing import Final


CONSTITUTION_VERSION: Final[str] = "dopey-constitution-v3"

PERMANENT_INVARIANTS: Final[tuple[str, ...]] = (
    "no_broker_order_authority",
    "no_order_construction_tools",
    "no_research_agent_credential_access",
    "simulation_is_not_realized_evidence",
    "backtest_is_not_forward_proof",
    "model_agreement_is_not_readiness",
    "optimizer_cannot_tune_its_judge",
    "truth_provenance_execution_and_holdout_rules_are_protected",
    "every_prediction_requires_settlement",
    "live_source_promotion_requires_operator_control",
    "every_evidence_item_requires_time_provenance_schema_and_identity",
    "confidence_requires_calibration_evidence",
    "agents_cannot_expand_permissions",
    "qualified_research_activation_is_autonomous_and_threshold_gated",
    "symbol_strategy_and_symbol_strategy_pair_gates_are_all_required",
    "candidate_cannot_grade_or_activate_itself",
    "research_activation_cannot_change_readiness_or_execution_authority",
    "cognitive_improvement_cannot_mutate_truth_verification_authority_or_permissions",
    "cognitive_methods_require_independent_cross_domain_replication",
    "theories_require_falsifiable_conditions_and_evidence_lineage",
)

PROTECTED_SURFACES: Final[frozenset[str]] = frozenset(
    {
        "constitution",
        "truth",
        "settlement",
        "provenance",
        "execution_seal",
        "readiness_gate",
        "held_out_evaluation",
        "autonomous_promotion_thresholds",
        "promotion_evaluator_independence",
        "cognitive_method_thresholds",
        "cognitive_evaluator_independence",
        "credential_restrictions",
        "protected_roots",
    }
)

EVOLVABLE_SURFACES: Final[frozenset[str]] = frozenset(
    {
        "agent_prompts",
        "agent_composition",
        "research_ordering",
        "technical_composites",
        "regime_strategies",
        "evidence_budgets",
        "model_selection",
        "stopping_policies",
        "disagreement_resolution",
        "calibration_models",
        "data_lane_priorities",
        "morphology_rules",
        "world_model_update_policies",
        "strategy_definitions",
        "strategy_invention_operators",
        "strategy_lineage_allocation",
        "reasoning_methods",
        "research_methods",
        "creativity_operators",
        "planning_methods",
        "problem_decomposition_methods",
        "memory_policies",
        "cognitive_agent_organizations",
        "cognitive_strategy_selection",
    }
)
