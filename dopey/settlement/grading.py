"""Forward-only settlement grading over verified price history."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from dopey.protocols.identity import canonical_hash
from dopey.gates.evaluator import evaluate_gate
from dopey.gates.policy import policy_by_id
from dopey_equity_swing.market_structure import Bar


@dataclass(frozen=True)
class SettlementPolicy:
    neutral_return_band: float
    contested_margin: float
    maximum_price_gap_days: int
    probability_floor: float


def _date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _probabilities(prediction: Mapping[str, Any], floor: float) -> dict[str, float]:
    raw = prediction.get("hypotheses")
    if not isinstance(raw, Mapping):
        raise TypeError(
            "prediction hypotheses must be an object: "
            f"prediction_id={prediction.get('prediction_id', '')}"
        )
    names = ("bull", "bear", "neutral", "unknown")
    unexpected = sorted(set(str(name) for name in raw) - set(names))
    missing = sorted(set(names) - set(str(name) for name in raw))
    values = {name: float(raw.get(name, 0.0)) for name in names}
    invalid = {
        name: value
        for name, value in values.items()
        if not math.isfinite(value) or not 0.0 <= value <= 1.0
    }
    if missing or unexpected or invalid:
        raise ValueError(
            "settlement prediction probabilities violate the governed class contract: "
            f"prediction_id={prediction.get('prediction_id', '')}, missing={missing}, "
            f"unexpected={unexpected}, invalid={invalid}"
        )
    values = {name: max(floor, value) for name, value in values.items()}
    total = sum(values.values())
    if total <= 0.0:
        raise ValueError(
            "prediction probabilities must have positive mass: "
            f"prediction_id={prediction.get('prediction_id', '')}"
        )
    return {name: value / total for name, value in values.items()}


def _price_bar_on_or_before(rows: Sequence[Bar], target: date) -> Bar | None:
    eligible = [row for row in rows if _date(str(row["date"])) <= target]
    return eligible[-1] if eligible else None


def _price_bar_on_or_after(rows: Sequence[Bar], target: date, maximum: date) -> Bar | None:
    return next(
        (
            row
            for row in rows
            if target <= _date(str(row["date"])) <= maximum
        ),
        None,
    )


def _realized_class(total_return: float, band: float) -> str:
    if total_return > band:
        return "bull"
    if total_return < -band:
        return "bear"
    return "neutral"


def _path_contested(rows: Sequence[Bar], start: date, end: date, entry: float, band: float) -> bool:
    window = [row for row in rows if start <= _date(str(row["date"])) <= end]
    if not window:
        return False
    maximum_return = max(float(row["high"]) / entry - 1.0 for row in window)
    minimum_return = min(float(row["low"]) / entry - 1.0 for row in window)
    return maximum_return > band and minimum_return < -band


def grade_forward_prediction(
    prediction: Mapping[str, Any],
    rows: Sequence[Bar],
    as_of_date: str,
    policy: SettlementPolicy,
) -> dict[str, Any]:
    prediction_id = str(prediction.get("prediction_id", ""))
    if not prediction_id:
        raise ValueError("settlement requires prediction_id")
    if prediction.get("paper_only") is not True or prediction.get("live_blocked") is not True:
        raise ValueError(f"settlement rejects non-research prediction: prediction_id={prediction_id}")
    if (
        prediction.get("point_in_time_complete") is not True
        or not str(prediction.get("point_in_time_proof_id", "")).strip()
    ):
        return {
            "artifact_type": "vnext_forward_settlement",
            "settlement_version": "dopey-vnext-forward-settlement-v1",
            "prediction_id": prediction_id,
            "symbol": str(prediction.get("symbol", "")),
            "settlement_status": "quarantined_missing_point_in_time_proof",
            "as_of_date": _date(as_of_date).isoformat(),
            "quarantine_reason": "prediction_is_not_settlement_eligible_without_complete_hashed_input_time_proof",
            "early_grading_performed": False,
            "calibration_eligible": False,
            "paper_only": True,
            "live_blocked": True,
            "promotion_allowed": False,
        }
    minimum_date = _date(str(prediction["minimum_settlement_date"]))
    observed_date = _date(as_of_date)
    if observed_date < minimum_date:
        return {
            "artifact_type": "vnext_forward_settlement",
            "settlement_version": "dopey-vnext-forward-settlement-v1",
            "prediction_id": prediction_id,
            "symbol": str(prediction["symbol"]),
            "settlement_status": "pending_minimum_horizon",
            "minimum_settlement_date": minimum_date.isoformat(),
            "as_of_date": observed_date.isoformat(),
            "days_until_eligible": (minimum_date - observed_date).days,
            "early_grading_performed": False,
            "paper_only": True,
            "live_blocked": True,
            "promotion_allowed": False,
        }
    prediction_date = _date(str(prediction["prediction_market_time"]))
    entry_bar = _price_bar_on_or_before(rows, prediction_date)
    settlement_bar = _price_bar_on_or_after(rows, minimum_date, observed_date)
    if entry_bar is None or settlement_bar is None:
        return {
            "artifact_type": "vnext_forward_settlement",
            "settlement_version": "dopey-vnext-forward-settlement-v1",
            "prediction_id": prediction_id,
            "symbol": str(prediction["symbol"]),
            "settlement_status": "due_missing_verified_price",
            "minimum_settlement_date": minimum_date.isoformat(),
            "as_of_date": observed_date.isoformat(),
            "entry_price_available": entry_bar is not None,
            "settlement_price_available": settlement_bar is not None,
            "early_grading_performed": False,
            "paper_only": True,
            "live_blocked": True,
            "promotion_allowed": False,
        }
    settlement_date = _date(str(settlement_bar["date"]))
    gap_days = (settlement_date - minimum_date).days
    if gap_days > policy.maximum_price_gap_days:
        # A stale/delisted symbol has no verified in-window price. That is a
        # data gap for this one prediction, not a fatal error: raising here
        # would wedge settlement grading for every other prediction in the
        # batch. Report it like any other missing verified price so the
        # operator refresh path applies.
        return {
            "artifact_type": "vnext_forward_settlement",
            "settlement_version": "dopey-vnext-forward-settlement-v1",
            "prediction_id": prediction_id,
            "symbol": str(prediction["symbol"]),
            "settlement_status": "due_missing_verified_price",
            "minimum_settlement_date": minimum_date.isoformat(),
            "as_of_date": observed_date.isoformat(),
            "entry_price_available": entry_bar is not None,
            "settlement_price_available": False,
            "settlement_price_gap_days": gap_days,
            "maximum_price_gap_days": policy.maximum_price_gap_days,
            "price_gap_reason": "settlement_price_too_stale_for_grading",
            "early_grading_performed": False,
            "paper_only": True,
            "live_blocked": True,
            "promotion_allowed": False,
        }
    entry_price = float(entry_bar["close"])
    settlement_price = float(settlement_bar["close"])
    if entry_price <= 0.0 or settlement_price <= 0.0:
        raise ValueError(f"settlement prices must be positive: prediction_id={prediction_id}")
    total_return = settlement_price / entry_price - 1.0
    outcome = _realized_class(total_return, policy.neutral_return_band)
    probabilities = _probabilities(prediction, policy.probability_floor)
    brier = sum(
        (probability - (1.0 if name == outcome else 0.0)) ** 2
        for name, probability in probabilities.items()
    ) / len(probabilities)
    log_loss = -math.log(max(probabilities[outcome], policy.probability_floor))
    dominant = str(prediction["dominant_hypothesis"])
    dominant_correct = dominant == outcome
    research_confidence = float(prediction["final_research_confidence"])
    threshold_distance = abs(abs(total_return) - policy.neutral_return_band)
    contested = threshold_distance <= policy.contested_margin or _path_contested(
        rows,
        prediction_date,
        settlement_date,
        entry_price,
        policy.neutral_return_band,
    )
    settlement_gate = evaluate_gate(
        policy_by_id("settlement_admission"),
        prediction_id,
        {
            "minimum_horizon_reached": True,
            "verified_terminal_price": True,
            "early_grading_performed": False,
        },
        (str(prediction["point_in_time_proof_id"]),),
    )
    if not settlement_gate["passed"]:
        raise RuntimeError(f"settlement admission gate failed after verified grading inputs: prediction_id={prediction_id}")
    body: dict[str, Any] = {
        "artifact_type": "vnext_forward_settlement",
        "settlement_version": "dopey-vnext-forward-settlement-v1",
        "prediction_id": prediction_id,
        "symbol": str(prediction["symbol"]),
        "settlement_status": "settled_forward_outcome",
        "prediction_market_date": prediction_date.isoformat(),
        "minimum_settlement_date": minimum_date.isoformat(),
        "actual_settlement_date": settlement_date.isoformat(),
        "as_of_date": observed_date.isoformat(),
        "entry_close": round(entry_price, 8),
        "settlement_close": round(settlement_price, 8),
        "total_return": round(total_return, 8),
        "neutral_return_band": policy.neutral_return_band,
        "realized_class": outcome,
        "dominant_hypothesis": dominant,
        "dominant_correct": dominant_correct,
        "research_confidence": research_confidence,
        "confidence_absolute_error": round(abs(research_confidence - float(dominant_correct)), 8),
        "multiclass_brier_score": round(brier, 8),
        "multiclass_log_loss": round(log_loss, 8),
        "contested_truth": contested,
        "contested_reason": (
            "threshold_or_path_ambiguity" if contested else "uncontested_terminal_classification"
        ),
        "early_grading_performed": False,
        "autonomous_threshold_gate": settlement_gate,
        "traded": False,
        "promotion_allowed": False,
        "not_readiness_evidence_until_external_gate_ingests": True,
        "paper_only": True,
        "live_blocked": True,
    }
    content_hash = canonical_hash(body)
    return {
        **body,
        "settlement_id": f"vnext-settlement:{content_hash[:24]}",
        "content_hash": content_hash,
    }
