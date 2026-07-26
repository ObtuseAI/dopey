"""Protected forward-only remove-one-agent ablation evaluation."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dopey.memory.ledger import MemoryKind, load_memory_records
from dopey.protocols.identity import canonical_hash


def _brier(probabilities: Mapping[str, Any], realized_class: str) -> float:
    names = ("bull", "bear", "neutral", "unknown")
    values = {name: max(0.0, float(probabilities.get(name, 0.0))) for name in names}
    total = sum(values.values())
    if total <= 0.0:
        raise ValueError(f"agent ablation probabilities have no positive mass: values={values}")
    normalized = {name: value / total for name, value in values.items()}
    return sum(
        (probability - (1.0 if name == realized_class else 0.0)) ** 2
        for name, probability in normalized.items()
    ) / len(names)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _bootstrap_means(values: Sequence[float], iterations: int, seed: int) -> list[float]:
    if iterations <= 0:
        raise ValueError(f"agent ablation bootstrap iterations must be positive: iterations={iterations}")
    if not values:
        return []
    generator = random.Random(seed)
    return [
        sum(values[generator.randrange(len(values))] for _ in values) / len(values)
        for _ in range(iterations)
    ]


def _load_prediction_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "agent ablation prediction ledger contains invalid JSON: "
                f"path={path}, line_number={line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise TypeError(
                "agent ablation prediction must be an object: "
                f"path={path}, line_number={line_number}"
            )
        records.append(value)
    return records


def evaluate_agent_ablation(
    predictions: Sequence[Mapping[str, Any]],
    settlements: Sequence[Mapping[str, Any]],
    bootstrap_iterations: int,
    seed: int,
    familywise_alpha: float,
    minimum_sample: int,
    minimum_symbol_count: int,
) -> dict[str, Any]:
    if not 0.0 < familywise_alpha < 1.0:
        raise ValueError(f"agent ablation alpha must be within (0, 1): alpha={familywise_alpha}")
    if minimum_sample <= 0 or minimum_symbol_count <= 0:
        raise ValueError(
            "agent ablation minimums must be positive: "
            f"minimum_sample={minimum_sample}, minimum_symbol_count={minimum_symbol_count}"
        )
    predictions_by_id = {str(record.get("prediction_id", "")): record for record in predictions}
    rows_by_agent: dict[str, list[dict[str, Any]]] = {}
    eligible_settlement_count = 0
    for settlement in settlements:
        if settlement.get("settlement_status") != "settled_forward_outcome":
            continue
        prediction_id = str(settlement.get("prediction_id", ""))
        prediction = predictions_by_id.get(prediction_id)
        if prediction is None:
            continue
        if prediction.get("agent_ablation_precommitted_before_outcome") is not True:
            continue
        ablations = prediction.get("agent_ablation_hypotheses", {})
        full = prediction.get("hypotheses", {})
        if not isinstance(ablations, Mapping) or not isinstance(full, Mapping):
            raise TypeError(f"precommitted agent ablation fields must be objects: prediction_id={prediction_id}")
        eligible_settlement_count += 1
        realized = str(settlement["realized_class"])
        full_brier = _brier(full, realized)
        for agent_id, ablated in ablations.items():
            if not isinstance(ablated, Mapping):
                raise TypeError(
                    "precommitted ablation hypothesis must be an object: "
                    f"prediction_id={prediction_id}, agent_id={agent_id}"
                )
            ablated_brier = _brier(ablated, realized)
            rows_by_agent.setdefault(str(agent_id), []).append(
                {
                    "prediction_id": prediction_id,
                    "symbol": str(prediction.get("symbol", "")),
                    "settlement_date": str(settlement.get("actual_settlement_date", "")),
                    "contested_truth": bool(settlement.get("contested_truth", False)),
                    "full_brier": full_brier,
                    "ablated_brier": ablated_brier,
                    "improvement": ablated_brier - full_brier,
                }
            )
    agent_ids = sorted(rows_by_agent)
    evaluation_count = max(len(agent_ids), 1)
    evaluations: list[dict[str, Any]] = []
    for agent_index, agent_id in enumerate(agent_ids):
        rows = rows_by_agent[agent_id]
        improvements = [float(row["improvement"]) for row in rows]
        bootstrap = _bootstrap_means(improvements, bootstrap_iterations, seed + agent_index)
        lower = _quantile(bootstrap, 0.025)
        upper = _quantile(bootstrap, 0.975)
        mean_improvement = sum(improvements) / len(improvements)
        raw_p = (1 + sum(value <= 0.0 for value in bootstrap)) / (1 + len(bootstrap))
        adjusted_p = min(1.0, raw_p * evaluation_count)
        symbols = {str(row["symbol"]) for row in rows}
        contested = [float(row["improvement"]) for row in rows if bool(row["contested_truth"])]
        contested_mean = sum(contested) / len(contested) if contested else None
        sample_sufficient = len(rows) >= minimum_sample and len(symbols) >= minimum_symbol_count
        robust_positive = (
            sample_sufficient
            and lower > 0.0
            and adjusted_p <= familywise_alpha
            and (contested_mean is None or contested_mean >= 0.0)
        )
        robust_negative = sample_sufficient and upper < 0.0
        recommendation = (
            "RETAIN_FORWARD_VALIDATED"
            if robust_positive
            else "RETIRE_RECOMMENDED_OPERATOR_REVIEW"
            if robust_negative
            else "SHADOW_ONLY_INSUFFICIENT_OR_INCONCLUSIVE"
        )
        evaluations.append(
            {
                "agent_id": agent_id,
                "sample_count": len(rows),
                "symbol_count": len(symbols),
                "settlement_ids": sorted(str(row["prediction_id"]) for row in rows),
                "mean_brier_improvement_vs_ablation": round(mean_improvement, 8),
                "bootstrap_95_percent_ci": [round(lower, 8), round(upper, 8)],
                "raw_one_sided_p_value": round(raw_p, 8),
                "bonferroni_adjusted_p_value": round(adjusted_p, 8),
                "contested_truth_count": len(contested),
                "contested_truth_mean_improvement": round(contested_mean, 8) if contested_mean is not None else None,
                "sample_sufficient": sample_sufficient,
                "forward_precommitted_held_out": True,
                "agent_contribution_validated": robust_positive,
                "retirement_recommended": robust_negative,
                "recommended_state": recommendation,
                "auto_applied": robust_positive or robust_negative,
                "human_review_required": False,
                "full_promotion_matrix_required_for_activation": True,
            }
        )
    sufficient = [record for record in evaluations if record["sample_sufficient"]]
    status = (
        "forward_ablation_evaluated"
        if sufficient
        else "insufficient_forward_settlements"
    )
    body: dict[str, Any] = {
        "artifact_type": "vnext_forward_agent_ablation_evaluation",
        "ablation_evaluator_version": "dopey-forward-agent-ablation-v1",
        "evaluation_status": status,
        "protected_evaluator": True,
        "optimizer_may_tune_evaluator": False,
        "precommitted_counterfactual_required": True,
        "eligible_settlement_count": eligible_settlement_count,
        "agent_count": len(evaluations),
        "minimum_sample": minimum_sample,
        "minimum_symbol_count": minimum_symbol_count,
        "bootstrap_iterations": bootstrap_iterations,
        "familywise_alpha": familywise_alpha,
        "multiple_testing_method": "bonferroni",
        "evaluations": evaluations,
        "validated_positive_agent_count": sum(record["agent_contribution_validated"] for record in evaluations),
        "retirement_recommendation_count": sum(record["retirement_recommended"] for record in evaluations),
        "automatic_retirement_count": sum(record["retirement_recommended"] for record in evaluations),
        "automatic_validation_transition_count": sum(record["agent_contribution_validated"] for record in evaluations),
        "automatic_promotion_count": 0,
        "historical_replay_counted_as_forward_proof": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}


def evaluate_agent_ablation_ledgers(
    prediction_ledger: Path,
    settlement_memory: Path,
    bootstrap_iterations: int,
    seed: int,
    familywise_alpha: float,
    minimum_sample: int,
    minimum_symbol_count: int,
) -> dict[str, Any]:
    predictions = _load_prediction_ledger(prediction_ledger)
    settlement_records = load_memory_records(settlement_memory, MemoryKind.SETTLEMENT)
    settlements = [
        record["payload"]
        for record in settlement_records
        if isinstance(record.get("payload"), Mapping)
    ]
    return evaluate_agent_ablation(
        predictions,
        settlements,
        bootstrap_iterations,
        seed,
        familywise_alpha,
        minimum_sample,
        minimum_symbol_count,
    )
