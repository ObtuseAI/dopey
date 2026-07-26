"""Point-in-time reverse engineering of settled research behavior."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from statistics import median
from typing import Any

from dopey.protocols.identity import canonical_hash

from .schema import ReverseCase


def _timestamp(value: object, field: str, identity: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"reverse engineering requires timezone-aware timestamps: field={field}, identity={identity}")
    return parsed


def _feature_values(prediction: Mapping[str, Any]) -> dict[str, float]:
    hypotheses = prediction.get("hypotheses")
    contributions = prediction.get("agent_contributions")
    if not isinstance(hypotheses, Mapping) or not isinstance(contributions, Mapping):
        raise TypeError(f"reverse engineering prediction lacks typed feature maps: prediction_id={prediction.get('prediction_id', '')}")
    features = {f"hypothesis_{name}": float(value) for name, value in hypotheses.items()}
    features.update({f"agent_{name}": float(value) for name, value in contributions.items()})
    features["final_research_confidence"] = float(prediction["final_research_confidence"])
    invalid = {name: value for name, value in features.items() if not math.isfinite(value)}
    if invalid:
        raise ValueError(f"reverse engineering feature values must be finite: invalid={invalid}")
    return features


def _settlement_payload(record: Mapping[str, Any]) -> Mapping[str, Any]:
    if record.get("artifact_type") != "dopey_research_memory_record":
        return record
    if record.get("memory_kind") != "settlement":
        raise ValueError(f"reverse engineering received a non-settlement memory record: memory_id={record.get('memory_id', '')}")
    if record.get("paper_only") is not True or record.get("live_blocked") is not True:
        raise ValueError(f"reverse engineering rejects an unsealed settlement memory record: memory_id={record.get('memory_id', '')}")
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise TypeError(f"reverse engineering settlement memory payload must be an object: memory_id={record.get('memory_id', '')}")
    return payload


def _index_settlements(settlements: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in settlements:
        payload = _settlement_payload(record)
        if payload.get("settlement_status") != "settled_forward_outcome":
            continue
        prediction_id = str(payload.get("prediction_id", "")).strip()
        if not prediction_id:
            raise ValueError("reverse engineering settled outcome lacks prediction_id")
        prior = indexed.get(prediction_id)
        if prior is not None and canonical_hash(prior) != canonical_hash(payload):
            raise ValueError(f"reverse engineering detected conflicting immutable settlements: prediction_id={prediction_id}")
        indexed[prediction_id] = payload
    return indexed


def build_reverse_cases(
    predictions: Sequence[Mapping[str, Any]],
    settlements: Sequence[Mapping[str, Any]],
) -> tuple[ReverseCase, ...]:
    settlement_by_prediction = _index_settlements(settlements)
    cases: list[ReverseCase] = []
    for prediction in predictions:
        prediction_id = str(prediction.get("prediction_id", "")).strip()
        settlement = settlement_by_prediction.get(prediction_id)
        if settlement is None:
            continue
        if prediction.get("paper_only") is not True or prediction.get("live_blocked") is not True:
            raise ValueError(f"reverse engineering rejects an unsealed prediction: prediction_id={prediction_id}")
        if settlement.get("paper_only") is not True or settlement.get("live_blocked") is not True:
            raise ValueError(f"reverse engineering rejects an unsealed settlement: prediction_id={prediction_id}")
        if prediction.get("point_in_time_complete") is not True or not str(prediction.get("point_in_time_proof_id", "")).strip():
            continue
        prediction_time = _timestamp(prediction.get("prediction_market_time"), "prediction_market_time", prediction_id)
        settlement_time = _timestamp(f"{settlement.get('actual_settlement_date')}T23:59:59+00:00", "actual_settlement_date", prediction_id)
        if prediction_time >= settlement_time:
            raise ValueError(f"reverse engineering detected non-forward causal order: prediction_id={prediction_id}")
        symbol = str(prediction.get("symbol", "")).strip()
        if not symbol:
            raise ValueError(f"reverse engineering prediction lacks symbol: prediction_id={prediction_id}")
        body = {
            "prediction_id": prediction_id,
            "symbol": symbol,
            "era": prediction_time.strftime("%Y"),
            "regime": str(prediction.get("research_regime", "unresolved_regime")),
            "feature_values": _feature_values(prediction),
            "dominant_correct": 1.0 if bool(settlement.get("dominant_correct")) else 0.0,
            "contested_truth": bool(settlement.get("contested_truth", False)),
            "evidence_ids": tuple(sorted(str(value) for value in prediction.get("evidence_ids", []))),
            "point_in_time_proof_id": str(prediction["point_in_time_proof_id"]),
        }
        case_id = f"reverse-case:{canonical_hash(body)[:24]}"
        cases.append({"case_id": case_id, **body})  # type: ignore[arg-type]
    return tuple(sorted(cases, key=lambda record: record["case_id"]))


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _transfer_consistency(
    cases: Sequence[ReverseCase],
    feature_name: str,
    split: float,
    grouping_field: str,
    overall_effect: float,
) -> tuple[int, float]:
    grouped: dict[str, dict[str, float | int]] = {}
    for case in cases:
        group_name = str(case[grouping_field])
        bucket = grouped.setdefault(
            group_name,
            {"high_sum": 0.0, "high_count": 0, "low_sum": 0.0, "low_count": 0},
        )
        outcome = float(case["dominant_correct"])
        if case["feature_values"][feature_name] >= split:
            bucket["high_sum"] = float(bucket["high_sum"]) + outcome
            bucket["high_count"] = int(bucket["high_count"]) + 1
        else:
            bucket["low_sum"] = float(bucket["low_sum"]) + outcome
            bucket["low_count"] = int(bucket["low_count"]) + 1
    effects: list[float] = []
    for group_name in sorted(grouped):
        bucket = grouped[group_name]
        high_count = int(bucket["high_count"])
        low_count = int(bucket["low_count"])
        if high_count and low_count:
            effects.append(
                float(bucket["high_sum"]) / high_count
                - float(bucket["low_sum"]) / low_count
            )
    if not effects or overall_effect == 0.0:
        return len(effects), 0.0
    consistent = sum(effect * overall_effect > 0.0 for effect in effects)
    return len(effects), consistent / len(effects)


def infer_reverse_hypotheses(
    cases: Sequence[ReverseCase],
    minimum_support: int,
    minimum_absolute_effect: float,
    maximum_hypotheses: int,
) -> dict[str, Any]:
    if minimum_support <= 1 or not 0.0 < minimum_absolute_effect < 1.0 or maximum_hypotheses <= 0:
        raise ValueError("reverse engineering thresholds are invalid")
    feature_names = sorted({name for case in cases for name in case["feature_values"]})
    hypotheses: list[dict[str, Any]] = []
    for feature_name in feature_names:
        available = tuple(case for case in cases if feature_name in case["feature_values"])
        if len(available) < minimum_support:
            continue
        split = median(case["feature_values"][feature_name] for case in available)
        high = tuple(case for case in available if case["feature_values"][feature_name] >= split)
        low = tuple(case for case in available if case["feature_values"][feature_name] < split)
        if not high or not low:
            continue
        effect = _mean(tuple(case["dominant_correct"] for case in high)) - _mean(tuple(case["dominant_correct"] for case in low))
        contested = tuple(case for case in available if case["contested_truth"])
        symbol_count = len({case["symbol"] for case in available})
        era_count = len({case["era"] for case in available})
        regime_count = len({case["regime"] for case in available if case["regime"] != "unresolved_regime"})
        eligible_symbol_groups, symbol_consistency = _transfer_consistency(available, feature_name, split, "symbol", effect)
        eligible_era_groups, era_consistency = _transfer_consistency(available, feature_name, split, "era", effect)
        status = (
            "association_only_replay_required"
            if (
                abs(effect) >= minimum_absolute_effect
                and symbol_count >= 2
                and era_count >= 2
                and eligible_symbol_groups >= 2
                and eligible_era_groups >= 2
                and symbol_consistency >= 2.0 / 3.0
                and era_consistency >= 2.0 / 3.0
            )
            else "rejected_weak_or_concentrated_association"
        )
        body = {
            "feature": feature_name,
            "split_threshold": split,
            "support": len(available),
            "high_group_support": len(high),
            "low_group_support": len(low),
            "correctness_effect": round(effect, 10),
            "contested_support": len(contested),
            "symbol_count": symbol_count,
            "era_count": era_count,
            "resolved_regime_count": regime_count,
            "eligible_symbol_transfer_groups": eligible_symbol_groups,
            "eligible_era_transfer_groups": eligible_era_groups,
            "symbol_direction_consistency": round(symbol_consistency, 10),
            "era_direction_consistency": round(era_consistency, 10),
            "hypothesis_status": status,
            "causal_claim_allowed": False,
            "promotion_allowed": False,
            "required_next_checks": ("circular_shift_null", "random_entry", "held_out_era", "cross_symbol_transfer", "multiple_testing_correction"),
            "case_ids": tuple(case["case_id"] for case in available),
        }
        hypotheses.append({**body, "hypothesis_id": f"reverse-hypothesis:{canonical_hash(body)[:24]}"})
    ranked = sorted(hypotheses, key=lambda record: (-abs(float(record["correctness_effect"])), str(record["hypothesis_id"])))[:maximum_hypotheses]
    transferable_count = sum(record["hypothesis_status"] == "association_only_replay_required" for record in ranked)
    status = (
        "insufficient_settled_observations"
        if not ranked
        else "complete_association_hypotheses_only"
        if transferable_count
        else "complete_no_transferable_association"
    )
    return {
        "artifact_type": "strategy_reverse_engineering_report",
        "reverse_engineering_version": "dopey-strategy-reverse-engineering-v1",
        "reverse_status": status,
        "settled_case_count": len(cases),
        "minimum_support": minimum_support,
        "hypothesis_count": len(ranked),
        "transferable_association_count": transferable_count,
        "hypotheses": ranked,
        "uses_only_settled_point_in_time_cases": True,
        "causal_claim_allowed": False,
        "automatic_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
