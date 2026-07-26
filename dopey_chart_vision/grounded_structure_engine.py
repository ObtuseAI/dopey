"""Deterministic chart structures and blind replay evidence for DOPEY coaching."""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Final, NotRequired, TypedDict

from dopey.protocols.identity import canonical_hash
from dopey_equity_swing.market_structure import (
    Bar,
    average_true_range,
    confirmed_pivots,
    trend_channel,
)


GROUNDED_STRUCTURE_VERSION: Final[str] = "dopey-grounded-chart-structures-v2"
BLIND_REPLAY_VERSION: Final[str] = "dopey-grounded-blind-replay-v2"
SWING_CONFIRMATION_RADIUS: Final[int] = 3
SWEEP_LOOKBACK_BARS: Final[int] = 20
MAX_STRUCTURE_RECORDS: Final[int] = 36
PRICE_QUANTUM: Final[Decimal] = Decimal("0.000001")


class NumericFact(TypedDict):
    level_ref: str
    label: str
    value_decimal: str
    canonical_display: str
    unit: str
    derivation: str
    source_bar_ids: list[str]


class StructureRecord(TypedDict):
    structure_id: str
    structure_hash: str
    definition_id: str
    structure_type: str
    directional_bias: str
    anchor_bar_ids: list[str]
    available_at_bar_id: str
    available_at_date: str
    level_refs: list[str]
    candidate_not_truth: bool
    not_edge_evidence: bool
    trend_direction: NotRequired[str]
    containment_state: NotRequired[str]


def _decimal(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"numeric structure fact must be finite: value={value!r}")
    normalized = Decimal(str(value)).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
    if normalized == Decimal("-0.000000"):
        normalized = Decimal("0.000000")
    return format(normalized, "f")


def _display(value_decimal: str) -> str:
    stripped = value_decimal.rstrip("0").rstrip(".")
    return stripped if stripped not in {"", "-0"} else "0"


def _validated_rows(rows: Sequence[Bar]) -> tuple[Bar, ...]:
    if len(rows) < 60:
        raise ValueError(
            "grounded chart structures require at least sixty bars: "
            f"actual={len(rows)}"
        )
    output: list[Bar] = []
    previous_date = ""
    for index, raw_row in enumerate(rows):
        date = str(raw_row["date"])
        if not date or date <= previous_date:
            raise ValueError(
                "grounded OHLC dates must be unique and strictly increasing: "
                f"index={index}, previous={previous_date!r}, actual={date!r}"
            )
        open_value = float(raw_row["open"])
        high = float(raw_row["high"])
        low = float(raw_row["low"])
        close = float(raw_row["close"])
        volume = int(raw_row["volume"])
        values = (open_value, high, low, close)
        if not all(math.isfinite(value) and value > 0.0 for value in values):
            raise ValueError(f"grounded OHLC prices must be positive and finite: date={date}")
        if high < max(open_value, close, low) or low > min(open_value, close, high):
            raise ValueError(f"grounded OHLC bounds are invalid: date={date}")
        if volume < 0:
            raise ValueError(f"grounded OHLC volume must be non-negative: date={date}")
        output.append(
            Bar(
                date=date,
                open=open_value,
                high=high,
                low=low,
                close=close,
                adjusted_close=float(raw_row.get("adjusted_close", close)),
                volume=volume,
            )
        )
        previous_date = date
    return tuple(output)


def _bar_id(symbol: str, row: Bar) -> str:
    body = {
        "symbol": symbol,
        "date": row["date"],
        "open": _decimal(row["open"]),
        "high": _decimal(row["high"]),
        "low": _decimal(row["low"]),
        "close": _decimal(row["close"]),
        "volume": row["volume"],
    }
    return f"bar:{canonical_hash(body)[:24]}"


