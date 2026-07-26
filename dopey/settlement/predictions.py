"""Append-only forward prediction records with no early settlement."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from dopey.chronos.market_calendar import is_trading_day
from dopey.protocols.identity import canonical_hash


HYPOTHESIS_NAMES = frozenset({"bull", "bear", "neutral", "unknown"})


def _validated_probabilities(values: Mapping[str, float], field_name: str) -> dict[str, float]:
    names = {str(name) for name in values}
    if names != HYPOTHESIS_NAMES:
        raise ValueError(
            "forward prediction hypothesis classes are incomplete or unexpected: "
            f"field={field_name}, missing={sorted(HYPOTHESIS_NAMES - names)}, "
            f"extra={sorted(names - HYPOTHESIS_NAMES)}"
        )
    normalized = {str(name): float(value) for name, value in values.items()}
    invalid = {
        name: value
        for name, value in normalized.items()
        if not math.isfinite(value) or not 0.0 <= value <= 1.0
    }
    if invalid:
        raise ValueError(
            "forward prediction probabilities must be finite and within [0, 1]: "
            f"field={field_name}, invalid={invalid}"
        )
    total = sum(normalized.values())
    if abs(total - 1.0) > 1e-5:
        raise ValueError(
            "forward prediction probabilities must sum to one: "
            f"field={field_name}, total={total}"
        )
    return normalized


def _future_trading_date(start: date, horizon_trading_days: int) -> date:
    if horizon_trading_days <= 0:
        raise ValueError(
            "settlement horizon must be positive: "
            f"horizon_trading_days={horizon_trading_days}"
        )
    cursor = start
    observed = 0
    while observed < horizon_trading_days:
        cursor += timedelta(days=1)
        if is_trading_day(cursor):
            observed += 1
    return cursor


def build_forward_prediction(
    symbol: str,
    research_event_time: str,
    market_time: str,
    hypotheses: Mapping[str, float],
    final_research_confidence: float,
    final_control: str,
    evidence_ids: tuple[str, ...],
    point_in_time_proof_id: str,
    point_in_time_complete: bool,
    horizon_trading_days: int,
    agent_contributions: Mapping[str, float],
    agent_ablation_hypotheses: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    normalized_hypotheses = _validated_probabilities(hypotheses, "hypotheses")
    normalized_ablations = {
        str(agent_id): _validated_probabilities(values, f"agent_ablation_hypotheses.{agent_id}")
        for agent_id, values in agent_ablation_hypotheses.items()
    }
    confidence = float(final_research_confidence)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError(
            "forward prediction confidence must be finite and within [0, 1]: "
            f"final_research_confidence={final_research_confidence}"
        )
    normalized_contributions = {str(key): float(value) for key, value in agent_contributions.items()}
    invalid_contributions = {
        name: value
        for name, value in normalized_contributions.items()
        if not math.isfinite(value) or not -1.0 <= value <= 1.0
    }
    if invalid_contributions:
        raise ValueError(
            "forward prediction agent contributions must be finite and within [-1, 1]: "
            f"invalid={invalid_contributions}"
        )
    parsed_market_time = datetime.fromisoformat(market_time.replace("Z", "+00:00"))
    if parsed_market_time.tzinfo is None:
        raise ValueError(f"market time requires timezone: market_time={market_time}")
    parsed_event_time = datetime.fromisoformat(research_event_time.replace("Z", "+00:00"))
    if parsed_event_time.tzinfo is None:
        raise ValueError(f"research event time requires timezone: research_event_time={research_event_time}")
    if parsed_event_time < parsed_market_time:
        raise ValueError(
            "research event time cannot precede market time: "
            f"research_event_time={research_event_time}, market_time={market_time}"
        )
    if not point_in_time_proof_id.strip():
        raise ValueError(f"forward prediction requires point-in-time proof identity: symbol={symbol}")
    if point_in_time_complete is not True:
        raise ValueError(f"forward prediction requires complete point-in-time proof: symbol={symbol}")
    settle_date = _future_trading_date(parsed_market_time.date(), horizon_trading_days)
    dominant = max(normalized_hypotheses, key=normalized_hypotheses.__getitem__)
    body: dict[str, Any] = {
        "artifact_type": "vnext_forward_research_prediction",
        "prediction_version": "dopey-vnext-forward-prediction-v1",
        "symbol": symbol,
        "research_event_time": research_event_time,
        "prediction_market_time": market_time,
        "minimum_settlement_date": settle_date.isoformat(),
        "horizon_trading_days": horizon_trading_days,
        "hypotheses": normalized_hypotheses,
        "agent_contributions": normalized_contributions,
        "agent_ablation_hypotheses": normalized_ablations,
        "agent_ablation_precommitted_before_outcome": True,
        "dominant_hypothesis": dominant,
        "final_research_confidence": confidence,
        "research_control": final_control,
        "evidence_ids": list(evidence_ids),
        "point_in_time_proof_id": point_in_time_proof_id,
        "point_in_time_complete": True,
        "prediction_status": "pending_forward_settlement",
        "settlement_policy": "never_grade_before_minimum_settlement_date",
        "contested_truth_required": True,
        "traded": False,
        "promotion_state": "SHADOW_ONLY",
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_trade_evidence": True,
        "not_readiness_evidence": True,
    }
    content_hash = canonical_hash(body)
    return {
        **body,
        "prediction_id": f"vnext-prediction:{content_hash[:24]}",
        "content_hash": content_hash,
    }


def append_prediction(path: Path, prediction: Mapping[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "prediction ledger contains invalid JSON: "
                    f"path={path}, line_number={line_number}"
                ) from exc
            existing[str(record.get("prediction_id", ""))] = str(record.get("content_hash", ""))
    prediction_id = str(prediction.get("prediction_id", ""))
    content_hash = str(prediction.get("content_hash", ""))
    if not prediction_id or not content_hash:
        raise ValueError("prediction requires prediction_id and content_hash")
    if prediction_id in existing:
        if existing[prediction_id] != content_hash:
            raise ValueError(
                "prediction identity conflict: "
                f"prediction_id={prediction_id}, existing_hash={existing[prediction_id]}, new_hash={content_hash}"
            )
        return {"append_status": "already_present_identical", "prediction_id": prediction_id, "path": str(path)}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(prediction), sort_keys=True, ensure_ascii=True) + "\n")
    return {"append_status": "appended", "prediction_id": prediction_id, "path": str(path)}
