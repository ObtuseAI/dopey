"""Deterministic matched baseline/challenger execution for cognitive methods."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Literal, TypedDict

from dopey.protocols.identity import canonical_hash

from .schema import (
    CognitiveBenchmarkTask,
    CognitiveExperiment,
    CognitiveHypothesis,
    CognitiveTaskCandidate,
    CognitiveTrialResult,
)
from .task_store import COGNITIVE_EVALUATOR_VERSION


_BASELINE_WEIGHTS: Final[dict[str, float]] = {
    "support": 0.22,
    "counterevidence": -0.20,
    "reliability": 0.20,
    "transfer": 0.08,
    "novelty": 0.04,
    "simplicity": 0.08,
    "coverage": 0.07,
    "constraint_safety": 0.07,
    "falsifiability": 0.04,
}
_OPERATOR_EMPHASIS: Final[dict[str, tuple[str, ...]]] = {
    "ANALOGY": ("transfer",),
    "INVERSION": ("counterevidence",),
    "MORPHOLOGICAL_SEARCH": ("coverage",),
    "CONSTRAINT_INVERSION": ("constraint_safety",),
    "RECOMBINATION": ("support", "coverage"),
    "COUNTERFACTUAL_REASONING": ("falsifiability",),
    "FIRST_PRINCIPLES_RECONSTRUCTION": ("reliability",),
    "ABSTRACTION": ("simplicity",),
}
_OPERATOR_COST: Final[dict[str, float]] = {
    "ANALOGY": 0.18,
    "INVERSION": 0.14,
    "MORPHOLOGICAL_SEARCH": 0.30,
    "CONSTRAINT_INVERSION": 0.22,
    "RECOMBINATION": 0.26,
    "COUNTERFACTUAL_REASONING": 0.24,
    "FIRST_PRINCIPLES_RECONSTRUCTION": 0.20,
    "ABSTRACTION": 0.12,
}


class CognitivePolicyNode(TypedDict):
    operation: Literal[
        "BASELINE_PRIOR",
        "EMPHASIZE",
        "INVERT_AND_EMPHASIZE",
    ]
    feature: str
    weight: float


class CognitiveMethodPolicy(TypedDict):
    policy_id: str
    method_id: str
    operator: str
    nodes: tuple[CognitivePolicyNode, ...]


def compile_cognitive_method_policy(
    hypothesis: CognitiveHypothesis,
) -> CognitiveMethodPolicy:
    operator = hypothesis["creativity_operator"]
    features = _OPERATOR_EMPHASIS.get(operator)
    if features is None:
        raise ValueError(
            f"unsupported cognitive creativity operator: operator={operator}"
        )
    specialized_weight = 0.82 / float(len(features))
    specialized_nodes = tuple(
        CognitivePolicyNode(
            operation=(
                "INVERT_AND_EMPHASIZE"
                if feature == "counterevidence"
                else "EMPHASIZE"
            ),
            feature=feature,
            weight=specialized_weight,
        )
        for feature in features
    )
    nodes = (
        CognitivePolicyNode(
            operation="BASELINE_PRIOR",
            feature="all_verified_features",
            weight=0.18,
        ),
        *specialized_nodes,
    )
    body = {
        "method_id": hypothesis["method_id"],
        "operator": operator,
        "nodes": nodes,
    }
    return {
        "policy_id": f"cognitive-policy:{canonical_hash(body)[:24]}",
        **body,
    }


def _feature_value(candidate: CognitiveTaskCandidate, feature: str) -> float:
    value = float(candidate[feature])
    return 1.0 - value if feature == "counterevidence" else value


def _baseline_score(candidate: CognitiveTaskCandidate) -> float:
    return sum(
        float(candidate[feature]) * weight
        for feature, weight in _BASELINE_WEIGHTS.items()
    )


def _execute_policy(
    candidate: CognitiveTaskCandidate,
    policy: CognitiveMethodPolicy,
) -> float:
    score = 0.0
    for node in policy["nodes"]:
        operation = node["operation"]
        if operation == "BASELINE_PRIOR":
            contribution = _baseline_score(candidate)
        elif operation == "INVERT_AND_EMPHASIZE":
            contribution = 1.0 - float(candidate[node["feature"]])
        elif operation == "EMPHASIZE":
            contribution = float(candidate[node["feature"]])
        else:
            raise ValueError(
                "unsupported cognitive policy operation: "
                f"method_id={policy['method_id']}, operation={operation}"
            )
        score += node["weight"] * contribution
    return score


def _select(
    candidates: tuple[CognitiveTaskCandidate, ...],
    policy: CognitiveMethodPolicy | None,
) -> tuple[str, float]:
    scored = tuple(
        (
            candidate["candidate_id"],
            _baseline_score(candidate)
            if policy is None
            else _execute_policy(candidate, policy),
        )
        for candidate in candidates
    )
    return max(scored, key=lambda item: (item[1], item[0]))


def _calibration_score(correct: bool, confidence: float) -> float:
    target = 1.0 if correct else 0.0
    bounded = max(0.0, min(confidence, 1.0))
    return -((bounded - target) ** 2)


def execute_cognitive_experiment(
    hypothesis: CognitiveHypothesis,
    experiment: CognitiveExperiment,
    tasks: Sequence[CognitiveBenchmarkTask],
    evaluator_independent: bool,
) -> tuple[CognitiveTrialResult, ...]:
    if hypothesis["method_id"] != experiment["method_id"]:
        raise ValueError(
            "cognitive experiment identity mismatch: "
            f"hypothesis={hypothesis['method_id']}, experiment={experiment['method_id']}"
        )
    operator = hypothesis["creativity_operator"]
    policy = compile_cognitive_method_policy(hypothesis)
    relevant = tuple(task for task in tasks if task["task_family"] == operator)
    trials: list[CognitiveTrialResult] = []
    for task in relevant:
        if task["evaluator_version"] != COGNITIVE_EVALUATOR_VERSION:
            raise ValueError(
                "cognitive task evaluator mismatch: "
                f"task_id={task['task_id']}, evaluator_version={task['evaluator_version']}"
            )
        baseline_id, baseline_score = _select(task["candidates"], None)
        challenger_id, challenger_score = _select(task["candidates"], policy)
        repeated_id, repeated_score = _select(task["candidates"], policy)
        baseline_correct = baseline_id == task["expected_candidate_id"]
        challenger_correct = challenger_id == task["expected_candidate_id"]
        identity_body = {
            "experiment_id": experiment["experiment_id"],
            "method_id": hypothesis["method_id"],
            "task_id": task["task_id"],
            "evaluator_version": task["evaluator_version"],
            "evaluator_independent": evaluator_independent,
        }
        trials.append(
            {
                "trial_id": f"cognitive-trial:{canonical_hash(identity_body)[:24]}",
                "experiment_id": experiment["experiment_id"],
                "method_id": hypothesis["method_id"],
                "task_id": task["task_id"],
                "domain_id": task["domain_id"],
                "partition": task["partition"],
                "baseline_candidate_id": baseline_id,
                "challenger_candidate_id": challenger_id,
                "expected_candidate_id": task["expected_candidate_id"],
                "baseline_correct": baseline_correct,
                "challenger_correct": challenger_correct,
                "quality_delta": float(int(challenger_correct) - int(baseline_correct)),
                "calibration_delta": _calibration_score(
                    challenger_correct, challenger_score
                )
                - _calibration_score(baseline_correct, baseline_score),
                "cost_delta": _OPERATOR_COST[operator],
                "deterministic": challenger_id == repeated_id
                and challenger_score == repeated_score,
                "evaluator_independent": evaluator_independent,
            }
        )
    return tuple(trials)


def execute_cognitive_experiments(
    hypotheses: Sequence[CognitiveHypothesis],
    experiments: Sequence[CognitiveExperiment],
    tasks: Sequence[CognitiveBenchmarkTask],
    evaluator_independent: bool,
) -> tuple[CognitiveTrialResult, ...]:
    hypothesis_by_id = {record["method_id"]: record for record in hypotheses}
    if len(hypothesis_by_id) != len(hypotheses):
        raise ValueError("cognitive hypotheses contain duplicate method identities")
    trials: list[CognitiveTrialResult] = []
    for experiment in experiments:
        hypothesis = hypothesis_by_id.get(experiment["method_id"])
        if hypothesis is None:
            raise ValueError(
                f"cognitive experiment references missing hypothesis: method_id={experiment['method_id']}"
            )
        trials.extend(
            execute_cognitive_experiment(
                hypothesis,
                experiment,
                tasks,
                evaluator_independent,
            )
        )
    return tuple(trials)
