"""Leak-safe reverse engineering of interpretable swing rules from historical outcomes."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .market_structure import Bar, average_true_range


RulePredicate = Callable[[dict[str, float]], bool]

RULES: dict[str, tuple[str, RulePredicate, list[str]]] = {
    "bull_channel_pullback": (
        "bullish",
        lambda feature: feature["ma_alignment"] == 1.0
        and feature["return_60d"] > 0.0
        and feature["range_position_60d"] <= 0.48
        and feature["support_distance_atr"] <= 4.5,
        ["ma20_gt_ma50_gt_ma200", "return_60d_gt_0", "range_position_60d_lte_0_48", "support_distance_atr_lte_4_5"],
    ),
    "bull_support_reversal": (
        "bullish",
        lambda feature: feature["return_60d"] > 0.0
        and feature["return_5d"] >= -0.03
        and feature["support_distance_atr"] <= 2.0,
        ["return_60d_gt_0", "return_5d_gte_minus_0_03", "support_distance_atr_lte_2"],
    ),
    "bull_breakout_continuation": (
        "bullish",
        lambda feature: feature["ma_alignment"] == 1.0
        and feature["range_position_60d"] >= 0.80
        and feature["volume_z_20d"] >= 0.0,
        ["ma20_gt_ma50_gt_ma200", "range_position_60d_gte_0_80", "volume_z_20d_gte_0"],
    ),
    "bear_channel_rally": (
        "bearish",
        lambda feature: feature["ma_alignment"] == -1.0
        and feature["return_60d"] < 0.0
        and feature["range_position_60d"] >= 0.52
        and feature["resistance_distance_atr"] <= 4.5,
        ["ma20_lt_ma50_lt_ma200", "return_60d_lt_0", "range_position_60d_gte_0_52", "resistance_distance_atr_lte_4_5"],
    ),
    "bear_resistance_reversal": (
        "bearish",
        lambda feature: feature["return_60d"] < 0.0
        and feature["return_5d"] <= 0.03
        and feature["resistance_distance_atr"] <= 2.0,
        ["return_60d_lt_0", "return_5d_lte_0_03", "resistance_distance_atr_lte_2"],
    ),
    "bear_breakdown_continuation": (
        "bearish",
        lambda feature: feature["ma_alignment"] == -1.0
        and feature["range_position_60d"] <= 0.20
        and feature["volume_z_20d"] >= 0.0,
        ["ma20_lt_ma50_lt_ma200", "range_position_60d_lte_0_20", "volume_z_20d_gte_0"],
    ),
}


def load_trade_evidence(path: Path) -> tuple[set[tuple[str, str, str]], list[dict[str, Any]]]:
    if not path.exists():
        raise FileNotFoundError(f"backtest trade evidence is missing: {path}")
    return build_trade_evidence(_iter_trade_evidence(path))


def _iter_trade_evidence(path: Path) -> Iterator[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError(f"backtest trade row must be an object: {path}:{line_number}")
            yield parsed


def build_trade_evidence(
    records: Iterable[dict[str, object]],
) -> tuple[set[tuple[str, str, str]], list[dict[str, Any]]]:
    emitted: set[tuple[str, str, str]] = set()
    groups: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"trade_count": 0.0, "win_count": 0.0, "return_sum": 0.0, "mfe_sum": 0.0, "mae_sum": 0.0}
    )
    for record in records:
        symbol = str(record["symbol"])
        signal_date = str(record["signal_date"])
        strategy = str(record["candidate_strategy"])
        direction = "bullish" if strategy == "long_call" else "bearish" if strategy == "long_put" else "unknown"
        if direction != "unknown":
            emitted.add((symbol, signal_date, direction))
        key = (str(record.get("signal_family", "unknown")), strategy)
        group = groups[key]
        group["trade_count"] += 1.0
        group["win_count"] += float(str(record.get("win_loss_marker", "")).startswith("win"))
        group["return_sum"] += float(record.get("trade_return_model_units", 0.0))
        group["mfe_sum"] += float(record.get("max_favorable_excursion", 0.0))
        group["mae_sum"] += float(record.get("max_adverse_excursion", 0.0))
    fingerprints = [_fingerprint(key, values) for key, values in sorted(groups.items())]
    return emitted, fingerprints


def build_retrospective_events(
    histories: dict[str, list[Bar]],
    emitted_signals: set[tuple[str, str, str]],
    sample_stride: int,
    future_horizon: int,
) -> list[dict[str, Any]]:
    if sample_stride < 1 or future_horizon < 1:
        raise ValueError(f"sample_stride and future_horizon must be positive: stride={sample_stride}, horizon={future_horizon}")
    events: list[dict[str, Any]] = []
    for symbol, rows in sorted(histories.items()):
        if len(rows) < 200 + future_horizon:
            continue
        for index in range(199, len(rows) - future_horizon, sample_stride):
            history = rows[index - 199 : index + 1]
            future = rows[index + 1 : index + future_horizon + 1]
            features = build_past_only_features(history)
            for direction in ("bullish", "bearish"):
                outcome = _future_outcome(history[-1], future, direction, float(features["atr_pct_14d"]))
                matching_rules = [
                    rule_name
                    for rule_name, (rule_direction, predicate, _) in RULES.items()
                    if rule_direction == direction and predicate(features)
                ]
                emitted = (symbol, history[-1]["date"], direction) in emitted_signals
                events.append(
                    {
                        "artifact_type": "retrospective_swing_event",
                        "symbol": symbol,
                        "observation_date": history[-1]["date"],
                        "direction": direction,
                        "future_horizon_trading_days": future_horizon,
                        "features_use_past_only": True,
                        "future_label_retrospective_only": True,
                        "features": features,
                        "matching_rule_candidates": matching_rules,
                        "future_favorable_excursion": outcome["favorable_excursion"],
                        "future_adverse_excursion": outcome["adverse_excursion"],
                        "swing_threshold": outcome["swing_threshold"],
                        "qualified_swing": outcome["qualified_swing"],
                        "prior_engine_signal_present": emitted,
                        "missed_trade": bool(outcome["qualified_swing"] and not emitted),
                        "not_edge_evidence": True,
                        "strategy_promotion_allowed": False,
                        "paper_only": True,
                        "live_blocked": True,
                    }
                )
    return events


def build_past_only_features(rows: list[Bar]) -> dict[str, float]:
    if len(rows) < 200:
        raise ValueError(f"past-only feature construction requires 200 bars: received={len(rows)}")
    closes = [row["close"] for row in rows]
    current = closes[-1]
    atr_value = average_true_range(rows, 14)
    lows = [row["low"] for row in rows[-60:]]
    highs = [row["high"] for row in rows[-60:]]
    low_60 = min(lows)
    high_60 = max(highs)
    width = high_60 - low_60
    ma20 = sum(closes[-20:]) / 20.0
    ma50 = sum(closes[-50:]) / 50.0
    ma200 = sum(closes[-200:]) / 200.0
    alignment = 1.0 if current > ma20 > ma50 > ma200 else -1.0 if current < ma20 < ma50 < ma200 else 0.0
    return {
        "return_5d": round(_return(closes, 5), 6),
        "return_20d": round(_return(closes, 20), 6),
        "return_60d": round(_return(closes, 60), 6),
        "ma_alignment": alignment,
        "range_position_60d": round((current - low_60) / width if width > 0.0 else 0.5, 6),
        "support_distance_atr": round((current - low_60) / atr_value if atr_value > 0.0 else 99.0, 6),
        "resistance_distance_atr": round((high_60 - current) / atr_value if atr_value > 0.0 else 99.0, 6),
        "channel_slope_60d": round(_least_squares_slope(closes[-60:]) / current if current > 0.0 else 0.0, 8),
        "volume_z_20d": round(_z_score([float(row["volume"]) for row in rows], 20), 6),
        "atr_pct_14d": round(atr_value / current if current > 0.0 else 0.0, 6),
    }


def mine_strategy_candidates(events: list[dict[str, Any]], split_date: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for rule_name, (direction, _, conditions) in RULES.items():
        directional = [event for event in events if event["direction"] == direction]
        train_base = _metrics([event for event in directional if str(event["observation_date"]) <= split_date])
        validation_base = _metrics([event for event in directional if str(event["observation_date"]) > split_date])
        train = _metrics(
            [event for event in directional if str(event["observation_date"]) <= split_date and rule_name in event["matching_rule_candidates"]]
        )
        validation = _metrics(
            [event for event in directional if str(event["observation_date"]) > split_date and rule_name in event["matching_rule_candidates"]]
        )
        train_lift = _safe_ratio(float(train["precision"]), float(train_base["precision"]))
        validation_lift = _safe_ratio(float(validation["precision"]), float(validation_base["precision"]))
        clears = (
            int(train["sample_count"]) >= 30
            and int(validation["sample_count"]) >= 20
            and train_lift >= 1.10
            and validation_lift >= 1.10
        )
        candidates.append(
            {
                "artifact_type": "reverse_engineered_strategy_candidate",
                "candidate_id": rule_name,
                "direction": direction,
                "conditions": conditions,
                "split_date": split_date,
                "train_metrics": train,
                "validation_metrics": validation,
                "train_directional_base_rate": train_base["precision"],
                "validation_directional_base_rate": validation_base["precision"],
                "train_precision_lift": round(train_lift, 6),
                "validation_precision_lift": round(validation_lift, 6),
                "candidate_status": "shadow_candidate_cleared_two_era_screen" if clears else "rejected_or_insufficient_shadow_evidence",
                "reverse_engineering_policy": "interpretable_fixed_rules_evaluated_out_of_sample_no_automatic_promotion",
                "not_edge_evidence": True,
                "strategy_promotion_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return candidates


def missed_trade_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if bool(event["missed_trade"])]


def _future_outcome(current: Bar, future: list[Bar], direction: str, atr_pct: float) -> dict[str, float | bool]:
    current_price = current["close"]
    threshold = max(0.05, 2.0 * atr_pct)
    if direction == "bullish":
        favorable = max(row["high"] for row in future) / current_price - 1.0
        adverse = min(row["low"] for row in future) / current_price - 1.0
    else:
        favorable = 1.0 - min(row["low"] for row in future) / current_price
        adverse = 1.0 - max(row["high"] for row in future) / current_price
    return {
        "favorable_excursion": round(favorable, 6),
        "adverse_excursion": round(adverse, 6),
        "swing_threshold": round(threshold, 6),
        "qualified_swing": favorable >= threshold,
    }


def _metrics(events: list[dict[str, Any]]) -> dict[str, float | int]:
    positives = [event for event in events if bool(event["qualified_swing"])]
    return {
        "sample_count": len(events),
        "qualified_swing_count": len(positives),
        "precision": round(len(positives) / len(events), 6) if events else 0.0,
        "average_favorable_excursion": round(
            sum(float(event["future_favorable_excursion"]) for event in events) / len(events), 6
        ) if events else 0.0,
        "missed_trade_count": sum(bool(event["missed_trade"]) for event in positives),
    }


def _fingerprint(key: tuple[str, str], values: dict[str, float]) -> dict[str, Any]:
    count = int(values["trade_count"])
    return {
        "artifact_type": "past_trade_strategy_fingerprint",
        "signal_family": key[0],
        "candidate_strategy": key[1],
        "trade_count": count,
        "model_validation_win_rate": round(values["win_count"] / count, 6),
        "mean_trade_return_model_units": round(values["return_sum"] / count, 6),
        "mean_max_favorable_excursion": round(values["mfe_sum"] / count, 6),
        "mean_max_adverse_excursion": round(values["mae_sum"] / count, 6),
        "pricing_source_warning": "model_priced_not_quote_priced_not_real_options_backtest",
        "not_edge_evidence": True,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _return(values: list[float], horizon: int) -> float:
    return values[-1] / values[-horizon - 1] - 1.0 if values[-horizon - 1] > 0.0 else 0.0


def _least_squares_slope(values: list[float]) -> float:
    center = (len(values) - 1) / 2.0
    denominator = sum((index - center) ** 2 for index in range(len(values)))
    numerator = sum((index - center) * value for index, value in enumerate(values))
    return numerator / denominator if denominator > 0.0 else 0.0


def _z_score(values: list[float], period: int) -> float:
    history = values[-period - 1 : -1]
    mean = sum(history) / len(history)
    variance = sum((value - mean) ** 2 for value in history) / max(len(history) - 1, 1)
    deviation = math.sqrt(variance)
    return (values[-1] - mean) / deviation if deviation > 0.0 else 0.0


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0.0 else 0.0
