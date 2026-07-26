"""Operational settlement cycle over the append-only vNext prediction ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dopey.memory.calibration import append_calibration
from dopey.memory.ledger import MemoryKind, load_memory_records
from dopey.memory.settlements import append_settlement
from dopey.protocols.identity import canonical_hash
from dopey.technical.history_adapter import load_default_validated_symbol_history

from .calibration import summarize_calibration
from .grading import SettlementPolicy, grade_forward_prediction
from .ledger import load_prediction_ledger


@dataclass(frozen=True)
class SettlementRunPaths:
    prediction_ledger: Path
    settlement_memory: Path
    calibration_memory: Path
    calibration_summary: Path


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), sort_keys=True, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _recorded_settlements(path: Path) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    records = load_memory_records(path, MemoryKind.SETTLEMENT)
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise TypeError(
                "settlement memory payload must be an object: "
                f"path={path}, memory_id={record.get('memory_id', '')}"
            )
        prediction_id = str(payload.get("prediction_id", "")).strip()
        if not prediction_id:
            raise ValueError(
                "settlement memory payload requires prediction_id: "
                f"path={path}, memory_id={record.get('memory_id', '')}"
            )
        if payload.get("settlement_status") != "settled_forward_outcome":
            raise ValueError(
                "settlement memory contains a non-final outcome: "
                f"path={path}, prediction_id={prediction_id}, "
                f"settlement_status={payload.get('settlement_status', '')}"
            )
        prior = indexed.get(prediction_id)
        if prior is not None and canonical_hash(prior) != canonical_hash(payload):
            raise ValueError(
                "settlement memory contains conflicting immutable outcomes: "
                f"path={path}, prediction_id={prediction_id}"
            )
        indexed[prediction_id] = dict(payload)
    return indexed


def _file_sha256_or_empty(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_settlement_cycle(
    as_of_date: str,
    observed_at: str,
    paths: SettlementRunPaths,
    policy: SettlementPolicy,
    calibration_bin_count: int,
    minimum_calibration_sample: int,
) -> dict[str, Any]:
    predictions = load_prediction_ledger(paths.prediction_ledger)
    recorded_settlements = _recorded_settlements(paths.settlement_memory)
    histories: dict[str, list[Any]] = {}
    settlements: list[dict[str, Any]] = []
    append_statuses: list[dict[str, str]] = []
    recorded_settlement_count = 0
    for prediction in predictions:
        prediction_id = str(prediction["prediction_id"])
        recorded = recorded_settlements.get(prediction_id)
        if recorded is not None:
            settlements.append(recorded)
            recorded_settlement_count += 1
            continue
        symbol = str(prediction["symbol"])
        if symbol not in histories:
            histories[symbol], _ = load_default_validated_symbol_history(symbol)
        settlement = grade_forward_prediction(prediction, histories[symbol], as_of_date, policy)
        settlements.append(settlement)
        if settlement["settlement_status"] == "settled_forward_outcome":
            append_statuses.append(
                append_settlement(
                    paths.settlement_memory,
                    settlement,
                    observed_at,
                    prediction_id,
                    tuple(str(value) for value in prediction.get("evidence_ids", [])),
                )
            )
    summarized = summarize_calibration(
        settlements,
        calibration_bin_count,
        minimum_calibration_sample,
    )
    calibration_body = dict(summarized)
    calibration_body.pop("reproducibility_hash", None)
    calibration_unsigned = {
        **calibration_body,
        "as_of_date": as_of_date,
        "observed_at": observed_at,
        "source_evidence_hashes": {
            "forward_predictions.jsonl": _file_sha256_or_empty(
                paths.prediction_ledger
            ),
            "memory/settlements.jsonl": _file_sha256_or_empty(
                paths.settlement_memory
            ),
        },
    }
    calibration = {
        **calibration_unsigned,
        "reproducibility_hash": canonical_hash(calibration_unsigned),
    }
    calibration_append = append_calibration(
        paths.calibration_memory,
        calibration,
        observed_at,
        "settlement-cycle",
        tuple(
            str(record["settlement_id"])
            for record in settlements
            if record.get("settlement_id")
        ),
    )
    _write_object(paths.calibration_summary, calibration)
    return {
        "artifact_type": "vnext_settlement_cycle_summary",
        "settlement_cycle_version": "dopey-vnext-settlement-cycle-v1",
        "as_of_date": as_of_date,
        "prediction_count": len(predictions),
        "settled_count": calibration["settled_total"],
        "pending_count": calibration["pending_total"],
        "missing_price_count": calibration["due_missing_verified_price_total"],
        "quarantined_count": calibration["quarantined_missing_point_in_time_proof_total"],
        "recorded_settlement_count": recorded_settlement_count,
        "newly_recorded_count": len(append_statuses),
        "settlement_append_statuses": append_statuses,
        "calibration_append_status": calibration_append,
        "calibration_summary_path": str(paths.calibration_summary),
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
