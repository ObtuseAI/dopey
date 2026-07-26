"""Append-only forward settlement for squeeze and bubble research signals."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean
from typing import Any

from dopey.protocols.identity import canonical_hash


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"settlement ledger contains invalid JSON: path={path}, line={line_number}, error={error}"
            ) from error
        if not isinstance(record, dict):
            raise TypeError(
                f"settlement ledger row must be an object: path={path}, line={line_number}"
            )
        records.append(record)
    return records


def _append_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
            )


def _signal_record(
    assessment: Mapping[str, Any],
    lane: str,
    decision_at_utc: str,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    lane_record = assessment[lane]
    direction = str(lane_record["direction"])
    body = {
        "artifact_type": "squeeze_bubble_forward_signal",
        "engine_version": str(assessment["engine_version"]),
        "assessment_id": str(assessment["assessment_id"]),
        "lane": lane,
        "symbol": str(assessment["symbol"]),
        "market_data_as_of": str(assessment["as_of_date"]),
        "decision_at_utc": decision_at_utc,
        "direction": direction,
        "score": float(lane_record["score"]),
        "lane_status": str(lane_record["status"]),
        "evidence_completeness": float(lane_record["evidence_completeness"]),
        "horizons": horizons,
        "entry_reference_price": float(
            lane_record["geometry"]["entry_reference_price"]
        ),
        "is_trade_signal": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    identity = {
        key: value
        for key, value in body.items()
        if key != "decision_at_utc"
    }
    return {
        **body,
        "signal_id": f"squeeze-bubble-signal:{canonical_hash(identity)[:24]}",
    }


def append_forward_signals(
    assessments: Sequence[Mapping[str, Any]],
    decision_at_utc: str,
    horizons: tuple[int, ...],
    ledger_path: Path,
) -> dict[str, Any]:
    """Record candidate and fragility-monitor signals once by content identity."""

    existing_ids = {
        str(record.get("signal_id", "")) for record in _read_jsonl(ledger_path)
    }
    candidates: list[dict[str, Any]] = []
    for assessment in assessments:
        squeeze_status = str(assessment["squeeze"]["status"])
        if squeeze_status == "squeeze_candidate_requires_existing_execution_gates":
            candidates.append(
                _signal_record(assessment, "squeeze", decision_at_utc, horizons)
            )
        bubble_status = str(assessment["bubble"]["status"])
        if bubble_status in {
            "bubble_fragility_monitor_wait_for_unwind",
            "bubble_unwind_candidate_requires_options_control_and_existing_gates",
        }:
            candidates.append(
                _signal_record(assessment, "bubble", decision_at_utc, horizons)
            )
    fresh = [
        record for record in candidates if str(record["signal_id"]) not in existing_ids
    ]
    _append_jsonl(ledger_path, fresh)
    return {
        "artifact_type": "squeeze_bubble_forward_recording",
        "candidate_signal_count": len(candidates),
        "appended_signal_count": len(fresh),
        "already_recorded_count": len(candidates) - len(fresh),
        "ledger_path": str(ledger_path),
        "paper_only": True,
        "live_blocked": True,
    }


def _settle_signal(
    signal: Mapping[str, Any],
    bars: Sequence[Mapping[str, float]],
    horizon: int,
) -> dict[str, Any] | None:
    decision_date = str(signal["decision_at_utc"])[:10]
    entry_index = next(
        (
            index
            for index, bar in enumerate(bars)
            if str(bar.get("date", "")) > decision_date
        ),
        None,
    )
    if entry_index is None:
        return None
    exit_index = entry_index + horizon
    if exit_index >= len(bars):
        return None
    entry = float(bars[entry_index]["close"])
    exit_price = float(bars[exit_index]["close"])
    if entry <= 0.0 or exit_price <= 0.0:
        raise ValueError(
            "forward settlement requires positive close prices: "
            f"symbol={signal['symbol']}, entry={entry}, exit={exit_price}"
        )
    raw_return = exit_price / entry - 1.0
    direction = str(signal["direction"])
    if direction not in {"bullish", "bearish"}:
        raise ValueError(
            f"forward settlement direction is invalid: signal_id={signal['signal_id']}, direction={direction}"
        )
    directional_return = raw_return if direction == "bullish" else -raw_return
    path_returns = [
        float(bar["close"]) / entry - 1.0 for bar in bars[entry_index : exit_index + 1]
    ]
    directional_path = (
        path_returns
        if direction == "bullish"
        else [-value for value in path_returns]
    )
    body = {
        "artifact_type": "squeeze_bubble_forward_settlement",
        "signal_id": str(signal["signal_id"]),
        "assessment_id": str(signal["assessment_id"]),
        "lane": str(signal["lane"]),
        "symbol": str(signal["symbol"]),
        "direction": direction,
        "score": float(signal["score"]),
        "evidence_completeness": float(signal["evidence_completeness"]),
        "entry_date": str(bars[entry_index]["date"]),
        "settle_date": str(bars[exit_index]["date"]),
        "horizon": horizon,
        "entry_close": entry,
        "exit_close": exit_price,
        "raw_underlying_return": round(raw_return, 8),
        "directional_return": round(directional_return, 8),
        "maximum_favorable_excursion": round(max(directional_path), 8),
        "maximum_adverse_excursion": round(min(directional_path), 8),
        "hit": directional_return > 0.0,
        "not_realized_trade_pnl": True,
        "paper_only": True,
        "live_blocked": True,
    }
    return {
        **body,
        "settlement_id": f"squeeze-bubble-settlement:{canonical_hash(body)[:24]}",
    }


def settle_forward_signals(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, float]]],
    signal_ledger_path: Path,
    settlement_ledger_path: Path,
) -> dict[str, Any]:
    """Settle every matured signal-horizon pair without rewriting history."""

    signals = _read_jsonl(signal_ledger_path)
    existing = _read_jsonl(settlement_ledger_path)
    settled_keys = {
        (str(record.get("signal_id", "")), int(record.get("horizon", 0)))
        for record in existing
    }
    fresh: list[dict[str, Any]] = []
    pending = 0
    for signal in signals:
        symbol = str(signal["symbol"])
        bars = bars_by_symbol.get(symbol)
        if bars is None:
            pending += len(signal["horizons"])
            continue
        for raw_horizon in signal["horizons"]:
            horizon = int(raw_horizon)
            key = (str(signal["signal_id"]), horizon)
            if key in settled_keys:
                continue
            settlement = _settle_signal(signal, bars, horizon)
            if settlement is None:
                pending += 1
            else:
                fresh.append(settlement)
    _append_jsonl(settlement_ledger_path, fresh)
    return {
        "artifact_type": "squeeze_bubble_forward_settlement_run",
        "new_settlement_count": len(fresh),
        "total_settlement_count": len(existing) + len(fresh),
        "pending_signal_horizon_count": pending,
        "settlement_ledger_path": str(settlement_ledger_path),
        "paper_only": True,
        "live_blocked": True,
    }


def _bucket(
    records: Sequence[Mapping[str, Any]],
    minimum_settled_observations: int,
) -> dict[str, Any]:
    count = len(records)
    directional_returns = [float(record["directional_return"]) for record in records]
    hits = sum(1 for record in records if record.get("hit") is True)
    rated = count >= minimum_settled_observations
    return {
        "settled_observations": count,
        "hit_rate": round(hits / count, 6) if count else None,
        "mean_directional_return": (
            round(fmean(directional_returns), 8) if directional_returns else None
        ),
        "mean_maximum_favorable_excursion": (
            round(
                fmean(float(record["maximum_favorable_excursion"]) for record in records),
                8,
            )
            if records
            else None
        ),
        "mean_maximum_adverse_excursion": (
            round(
                fmean(float(record["maximum_adverse_excursion"]) for record in records),
                8,
            )
            if records
            else None
        ),
        "research_evidence_status": (
            "rated_forward_observations"
            if rated
            else "unrated_insufficient_forward_observations"
        ),
        "minimum_settled_observations": minimum_settled_observations,
        "strategy_promotion_allowed": False,
    }


def build_forward_evidence_report(
    settlement_ledger_path: Path,
    minimum_settled_observations: int,
) -> dict[str, Any]:
    """Summarize evidence by lane and horizon, never as realized P&L."""

    settlements = _read_jsonl(settlement_ledger_path)
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in settlements:
        grouped.setdefault(
            (str(record["lane"]), int(record["horizon"])),
            [],
        ).append(record)
    buckets = {
        f"{lane}:{horizon}": _bucket(records, minimum_settled_observations)
        for (lane, horizon), records in sorted(grouped.items())
    }
    rated_bucket_count = sum(
        1
        for bucket in buckets.values()
        if bucket["research_evidence_status"] == "rated_forward_observations"
    )
    return {
        "artifact_type": "squeeze_bubble_forward_evidence_report",
        "evidence_version": "dopey-squeeze-bubble-forward-evidence-v1",
        "settlement_count": len(settlements),
        "bucket_count": len(buckets),
        "rated_bucket_count": rated_bucket_count,
        "buckets": buckets,
        "overall_evidence_status": (
            "rated_buckets_present_no_automatic_promotion"
            if rated_bucket_count
            else "unrated_insufficient_forward_observations"
        ),
        "adaptive_threshold_mutation_allowed": False,
        "strategy_promotion_allowed": False,
        "not_realized_trade_pnl": True,
        "paper_only": True,
        "live_blocked": True,
    }