def _register_fact(
    facts: dict[str, NumericFact],
    label: str,
    value: float,
    unit: str,
    derivation: str,
    source_bar_ids: Sequence[str],
) -> str:
    value_decimal = _decimal(value)
    identity = {
        "label": label,
        "value_decimal": value_decimal,
        "unit": unit,
        "derivation": derivation,
        "source_bar_ids": list(source_bar_ids),
    }
    level_ref = f"level:{canonical_hash(identity)[:24]}"
    facts[level_ref] = {
        "level_ref": level_ref,
        "label": label,
        "value_decimal": value_decimal,
        "canonical_display": _display(value_decimal),
        "unit": unit,
        "derivation": derivation,
        "source_bar_ids": list(source_bar_ids),
    }
    return level_ref


def _structure(
    definition_id: str,
    structure_type: str,
    directional_bias: str,
    anchor_bar_ids: Sequence[str],
    available_at_bar_id: str,
    available_at_date: str,
    level_refs: Sequence[str],
) -> StructureRecord:
    body = {
        "definition_id": definition_id,
        "structure_type": structure_type,
        "directional_bias": directional_bias,
        "anchor_bar_ids": list(anchor_bar_ids),
        "available_at_bar_id": available_at_bar_id,
        "available_at_date": available_at_date,
        "level_refs": list(level_refs),
        "candidate_not_truth": True,
        "not_edge_evidence": True,
    }
    structure_hash = canonical_hash(body)
    return {
        "structure_id": f"structure:{structure_hash[:24]}",
        "structure_hash": structure_hash,
        **body,
    }


def _confirmed_swing_structures(
    symbol: str,
    rows: tuple[Bar, ...],
    bar_ids: tuple[str, ...],
    facts: dict[str, NumericFact],
) -> tuple[list[StructureRecord], list[dict[str, Any]]]:
    pivots = confirmed_pivots(list(rows), SWING_CONFIRMATION_RADIUS)
    records: list[StructureRecord] = []
    for pivot in pivots[-12:]:
        index = int(pivot["bar_index"])
        confirmed_index = index + SWING_CONFIRMATION_RADIUS
        role = str(pivot["role"])
        level_ref = _register_fact(
            facts,
            f"confirmed_{role}_{rows[index]['date']}",
            float(pivot["price"]),
            "price",
            f"confirmed_fractal_radius_{SWING_CONFIRMATION_RADIUS}",
            (bar_ids[index], bar_ids[confirmed_index]),
        )
        records.append(
            _structure(
                f"confirmed_swing_fractal_radius_{SWING_CONFIRMATION_RADIUS}_v1",
                f"swing_{'low' if role == 'support' else 'high'}",
                "bullish" if role == "support" else "bearish",
                (bar_ids[index],),
                bar_ids[confirmed_index],
                rows[confirmed_index]["date"],
                (level_ref,),
            )
        )
    return records, pivots


def _sequence_structure(
    rows: tuple[Bar, ...],
    bar_ids: tuple[str, ...],
    pivots: list[dict[str, Any]],
    facts: dict[str, NumericFact],
) -> list[StructureRecord]:
    highs = [pivot for pivot in pivots if pivot["role"] == "resistance"]
    lows = [pivot for pivot in pivots if pivot["role"] == "support"]
    if len(highs) < 2 or len(lows) < 2:
        return []
    selected = (highs[-2], highs[-1], lows[-2], lows[-1])
    high_state = "higher_high" if float(highs[-1]["price"]) > float(highs[-2]["price"]) else "lower_high"
    low_state = "higher_low" if float(lows[-1]["price"]) > float(lows[-2]["price"]) else "lower_low"
    if high_state == "higher_high" and low_state == "higher_low":
        bias = "bullish"
    elif high_state == "lower_high" and low_state == "lower_low":
        bias = "bearish"
    else:
        bias = "neutral"
    level_refs = [
        _register_fact(
            facts,
            f"market_sequence_{index}_{str(pivot['role'])}",
            float(pivot["price"]),
            "price",
            "last_two_confirmed_highs_and_lows",
            (bar_ids[int(pivot["bar_index"])],),
        )
        for index, pivot in enumerate(selected)
    ]
    availability_index = max(
        int(pivot["bar_index"]) + SWING_CONFIRMATION_RADIUS for pivot in selected
    )
    return [
        _structure(
            f"confirmed_hh_hl_lh_ll_radius_{SWING_CONFIRMATION_RADIUS}_v1",
            f"{high_state}_{low_state}",
            bias,
            tuple(bar_ids[int(pivot["bar_index"])] for pivot in selected),
            bar_ids[availability_index],
            rows[availability_index]["date"],
            tuple(level_refs),
        )
    ]


