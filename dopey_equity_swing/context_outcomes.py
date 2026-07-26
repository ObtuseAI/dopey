"""Resolve matured forward context decisions without mutating the decision ledger."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .market_structure import Bar


def load_jsonl_records(path: Path, identifier_field: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict) or identifier_field not in parsed:
                raise ValueError(
                    f"JSONL row is invalid: path={path}, line={line_number}, required_field={identifier_field}"
                )
            identifier = str(parsed[identifier_field])
            if identifier in identifiers:
                raise ValueError(f"duplicate JSONL identifier: path={path}, field={identifier_field}, value={identifier}")
            identifiers.add(identifier)
            records.append(parsed)
    return records


def build_matured_context_outcomes(
    decisions: list[dict[str, Any]],
    histories: dict[str, list[Bar]],
    resolved_decision_ids: set[str],
    resolution_as_of: str,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for decision in decisions:
        decision_id = str(decision["decision_id"])
        if decision_id in resolved_decision_ids:
            continue
        symbol = str(decision["symbol"])
        rows = histories.get(symbol)
        if not rows:
            continue
        market_as_of = str(decision["market_as_of"])
        index_by_date = {row["date"]: index for index, row in enumerate(rows)}
        if market_as_of not in index_by_date:
            continue
        start_index = index_by_date[market_as_of]
        horizon = int(decision.get("expected_hold_trading_days") or 0)
        if horizon < 1 or len(rows) <= start_index + horizon:
            continue
        future = rows[start_index + 1 : start_index + horizon + 1]
        outcome = resolve_decision_path(decision, future)
        outcomes.append(
            {
                "artifact_type": "external_context_forward_outcome",
                "decision_id": decision_id,
                "symbol": symbol,
                "market_as_of": market_as_of,
                "resolution_as_of": resolution_as_of,
                "horizon_end_date": future[-1]["date"],
                "expected_hold_trading_days": horizon,
                **outcome,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return outcomes


def resolve_decision_path(decision: dict[str, Any], future: list[Bar]) -> dict[str, Any]:
    entry = float(decision["entry_reference_price"])
    direction = str(decision["equity_direction"])
    target = _optional_float(decision.get("target_price"))
    invalidation = _optional_float(decision.get("invalidation_price"))
    if entry <= 0.0 or direction not in {"bullish", "bearish", "neutral"}:
        raise ValueError(f"invalid context decision outcome inputs: entry={entry}, direction={direction}")
    target_index = _first_hit_index(future, direction, target, True)
    invalidation_index = _first_hit_index(future, direction, invalidation, False)
    if target_index is not None and invalidation_index is not None and target_index == invalidation_index:
        label = "inconclusive_same_bar_target_and_invalidation"
    elif target_index is not None and (invalidation_index is None or target_index < invalidation_index):
        label = "target_hit_before_invalidation"
    elif invalidation_index is not None:
        label = "invalidation_hit_before_target"
    else:
        final_return = future[-1]["close"] / entry - 1.0
        signed_return = final_return if direction == "bullish" else -final_return if direction == "bearish" else 0.0
        label = "positive_horizon_return" if signed_return > 0.0 else "negative_horizon_return" if signed_return < 0.0 else "flat_horizon_return"
    favorable, adverse = _excursions(direction, entry, future)
    final_return = future[-1]["close"] / entry - 1.0
    signed_return = final_return if direction == "bullish" else -final_return if direction == "bearish" else 0.0
    return {
        "outcome_label": label,
        "signed_underlying_return": round(signed_return, 6),
        "max_favorable_excursion": round(favorable, 6),
        "max_adverse_excursion": round(adverse, 6),
        "target_hit_index": target_index,
        "invalidation_hit_index": invalidation_index,
        "outcome_source": "validated_underlying_daily_ohlcv_not_option_pnl",
    }


def append_outcome_records(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {str(record["decision_id"]) for record in load_jsonl_records(path, "decision_id")}
    new_records = [record for record in records if str(record["decision_id"]) not in existing]
    with path.open("a", encoding="utf-8") as handle:
        for record in new_records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return len(new_records)


def _first_hit_index(future: list[Bar], direction: str, price: float | None, target: bool) -> int | None:
    if price is None:
        return None
    for index, row in enumerate(future, start=1):
        if direction == "bullish":
            hit = row["high"] >= price if target else row["low"] <= price
        elif direction == "bearish":
            hit = row["low"] <= price if target else row["high"] >= price
        else:
            hit = False
        if hit:
            return index
    return None


def _excursions(direction: str, entry: float, future: list[Bar]) -> tuple[float, float]:
    if direction == "bullish":
        return max(row["high"] / entry - 1.0 for row in future), min(row["low"] / entry - 1.0 for row in future)
    if direction == "bearish":
        return 1.0 - min(row["low"] for row in future) / entry, 1.0 - max(row["high"] for row in future) / entry
    return 0.0, 0.0


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
