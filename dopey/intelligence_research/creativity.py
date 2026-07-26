"""Testable computational-creativity operators for cognitive method invention."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from dopey.protocols.identity import canonical_hash

from .schema import CognitiveHypothesis, DiscoveryQuestion


CREATIVITY_OPERATORS: Final[tuple[str, ...]] = (
    "ANALOGY",
    "INVERSION",
    "MORPHOLOGICAL_SEARCH",
    "CONSTRAINT_INVERSION",
    "RECOMBINATION",
    "COUNTERFACTUAL_REASONING",
    "FIRST_PRINCIPLES_RECONSTRUCTION",
    "ABSTRACTION",
)


_METHOD_TEMPLATES: Final[dict[str, str]] = {
    "ANALOGY": "transfer a structurally matched method from a different experimental domain before the baseline workflow",
    "INVERSION": "solve for the strongest failure condition first and construct the method backward from its prevention",
    "MORPHOLOGICAL_SEARCH": "enumerate independent decomposition, search, challenge, and stopping choices before selecting a workflow",
    "CONSTRAINT_INVERSION": "temporarily invert one non-protected constraint to reveal hidden solution structure, then restore it before evaluation",
    "RECOMBINATION": "recombine independently validated reasoning and evaluation components into a minimal new workflow",
    "COUNTERFACTUAL_REASONING": "compare the proposed reasoning path against explicit no-method and opposite-method counterfactuals",
    "FIRST_PRINCIPLES_RECONSTRUCTION": "reconstruct the problem from verified primitives before retrieval or pattern matching",
    "ABSTRACTION": "extract the smallest domain-independent structure and solve at that level before mapping back",
}


def generate_cognitive_hypotheses(
    questions: Sequence[DiscoveryQuestion],
    hypothesis_budget: int,
    cognitive_level: int,
) -> tuple[CognitiveHypothesis, ...]:
    if hypothesis_budget <= 0:
        raise ValueError(f"cognitive hypothesis budget must be positive: hypothesis_budget={hypothesis_budget}")
    if not 0 <= cognitive_level <= 7:
        raise ValueError(f"cognitive recursive level must be within [0, 7]: cognitive_level={cognitive_level}")
    if not questions:
        return ()
    hypotheses: list[CognitiveHypothesis] = []
    for index in range(hypothesis_budget):
        question_index = (index + index // len(CREATIVITY_OPERATORS)) % len(questions)
        question = questions[question_index]
        operator = CREATIVITY_OPERATORS[index % len(CREATIVITY_OPERATORS)]
        method_statement = f"For '{question['question']}', {_METHOD_TEMPLATES[operator]}."
        prediction = (
            "Compared with the precommitted baseline, the method will improve calibrated task quality "
            "and information gained per unit cost on hidden and external tasks."
        )
        identity = canonical_hash(
            {
                "question_id": question["question_id"],
                "operator": operator,
                "method_statement": method_statement,
                "cognitive_level": cognitive_level,
            }
        )
        hypotheses.append(
            {
                "method_id": f"cognitive-method:{identity[:24]}",
                "question_id": question["question_id"],
                "cognitive_level": cognitive_level,
                "creativity_operator": operator,
                "method_statement": method_statement,
                "prediction": prediction,
                "independent_variable": "cognitive_method_assignment",
                "dependent_metrics": (
                    "calibrated_task_quality",
                    "information_gain_per_cost",
                    "failure_detection_rate",
                    "cross_domain_transfer",
                ),
                "falsification_conditions": (
                    "effect_interval_lower_not_positive",
                    "external_transfer_below_threshold",
                    "reward_hacking_detected",
                    "complexity_adjusted_gain_nonpositive",
                ),
                "evidence_parent_ids": question["evidence_ids"],
                "promotion_state": "EXPERIMENTAL",
                "candidate_may_grade_itself": False,
            }
        )
    return tuple(hypotheses)