def _active_fair_value_gaps(
    rows: tuple[Bar, ...],
    bar_ids: tuple[str, ...],
    facts: dict[str, NumericFact],
) -> list[StructureRecord]:
    records: list[StructureRecord] = []
    start = max(2, len(rows) - 120)
    for index in range(start, len(rows)):
        left = rows[index - 2]
        right = rows[index]
        if right["low"] > left["high"]:
            low = left["high"]
            high = right["low"]
            filled = any(row["low"] <= low for row in rows[index + 1 :])
            bias = "bullish"
        elif right["high"] < left["low"]:
            low = right["high"]
            high = left["low"]
            filled = any(row["high"] >= high for row in rows[index + 1 :])
            bias = "bearish"
        else:
            continue
        if filled:
            continue
        source_ids = (bar_ids[index - 2], bar_ids[index - 1], bar_ids[index])
        low_ref = _register_fact(
            facts,
            f"active_{bias}_fair_value_gap_low_{right['date']}",
            low,
            "price",
            "three_candle_inefficiency_lower_bound",
            source_ids,
        )
        high_ref = _register_fact(
            facts,
            f"active_{bias}_fair_value_gap_high_{right['date']}",
            high,
            "price",
            "three_candle_inefficiency_upper_bound",
            source_ids,
        )
        records.append(
            _structure(
                "three_candle_unfilled_fair_value_gap_v1",
                "fair_value_gap_candidate",
                bias,
                source_ids,
                bar_ids[index],
                right["date"],
                (low_ref, high_ref),
            )
        )
    return records[-6:]


def _liquidity_sweeps(
    rows: tuple[Bar, ...],
    bar_ids: tuple[str, ...],
    facts: dict[str, NumericFact],
) -> list[StructureRecord]:
    records: list[StructureRecord] = []
    start = max(SWEEP_LOOKBACK_BARS, len(rows) - 100)
    for index in range(start, len(rows)):
        prior = rows[index - SWEEP_LOOKBACK_BARS : index]
        prior_high = max(row["high"] for row in prior)
        prior_low = min(row["low"] for row in prior)
        current = rows[index]
        if current["high"] > prior_high and current["close"] < prior_high:
            bias = "bearish"
            swept_level = prior_high
            extreme = current["high"]
        elif current["low"] < prior_low and current["close"] > prior_low:
            bias = "bullish"
            swept_level = prior_low
            extreme = current["low"]
        else:
            continue
        source_ids = (bar_ids[index - SWEEP_LOOKBACK_BARS], bar_ids[index])
        level_ref = _register_fact(
            facts,
            f"{bias}_liquidity_sweep_reference_{current['date']}",
            swept_level,
            "price",
            f"wick_beyond_trailing_{SWEEP_LOOKBACK_BARS}_bar_extreme_and_close_back_inside",
            source_ids,
        )
        extreme_ref = _register_fact(
            facts,
            f"{bias}_liquidity_sweep_extreme_{current['date']}",
            extreme,
            "price",
            "observed_sweep_wick_extreme",
            (bar_ids[index],),
        )
        records.append(
            _structure(
                f"close_back_inside_liquidity_sweep_{SWEEP_LOOKBACK_BARS}_bar_v1",
                "liquidity_sweep_candidate",
                bias,
                source_ids,
                bar_ids[index],
                current["date"],
                (level_ref, extreme_ref),
            )
        )
    return records[-6:]


def _rolling_atr(rows: tuple[Bar, ...], end_index: int) -> float:
    return average_true_range(list(rows[: end_index + 1]), 14)


