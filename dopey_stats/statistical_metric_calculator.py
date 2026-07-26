"""Pure metric calculations for model-unit backtest diagnostics."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from .statistical_truth_models import BacktestMetricSet, BacktestSampleProfile


FIXTURE_DIAGNOSTIC_MIN_TRADES = 20
REAL_EVIDENCE_MIN_TRADES = 250
REAL_EVIDENCE_MIN_REGIMES = 4
REAL_EVIDENCE_MIN_SYMBOLS = 20
REAL_EVIDENCE_MIN_DATE_SPAN_DAYS = 365


def load_json(path: Path | str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    text = target.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {}


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_sample_profile(summary: dict[str, Any], trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    sample_count = len(trade_records)
    real_history_used = bool(summary.get("real_history_used", False))
    quote_priced_count = int(summary.get("quote_priced_trade_count", 0))
    real_sample_size = sample_count if real_history_used and quote_priced_count > 0 else 0
    date_span_days = _date_span_days([str(record.get("entry_date", "")) for record in trade_records])
    distinct_symbols = {str(record.get("symbol", "")) for record in trade_records if record.get("symbol")}
    signal_families = {str(record.get("signal_family", "")) for record in trade_records if record.get("signal_family")}
    strategies = {str(record.get("candidate_strategy", "")) for record in trade_records if record.get("candidate_strategy")}
    real_thresholds_met = (
        real_sample_size >= REAL_EVIDENCE_MIN_TRADES
        and len(signal_families) >= REAL_EVIDENCE_MIN_REGIMES
        and len(distinct_symbols) >= REAL_EVIDENCE_MIN_SYMBOLS
        and date_span_days >= REAL_EVIDENCE_MIN_DATE_SPAN_DAYS
    )
    profile = BacktestSampleProfile(
        artifact_type="backtest_sample_profile",
        statistical_truth_version="",
        sample_count=sample_count,
        real_sample_size=real_sample_size,
        fixture_model_sample_size=sample_count - real_sample_size,
        distinct_symbol_count=len(distinct_symbols),
        distinct_signal_family_count=len(signal_families),
        distinct_strategy_count=len(strategies),
        date_span_days=date_span_days,
        minimum_trades_for_fixture_diagnostic=FIXTURE_DIAGNOSTIC_MIN_TRADES,
        minimum_trades_for_real_evidence=REAL_EVIDENCE_MIN_TRADES,
        minimum_regimes_for_real_evidence=REAL_EVIDENCE_MIN_REGIMES,
        minimum_distinct_symbols_for_real_evidence=REAL_EVIDENCE_MIN_SYMBOLS,
        minimum_date_span_days_for_real_evidence=REAL_EVIDENCE_MIN_DATE_SPAN_DAYS,
        fixture_diagnostic_threshold_met=sample_count >= FIXTURE_DIAGNOSTIC_MIN_TRADES,
        real_evidence_thresholds_met=real_thresholds_met,
        promotion_allowed=False,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        profile_hash="",
    )
    return profile.to_dict()


def calculate_metric_set(summary: dict[str, Any], trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    pnl_values = [round(float(record.get("path_pnl", 0.0)), 6) for record in trade_records]
    sample_count = len(pnl_values)
    wins = [value for value in pnl_values if value > 0.0]
    losses = [value for value in pnl_values if value < 0.0]
    flats = [value for value in pnl_values if value == 0.0]
    total = round(sum(pnl_values), 6)
    average = round(total / sample_count, 6) if sample_count else 0.0
    stddev = _population_stddev(pnl_values)
    downside_deviation = _downside_deviation(pnl_values)
    average_win = round(sum(wins) / len(wins), 6) if wins else 0.0
    average_loss = round(sum(losses) / len(losses), 6) if losses else 0.0
    payoff_ratio = round(average_win / abs(average_loss), 6) if average_loss < 0.0 else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 6) if gross_loss > 0.0 else 0.0
    real_sample_size = sample_count if bool(summary.get("real_history_used", False)) and int(summary.get("quote_priced_trade_count", 0)) > 0 else 0
    metric_set = BacktestMetricSet(
        artifact_type="backtest_metric_set",
        statistical_truth_version="",
        sample_count=sample_count,
        win_count=len(wins),
        loss_count=len(losses),
        flat_count=len(flats),
        win_rate=round(len(wins) / sample_count, 6) if sample_count else 0.0,
        average_model_unit_pnl=average,
        median_model_unit_pnl=round(float(median(pnl_values)), 6) if pnl_values else 0.0,
        total_model_unit_pnl=total,
        stddev_model_unit_pnl=stddev,
        downside_deviation_model_units=downside_deviation,
        sharpe_like_model_units=round(average / stddev, 6) if stddev > 0.0 else 0.0,
        sortino_like_model_units=round(average / downside_deviation, 6) if downside_deviation > 0.0 else 0.0,
        max_drawdown_model_units=round(float(summary.get("max_drawdown_model_units", _max_drawdown(pnl_values))), 6),
        average_win_model_units=average_win,
        average_loss_model_units=average_loss,
        payoff_ratio_model_units=payoff_ratio,
        expectancy_model_units=average,
        profit_factor_model_units=profit_factor,
        longest_win_streak=_longest_streak(pnl_values, True),
        longest_loss_streak=_longest_streak(pnl_values, False),
        real_sample_size=real_sample_size,
        promotion_allowed=False,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        metric_hash="",
    )
    return metric_set.to_dict()


def pnl_values_from_records(trade_records: list[dict[str, Any]]) -> list[float]:
    return [round(float(record.get("path_pnl", 0.0)), 6) for record in trade_records]


def _population_stddev(values: list[float]) -> float:
    if not values:
        return 0.0
    mean_value = sum(values) / len(values)
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    return round(math.sqrt(variance), 6)


def _downside_deviation(values: list[float]) -> float:
    downside = [min(0.0, value) for value in values]
    if not downside:
        return 0.0
    return round(math.sqrt(sum(value * value for value in downside) / len(downside)), 6)


def _max_drawdown(pnl_values: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_drawdown = 0.0
    for value in pnl_values:
        cumulative = round(cumulative + value, 6)
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, round(cumulative - peak, 6))
    return round(max_drawdown, 6)


def _longest_streak(values: list[float], winning: bool) -> int:
    longest = 0
    current = 0
    for value in values:
        matches = value > 0.0 if winning else value < 0.0
        current = current + 1 if matches else 0
        longest = max(longest, current)
    return longest


def _date_span_days(date_values: list[str]) -> int:
    parsed: list[date] = []
    for value in date_values:
        if not value:
            continue
        parsed.append(date.fromisoformat(value[:10]))
    if len(parsed) < 2:
        return 0
    return (max(parsed) - min(parsed)).days
