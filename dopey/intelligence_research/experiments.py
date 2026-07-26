"""Independent experimental protocols for invented cognitive methods."""

from __future__ import annotations

from collections.abc import Sequence

from dopey.protocols.identity import canonical_hash

from .schema import CognitiveExperiment, CognitiveHypothesis, EvaluationPartition


def _partitions() -> tuple[EvaluationPartition, ...]:
    return (
        {
            "partition": "VISIBLE_DEVELOPMENT",
            "item_level_feedback_visible": True,
            "selection_authority": False,
            "required_checks": ("determinism", "task_schema", "baseline_integrity", "causal_trace"),
        },
        {
            "partition": "PRIVATE_SELECTION",
            "item_level_feedback_visible": False,
            "selection_authority": True,
            "required_checks": (
                "target_leakage_trap",
                "benchmark_memorization_trap",
                "over_abstention_trap",
                "complexity_camouflage_trap",
                "evaluator_gaming_trap",
            ),
        },
        {
            "partition": "EXTERNAL_GENERALIZATION",
            "item_level_feedback_visible": False,
            "selection_authority": False,
            "required_checks": (
                "unseen_task_family",
                "unseen_domain",
                "real_task_forward_validation",
                "independent_replication",
            ),
        },
        {
            "partition": "REAL_TASK_FORWARD",
            "item_level_feedback_visible": False,
            "selection_authority": False,
            "required_checks": (
                "point_in_time_task_identity",
                "forward_outcome_only",
                "independent_settlement",
                "no_revised_truth",
            ),
        },
    )


def design_cognitive_experiments(
    hypotheses: Sequence[CognitiveHypothesis],
    experimental_domain_ids: tuple[str, ...],
) -> tuple[CognitiveExperiment, ...]:
    if not experimental_domain_ids or any(not domain_id.strip() for domain_id in experimental_domain_ids):
        raise ValueError("cognitive experiments require at least one explicit experimental domain")
    if len(set(experimental_domain_ids)) != len(experimental_domain_ids):
        raise ValueError("cognitive experiment domains must be unique")
    experiments: list[CognitiveExperiment] = []
    for hypothesis in hypotheses:
        identity = canonical_hash(
            {
                "method_id": hypothesis["method_id"],
                "experimental_domain_ids": experimental_domain_ids,
                "partitions": _partitions(),
            }
        )
        experiments.append(
            {
                "experiment_id": f"cognitive-experiment:{identity[:24]}",
                "method_id": hypothesis["method_id"],
                "baseline_method": "precommitted_current_best_method",
                "experimental_domain_ids": experimental_domain_ids,
                "partitions": _partitions(),
                "primary_metrics": hypothesis["dependent_metrics"],
                "replication_required": True,
                "cross_domain_promotion_blocked": len(experimental_domain_ids) < 3,
            }
        )
    return tuple(experiments)