def _order_block_candidates(
    rows: tuple[Bar, ...],
    bar_ids: tuple[str, ...],
    facts: dict[str, NumericFact],
) -> list[StructureRecord]:
    records: list[StructureRecord] = []
    start = max(15, len(rows) - 100)
    for index in range(start, len(rows)):
        current = rows[index]
        prior = rows[index - 1]
        atr = _rolling_atr(rows, index)
        body = abs(current["close"] - current["open"])
        if atr <= 0.0 or body < atr:
            continue
        if current["close"] > prior["high"] and prior["close"] < prior["open"]:
            bias = "bullish"
            zone_low = prior["low"]
            zone_high = prior["open"]
        elif current["close"] < prior["low"] and prior["close"] > prior["open"]:
            bias = "bearish"
            zone_low = prior["open"]
            zone_high = prior["high"]
        else:
            continue
        source_ids = (bar_ids[index - 1], bar_ids[index])
        low_ref = _register_fact(
            facts,
            f"{bias}_order_block_candidate_low_{prior['date']}",
            zone_low,
            "price",
            "opposite_candle_before_atr_displacement_lower_bound",
            source_ids,
        )
        high_ref = _register_fact(
            facts,
            f"{bias}_order_block_candidate_high_{prior['date']}",
            zone_high,
            "price",
            "opposite_candle_before_atr_displacement_upper_bound",
            source_ids,
        )
        records.append(
            _structure(
                "opposite_candle_before_one_atr_displacement_order_block_candidate_v1",
                "order_block_candidate",
                bias,
                source_ids,
                bar_ids[index],
                current["date"],
                (low_ref, high_ref),
            )
        )
    return records[-6:]


def _fibonacci_structure(
    rows: tuple[Bar, ...],
    bar_ids: tuple[str, ...],
    pivots: list[dict[str, Any]],
    facts: dict[str, NumericFact],
) -> list[StructureRecord]:
    selected: tuple[dict[str, Any], dict[str, Any]] | None = None
    for right_index in range(len(pivots) - 1, 0, -1):
        right = pivots[right_index]
        left = pivots[right_index - 1]
        if left["role"] != right["role"]:
            selected = (left, right)
            break
    if selected is None:
        return []
    left, right = selected
    left_value = float(left["price"])
    right_value = float(right["price"])
    span = abs(right_value - left_value)
    if span <= 0.0:
        return []
    direction = "bullish" if right_value > left_value else "bearish"
    left_index = int(left["bar_index"])
    right_index = int(right["bar_index"])
    source_ids = (bar_ids[left_index], bar_ids[right_index])
    refs = [
        _register_fact(
            facts,
            f"latest_confirmed_leg_{label}",
            value,
            "price",
            "latest_opposite_confirmed_pivot_leg_anchor",
            source_ids,
        )
        for label, value in (("start", left_value), ("end", right_value))
    ]
    ratios = (0.236, 0.382, 0.5, 0.618, 0.786)
    for ratio in ratios:
        value = right_value - span * ratio if direction == "bullish" else right_value + span * ratio
        refs.append(
            _register_fact(
                facts,
                f"latest_confirmed_leg_fibonacci_{str(ratio).replace('.', '_')}",
                value,
                "price",
                "declared_latest_opposite_confirmed_pivot_leg_retracement",
                source_ids,
            )
        )
    availability_index = right_index + SWING_CONFIRMATION_RADIUS
    return [
        _structure(
            "latest_opposite_confirmed_pivot_leg_fibonacci_v1",
            "fibonacci_retracement_set",
            direction,
            source_ids,
            bar_ids[availability_index],
            rows[availability_index]["date"],
            tuple(refs),
        )
    ]


