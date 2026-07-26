"""Deterministic forward-evidence accrual monitoring without readiness authority."""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from dopey.constitution.execution_seal import assert_output_research_only
from dopey.memory.ledger import MemoryKind, load_memory_records
from dopey.protocols.identity import canonical_hash
from dopey.technical.history_adapter import load_default_validated_symbol_history
from dopey_equity_swing.market_structure import Bar

from .grading import SettlementPolicy, grade_forward_prediction
from .ledger import load_prediction_ledger


def _settlements_by_prediction(
    settlement_payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for payload in settlement_payloads:
        prediction_id = str(payload.get("prediction_id", "")).strip()
        if not prediction_id:
            raise ValueError("settlement memory payload requires prediction_id")
        existing = indexed.get(prediction_id)
        if existing is not None and canonical_hash(existing) != canonical_hash(payload):
            raise ValueError(
                "settlement memory contains conflicting outcomes: "
                f"prediction_id={prediction_id}"
            )
        indexed[prediction_id] = payload
    return indexed


def _queue_status(
    prediction: Mapping[str, Any],
    rows: Sequence[Bar],
    recorded_settlement: Mapping[str, Any] | None,
    as_of_date: str,
    policy: SettlementPolicy,
) -> tuple[str, Mapping[str, Any]]:
    if recorded_settlement is not None:
        if recorded_settlement.get("settlement_status") != "settled_forward_outcome":
            raise ValueError(
                "settlement memory contains a non-final outcome: "
                f"prediction_id={prediction.get('prediction_id', '')}, "
                f"settlement_status={recorded_settlement.get('settlement_status', '')}"
            )
        return "settled_recorded", recorded_settlement
    assessment = grade_forward_prediction(prediction, rows, as_of_date, policy)
    settlement_status = str(assessment["settlement_status"])
    status_by_settlement = {
        "pending_minimum_horizon": "pending_minimum_horizon",
        "due_missing_verified_price": "due_missing_verified_price",
        "quarantined_missing_point_in_time_proof": "quarantined_missing_point_in_time_proof",
        "settled_forward_outcome": "gradeable_unrecorded",
    }
    if settlement_status not in status_by_settlement:
        raise ValueError(
            "forward accrual monitor received an unsupported settlement status: "
            f"prediction_id={prediction.get('prediction_id', '')}, settlement_status={settlement_status}"
        )
    return status_by_settlement[settlement_status], assessment


def _operator_next_step(status: str) -> str:
    next_step_by_status = {
        "settled_recorded": "none_already_recorded_append_only",
        "pending_minimum_horizon": "wait_until_minimum_settlement_date",
        "due_missing_verified_price": "refresh_verified_symbol_history_then_rerun_settlement",
        "quarantined_missing_point_in_time_proof": "operator_review_point_in_time_proof_no_auto_repair",
        "gradeable_unrecorded": "run_idempotent_settlement_cycle",
    }
    if status not in next_step_by_status:
        raise ValueError(f"forward accrual status has no operator next step: status={status}")
    return next_step_by_status[status]


def _queue_record(
    prediction: Mapping[str, Any],
    status: str,
    assessment: Mapping[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    minimum_date = str(prediction.get("minimum_settlement_date", ""))
    days_until_eligible: int | None
    if status == "pending_minimum_horizon" and minimum_date:
        days_until_eligible = max(
            (date.fromisoformat(minimum_date) - date.fromisoformat(as_of_date[:10])).days,
            0,
        )
    elif status == "quarantined_missing_point_in_time_proof":
        days_until_eligible = None
    else:
        days_until_eligible = 0
    return {
        "prediction_id": str(prediction.get("prediction_id", "")),
        "symbol": str(prediction.get("symbol", "")),
        "prediction_market_time": str(prediction.get("prediction_market_time", "")),
        "minimum_settlement_date": minimum_date,
        "queue_status": status,
        "days_until_eligible": days_until_eligible,
        "operator_next_step": _operator_next_step(status),
        "settlement_already_recorded": status == "settled_recorded",
        "point_in_time_complete": prediction.get("point_in_time_complete") is True,
        "assessment_status": str(assessment.get("settlement_status", "")),
        "early_grading_performed": False,
        "promotion_allowed": False,
    }


def _monitor_status(counts: Mapping[str, int], prediction_count: int) -> str:
    attention_count = sum(
        counts.get(status, 0)
        for status in (
            "gradeable_unrecorded",
            "due_missing_verified_price",
            "quarantined_missing_point_in_time_proof",
        )
    )
    if prediction_count == 0:
        return "empty_prediction_ledger"
    if attention_count > 0:
        return "operator_attention_required"
    if counts.get("pending_minimum_horizon", 0) > 0:
        return "awaiting_forward_maturity"
    return "all_eligible_settlements_recorded"


def build_forward_accrual_monitor(
    predictions: Sequence[Mapping[str, Any]],
    histories: Mapping[str, Sequence[Bar]],
    settlement_payloads: Sequence[Mapping[str, Any]],
    as_of_date: str,
    policy: SettlementPolicy,
) -> dict[str, Any]:
    observed_date = date.fromisoformat(as_of_date[:10]).isoformat()
    recorded = _settlements_by_prediction(settlement_payloads)
    queue: list[dict[str, Any]] = []
    ordered_predictions = sorted(
        predictions,
        key=lambda value: (
            str(value.get("minimum_settlement_date", "")),
            str(value.get("symbol", "")),
            str(value.get("prediction_id", "")),
        ),
    )
    for prediction in ordered_predictions:
        prediction_id = str(prediction.get("prediction_id", "")).strip()
        symbol = str(prediction.get("symbol", "")).strip()
        if not prediction_id or not symbol:
            raise ValueError(
                "forward accrual prediction requires identity and symbol: "
                f"prediction_id={prediction_id}, symbol={symbol}"
            )
        recorded_settlement = recorded.get(prediction_id)
        requires_history = (
            recorded_settlement is None
            and prediction.get("point_in_time_complete") is True
            and bool(str(prediction.get("point_in_time_proof_id", "")).strip())
        )
        if requires_history and symbol not in histories:
            raise KeyError(
                "forward accrual monitor lacks verified history: "
                f"prediction_id={prediction_id}, symbol={symbol}"
            )
        status, assessment = _queue_status(
            prediction,
            histories.get(symbol, ()),
            recorded_settlement,
            observed_date,
            policy,
        )
        queue.append(_queue_record(prediction, status, assessment, observed_date))
    counts = Counter(str(record["queue_status"]) for record in queue)
    future_dates = sorted(
        {
            str(record["minimum_settlement_date"])
            for record in queue
            if record["queue_status"] == "pending_minimum_horizon"
            and str(record["minimum_settlement_date"])
        }
    )
    body: dict[str, Any] = {
        "artifact_type": "vnext_forward_evidence_accrual_monitor",
        "monitor_version": "dopey-vnext-forward-accrual-monitor-v1",
        "monitor_status": _monitor_status(counts, len(queue)),
        "as_of_date": observed_date,
        "prediction_count": len(queue),
        "settled_recorded_count": counts.get("settled_recorded", 0),
        "pending_minimum_horizon_count": counts.get("pending_minimum_horizon", 0),
        "gradeable_unrecorded_count": counts.get("gradeable_unrecorded", 0),
        "due_missing_verified_price_count": counts.get("due_missing_verified_price", 0),
        "quarantined_missing_point_in_time_proof_count": counts.get(
            "quarantined_missing_point_in_time_proof", 0
        ),
        "next_minimum_settlement_date": future_dates[0] if future_dates else None,
        "queue": queue,
        "early_grading_performed": False,
        "synthetic_evidence_counted": False,
        "historical_replay_counted_as_forward_proof": False,
        "readiness_effect": "none_protected_external_gate",
        "action_ready": False,
        "automatic_promotion_count": 0,
        "paper_only": True,
        "live_blocked": True,
    }
    monitor = {**body, "reproducibility_hash": canonical_hash(body)}
    assert_output_research_only(monitor)
    return monitor


def _write_object_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(dict(value), sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_forward_accrual_monitor(
    prediction_ledger: Path,
    settlement_memory: Path,
    as_of_date: str,
    output_path: Path,
    policy: SettlementPolicy,
) -> dict[str, Any]:
    predictions = load_prediction_ledger(prediction_ledger)
    settlement_records = load_memory_records(settlement_memory, MemoryKind.SETTLEMENT)
    settlement_payloads = [
        record["payload"]
        for record in settlement_records
        if isinstance(record.get("payload"), Mapping)
    ]
    recorded_prediction_ids = {
        str(payload.get("prediction_id", "")).strip()
        for payload in settlement_payloads
    }
    symbols = sorted(
        {
            str(prediction.get("symbol", "")).strip()
            for prediction in predictions
            if str(prediction.get("prediction_id", "")).strip() not in recorded_prediction_ids
            and prediction.get("point_in_time_complete") is True
            and bool(str(prediction.get("point_in_time_proof_id", "")).strip())
        }
    )
    histories: dict[str, Sequence[Bar]] = {}
    for symbol in symbols:
        if not symbol:
            raise ValueError(f"forward accrual ledger contains an empty symbol: path={prediction_ledger}")
        history, _ = load_default_validated_symbol_history(symbol)
        histories[symbol] = history
    monitor = build_forward_accrual_monitor(
        predictions,
        histories,
        settlement_payloads,
        as_of_date,
        policy,
    )
    _write_object_atomic(output_path, monitor)
    return monitor