def _trend_channel_structure(
    rows: tuple[Bar, ...],
    bar_ids: tuple[str, ...],
    pivots: list[dict[str, Any]],
    facts: dict[str, NumericFact],
) -> list[StructureRecord]:
    lookback_bars = 90
    channel = trend_channel(list(rows), pivots, lookback_bars)
    if channel["channel_status"] != "confirmed":
        return []
    start_index = max(len(rows) - lookback_bars, 0)
    consumed_pivots = tuple(
        pivot
        for pivot in pivots
        if pivot["role"] in {"support", "resistance"}
        and int(pivot["bar_index"]) >= start_index
    )
    pivot_source_ids = tuple(
        bar_ids[int(pivot["bar_index"])]
        for pivot in consumed_pivots
    )
    source_ids = tuple(dict.fromkeys((*pivot_source_ids, bar_ids[-1])))
    lower_ref = _register_fact(
        facts,
        "confirmed_trend_channel_lower_bound",
        float(channel["lower_bound"]),
        "price",
        "theil_sen_confirmed_pivot_channel_lower_bound",
        source_ids,
    )
    upper_ref = _register_fact(
        facts,
        "confirmed_trend_channel_upper_bound",
        float(channel["upper_bound"]),
        "price",
        "theil_sen_confirmed_pivot_channel_upper_bound",
        source_ids,
    )
    direction = str(channel["direction"])
    channel_position = float(channel["channel_position"])
    containment_state = (
        "below_lower_bound"
        if channel_position < 0.0
        else "above_upper_bound"
        if channel_position > 1.0
        else "contained"
    )
    position_ref = _register_fact(
        facts,
        "confirmed_trend_channel_position",
        channel_position,
        "ratio",
        "current_close_position_within_confirmed_pivot_channel",
        source_ids,
    )
    bias = (
        "bullish"
        if containment_state == "contained" and direction == "uptrend"
        else "bearish"
        if containment_state == "contained" and direction == "downtrend"
        else "neutral"
    )
    record = _structure(
        "confirmed_pivot_theil_sen_trend_channel_containment_gated_v2",
        "trend_channel",
        bias,
        source_ids,
        bar_ids[-1],
        rows[-1]["date"],
        (lower_ref, upper_ref, position_ref),
    )
    return [
        {
            **record,
            "trend_direction": direction,
            "containment_state": containment_state,
        }
    ]


def build_grounded_structure_evidence(
    symbol: str,
    timeframe: str,
    rows: Sequence[Bar],
    data_version: str,
) -> dict[str, Any]:
    """Build viewport-independent, versioned structures from raw OHLCV only."""

    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip().lower()
    if not normalized_symbol:
        raise ValueError("grounded chart structure symbol must not be empty")
    if normalized_timeframe not in {"daily", "weekly", "monthly"}:
        raise ValueError(f"unsupported grounded chart timeframe: {timeframe!r}")
    validated = _validated_rows(rows)
    bar_ids = tuple(_bar_id(normalized_symbol, row) for row in validated)
    snapshot_body = [
        {
            "bar_id": bar_id,
            "date": row["date"],
            "open": _decimal(row["open"]),
            "high": _decimal(row["high"]),
            "low": _decimal(row["low"]),
            "close": _decimal(row["close"]),
            "volume": row["volume"],
        }
        for row, bar_id in zip(validated, bar_ids)
    ]
    facts: dict[str, NumericFact] = {}
    current_refs = [
        _register_fact(
            facts,
            f"latest_{field}",
            float(validated[-1][field]),
            "price",
            f"observed_latest_bar_{field}",
            (bar_ids[-1],),
        )
        for field in ("open", "high", "low", "close")
    ]
    structures, pivots = _confirmed_swing_structures(
        normalized_symbol,
        validated,
        bar_ids,
        facts,
    )
    structures.extend(_sequence_structure(validated, bar_ids, pivots, facts))
    structures.extend(_active_fair_value_gaps(validated, bar_ids, facts))
    structures.extend(_liquidity_sweeps(validated, bar_ids, facts))
    structures.extend(_order_block_candidates(validated, bar_ids, facts))
    structures.extend(_fibonacci_structure(validated, bar_ids, pivots, facts))
    structures.extend(_trend_channel_structure(validated, bar_ids, pivots, facts))
    structures.append(
        _structure(
            "observed_latest_ohlc_bar_v1",
            "current_bar",
            "neutral",
            (bar_ids[-1],),
            bar_ids[-1],
            validated[-1]["date"],
            tuple(current_refs),
        )
    )
    ordered_structures = sorted(
        structures,
        key=lambda record: (
            record["available_at_date"],
            record["structure_type"],
            record["structure_id"],
        ),
    )[-MAX_STRUCTURE_RECORDS:]
    referenced_facts = {
        level_ref
        for record in ordered_structures
        for level_ref in record["level_refs"]
    }
    numeric_facts = [facts[level_ref] for level_ref in sorted(referenced_facts)]
    body: dict[str, Any] = {
        "artifact_type": "grounded_chart_structure_evidence",
        "schema_version": GROUNDED_STRUCTURE_VERSION,
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "as_of": validated[-1]["date"],
        "data_version": data_version,
        "visible_ohlcv_hash": canonical_hash(snapshot_body),
        "visible_start_date": validated[0]["date"],
        "visible_end_date": validated[-1]["date"],
        "visible_bar_count": len(validated),
        "structures": ordered_structures,
        "numeric_facts": numeric_facts,
        "structure_count": len(ordered_structures),
        "numeric_fact_count": len(numeric_facts),
        "definition_policy": "explicit_versioned_candidates_not_smart_money_truth",
        "viewport_is_detector_input": False,
        "image_pixels_are_detector_input": False,
        "raw_ohlcv_is_detector_input": True,
        "same_visible_ohlcv_implies_identical_levels": True,
        "fibonacci_anchor_policy": "latest_opposite_confirmed_pivot_leg",
        "paper_only": True,
        "live_blocked": True,
        "not_trade_decision": True,
        "not_edge_evidence": True,
    }
    return {**body, "evidence_hash": canonical_hash(body)}


def build_blind_replay_evidence(
    symbol: str,
    timeframe: str,
    rows: Sequence[Bar],
    data_version: str,
    reveal_bar_count: int,
) -> dict[str, Any]:
    """Freeze a historical prefix, then reveal a separate underlying-only outcome window."""

    validated = _validated_rows(rows)
    if reveal_bar_count < 1 or len(validated) - reveal_bar_count < 60:
        raise ValueError(
            "blind replay window is invalid: "
            f"bars={len(validated)}, reveal_bar_count={reveal_bar_count}"
        )
    frozen = validated[:-reveal_bar_count]
    revealed = validated[-reveal_bar_count:]
    frozen_evidence = build_grounded_structure_evidence(
        symbol,
        timeframe,
        frozen,
        f"{data_version}:frozen:{frozen[-1]['date']}",
    )
    entry = float(frozen[-1]["close"])
    ending = float(revealed[-1]["close"])
    highs = [float(row["high"]) for row in revealed]
    lows = [float(row["low"]) for row in revealed]
    outcome = {
        "underlying_close_return_decimal": _decimal(ending / entry - 1.0),
        "underlying_max_favorable_excursion_decimal": _decimal(max(highs) / entry - 1.0),
        "underlying_max_adverse_excursion_decimal": _decimal(min(lows) / entry - 1.0),
        "option_outcome_status": "blocked_missing_point_in_time_option_evidence",
        "not_option_pnl_evidence": True,
    }
    body: dict[str, Any] = {
        "artifact_type": "grounded_blind_chart_replay",
        "schema_version": BLIND_REPLAY_VERSION,
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe.strip().lower(),
        "decision_cutoff": frozen[-1]["date"],
        "reveal_end": revealed[-1]["date"],
        "reveal_bar_count": reveal_bar_count,
        "frozen_evidence": frozen_evidence,
        "reveal_window_hash": canonical_hash(
            [
                {
                    "date": row["date"],
                    "open": _decimal(row["open"]),
                    "high": _decimal(row["high"]),
                    "low": _decimal(row["low"]),
                    "close": _decimal(row["close"]),
                    "volume": row["volume"],
                }
                for row in revealed
            ]
        ),
        "outcome": outcome,
        "decision_inputs_exclude_reveal_window": True,
        "replay_outcome_separate_from_frozen_decision_packet": True,
        "future_data_visible_during_frozen_detection": False,
        "underlying_only": True,
        "paper_only": True,
        "live_blocked": True,
        "not_trade_decision": True,
        "not_edge_evidence": True,
    }
    return {**body, "replay_hash": canonical_hash(body)}
