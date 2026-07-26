"""Model-priced premium-unit trade simulator for the honest backtester."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backtest_models import (
    BacktestEntryDecision,
    BacktestExitDecision,
    BacktestMarkRecord,
    BacktestPositionState,
    BacktestQualityFlag,
    BacktestTradeRecord,
)
from . import exit_policy_config


@dataclass(frozen=True)
class BacktestExitConfig:
    premium_stop_pct: float
    premium_target_pct: float
    max_holding_steps: int


def default_exit_config() -> BacktestExitConfig:
    # Values live in exit_policy_config (the whitelisted evolvable surface);
    # read at call time so a subprocess-fresh import sees the file's constants.
    return BacktestExitConfig(
        premium_stop_pct=float(exit_policy_config.PREMIUM_STOP_PCT),
        premium_target_pct=float(exit_policy_config.PREMIUM_TARGET_PCT),
        max_holding_steps=int(exit_policy_config.MAX_HOLDING_STEPS),
    )


def load_model_repricing_paths(path: Path | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(json.loads(stripped))
    return rows


def simulate_trade_intents(
    trade_intents: list[dict[str, Any]],
    model_paths: list[dict[str, Any]],
    history_dataset_status: str,
    exit_config: BacktestExitConfig,
) -> dict[str, list[dict[str, Any]]]:
    entry_decisions: list[dict[str, Any]] = []
    exit_decisions: list[dict[str, Any]] = []
    position_states: list[dict[str, Any]] = []
    mark_records: list[dict[str, Any]] = []
    trade_records: list[dict[str, Any]] = []
    quality_flags: list[dict[str, Any]] = []
    paths_by_strategy = _paths_by_strategy(model_paths)
    path_offsets: dict[str, int] = {"long_call": 0, "long_put": 0}
    for intent in trade_intents:
        strategy = str(intent["candidate_strategy"])
        if strategy == "no_trade":
            entry_decisions.append(_no_trade_entry_decision(intent).to_dict())
            exit_decisions.append(_no_trade_exit_decision(intent).to_dict())
            continue
        available_paths = paths_by_strategy[strategy]
        if not available_paths:
            quality_flags.append(_quality_flag(intent, "error", "missing_model_repricing_path", "no model repricing path is available for this long-premium strategy").to_dict())
            continue
        path_index = path_offsets[strategy] % len(available_paths)
        path_offsets[strategy] += 1
        path = available_paths[path_index]
        simulation = simulate_intent_with_model_path(intent, path, history_dataset_status, exit_config)
        entry_decisions.extend(simulation["entry_decisions"])
        exit_decisions.extend(simulation["exit_decisions"])
        position_states.extend(simulation["position_states"])
        mark_records.extend(simulation["mark_records"])
        trade_records.extend(simulation["trade_records"])
        quality_flags.extend(simulation["quality_flags"])
    return {
        "entry_decisions": entry_decisions,
        "exit_decisions": exit_decisions,
        "position_states": position_states,
        "mark_records": mark_records,
        "trade_records": trade_records,
        "quality_flags": quality_flags,
    }


def simulate_intent_with_model_path(
    intent: dict[str, Any],
    model_path: dict[str, Any],
    history_dataset_status: str,
    exit_config: BacktestExitConfig,
) -> dict[str, list[dict[str, Any]]]:
    marks = [float(value) for value in model_path.get("mark_to_market_path", [])]
    dates = [
        str(row.get("valuation_date", ""))
        for row in model_path.get("repricing_results", [])
    ]
    path_id = str(model_path.get("path_id", "model_path"))
    return simulate_intent_with_marks(intent, marks, dates, path_id, history_dataset_status, exit_config)


def simulate_intent_with_marks(
    intent: dict[str, Any],
    marks: list[float],
    mark_dates: list[str],
    model_path_id: str,
    history_dataset_status: str,
    exit_config: BacktestExitConfig,
) -> dict[str, list[dict[str, Any]]]:
    if len(marks) < 2:
        return {
            "entry_decisions": [],
            "exit_decisions": [],
            "position_states": [],
            "mark_records": [],
            "trade_records": [],
            "quality_flags": [_quality_flag(intent, "error", "insufficient_model_marks", "at least two model marks are required to avoid same-day churn").to_dict()],
        }
    if len(mark_dates) < len(marks):
        raise ValueError("mark_dates length must be at least marks length")
    entry_premium = round(float(marks[0]), 6)
    if entry_premium <= 0.0:
        raise ValueError("entry_premium must be positive for model-priced premium-unit simulation")
    exit_index, exit_reason = _select_exit_index(marks, exit_config)
    if exit_index <= 0:
        raise ValueError("same-day open/close is forbidden for current honest backtester fixture path")
    entry_date = str(mark_dates[0])
    exit_date = str(mark_dates[exit_index])
    trade_id = f"{intent['intent_id']}-{model_path_id}-trade"
    entry_decision = _entry_decision(intent, entry_date, entry_premium, model_path_id)
    scoped_marks = marks[: exit_index + 1]
    scoped_dates = mark_dates[: exit_index + 1]
    mark_records = _mark_records(intent, trade_id, scoped_marks, scoped_dates, model_path_id)
    position_states = _position_states(intent, trade_id, scoped_marks, scoped_dates, model_path_id)
    exit_premium = round(float(marks[exit_index]), 6)
    path_pnl = round(exit_premium - entry_premium, 6)
    max_adverse = round(min(value - entry_premium for value in scoped_marks), 6)
    max_favorable = round(max(value - entry_premium for value in scoped_marks), 6)
    holding_steps = exit_index
    trade_return = round(path_pnl / entry_premium, 6)
    win_loss_marker = "win_model_validation_only" if path_pnl > 0.0 else "loss_model_validation_only" if path_pnl < 0.0 else "flat_model_validation_only"
    reason_codes = [str(code) for code in intent.get("reason_codes", [])]
    reason_codes.extend([
        "model_priced_backtest_validation_only",
        "premium_units_only",
        exit_reason,
    ])
    if history_dataset_status != "valid_real_dataset":
        reason_codes.append("missing_real_history_fixture_validation_only")
    trade = BacktestTradeRecord(
        artifact_type="backtest_trade_record",
        trade_id=trade_id,
        symbol=str(intent["symbol"]),
        signal_id=str(intent["signal_id"]),
        signal_family=str(intent["signal_family"]),
        signal_date=str(intent["signal_date"]),
        direction=str(intent["direction"]),
        candidate_strategy=str(intent["candidate_strategy"]),
        option_structure=str(intent["option_structure"]),
        entry_date=entry_date,
        exit_date=exit_date,
        entry_premium=entry_premium,
        exit_premium=exit_premium,
        path_pnl=path_pnl,
        max_adverse_excursion=max_adverse,
        max_favorable_excursion=max_favorable,
        trade_return_model_units=trade_return,
        holding_steps=holding_steps,
        exit_reason=exit_reason,
        win_loss_marker=win_loss_marker,
        pricing_source_tier="model_priced",
        data_source_tier=str(intent["data_source_tier"]),
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=True,
        quote_priced=False,
        not_real_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        record_hash="",
    )
    exit_decision = _exit_decision(intent, trade_id, entry_date, exit_date, entry_premium, exit_premium, exit_reason, holding_steps, model_path_id)
    quality_flags = _history_quality_flags(intent, history_dataset_status)
    return {
        "entry_decisions": [entry_decision.to_dict()],
        "exit_decisions": [exit_decision.to_dict()],
        "position_states": [record.to_dict() for record in position_states],
        "mark_records": [record.to_dict() for record in mark_records],
        "trade_records": [trade.to_dict()],
        "quality_flags": [flag.to_dict() for flag in quality_flags],
    }


def model_unit_equity_curve(trade_records: list[dict[str, Any]]) -> list[float]:
    curve: list[float] = []
    cumulative = 0.0
    for trade in trade_records:
        cumulative = round(cumulative + float(trade.get("path_pnl", 0.0)), 6)
        curve.append(cumulative)
    return curve


def max_drawdown_model_units(equity_curve: list[float]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, float(value))
        drawdown = round(float(value) - peak, 6)
        max_drawdown = min(max_drawdown, drawdown)
    return round(max_drawdown, 6)


def _paths_by_strategy(model_paths: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "long_call": [path for path in model_paths if str(path.get("option_type", "")) == "call"],
        "long_put": [path for path in model_paths if str(path.get("option_type", "")) == "put"],
    }


def _select_exit_index(marks: list[float], exit_config: BacktestExitConfig) -> tuple[int, str]:
    entry = float(marks[0])
    maximum_index = min(len(marks) - 1, int(exit_config.max_holding_steps))
    for index in range(1, maximum_index + 1):
        mark_return = (float(marks[index]) / entry) - 1.0
        if mark_return <= float(exit_config.premium_stop_pct):
            return index, "premium_stop"
        if mark_return >= float(exit_config.premium_target_pct):
            return index, "premium_target"
    if maximum_index >= int(exit_config.max_holding_steps):
        return maximum_index, "time_stop"
    return maximum_index, "terminal_path_mark"


def _entry_decision(intent: dict[str, Any], entry_date: str, entry_premium: float, model_path_id: str) -> BacktestEntryDecision:
    reason_codes = [str(code) for code in intent.get("reason_codes", [])]
    reason_codes.extend(["entry_model_price_selected", model_path_id])
    return BacktestEntryDecision(
        artifact_type="backtest_entry_decision",
        decision_id=f"{intent['intent_id']}-entry",
        intent_id=str(intent["intent_id"]),
        symbol=str(intent["symbol"]),
        signal_id=str(intent["signal_id"]),
        signal_family=str(intent["signal_family"]),
        signal_date=str(intent["signal_date"]),
        direction=str(intent["direction"]),
        candidate_strategy=str(intent["candidate_strategy"]),
        option_structure=str(intent["option_structure"]),
        entry_date=entry_date,
        entry_premium=entry_premium,
        decision="enter_model_priced_validation_trade",
        pricing_source_tier="model_priced",
        data_source_tier=str(intent["data_source_tier"]),
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=True,
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        record_hash="",
    )


def _exit_decision(
    intent: dict[str, Any],
    trade_id: str,
    entry_date: str,
    exit_date: str,
    entry_premium: float,
    exit_premium: float,
    exit_reason: str,
    holding_steps: int,
    model_path_id: str,
) -> BacktestExitDecision:
    reason_codes = [str(code) for code in intent.get("reason_codes", [])]
    reason_codes.extend(["exit_model_price_selected", exit_reason, model_path_id])
    return BacktestExitDecision(
        artifact_type="backtest_exit_decision",
        decision_id=f"{intent['intent_id']}-exit",
        intent_id=str(intent["intent_id"]),
        trade_id=trade_id,
        symbol=str(intent["symbol"]),
        signal_id=str(intent["signal_id"]),
        signal_family=str(intent["signal_family"]),
        signal_date=str(intent["signal_date"]),
        direction=str(intent["direction"]),
        candidate_strategy=str(intent["candidate_strategy"]),
        option_structure=str(intent["option_structure"]),
        entry_date=entry_date,
        exit_date=exit_date,
        entry_premium=entry_premium,
        exit_premium=exit_premium,
        exit_reason=exit_reason,
        holding_steps=holding_steps,
        pricing_source_tier="model_priced",
        data_source_tier=str(intent["data_source_tier"]),
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=True,
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=reason_codes,
        record_hash="",
    )


def _mark_records(
    intent: dict[str, Any],
    trade_id: str,
    marks: list[float],
    mark_dates: list[str],
    model_path_id: str,
) -> list[BacktestMarkRecord]:
    entry = float(marks[0])
    records: list[BacktestMarkRecord] = []
    for index, mark in enumerate(marks):
        records.append(BacktestMarkRecord(
            artifact_type="backtest_mark_record",
            mark_id=f"{trade_id}-mark-{index:03d}",
            trade_id=trade_id,
            intent_id=str(intent["intent_id"]),
            symbol=str(intent["symbol"]),
            signal_id=str(intent["signal_id"]),
            candidate_strategy=str(intent["candidate_strategy"]),
            option_structure=str(intent["option_structure"]),
            mark_date=str(mark_dates[index]),
            step_index=index,
            premium_mark=float(mark),
            entry_premium=entry,
            mark_pnl=float(mark) - entry,
            pricing_source_tier="model_priced",
            data_source_tier=str(intent["data_source_tier"]),
            real_history_used=False,
            real_option_chain_used=False,
            fixture_only=True,
            model_priced=True,
            quote_priced=False,
            not_real_backtest_evidence=True,
            paper_only=True,
            live_blocked=True,
            reason_codes=["model_priced_mark", model_path_id, "premium_units_only"],
            record_hash="",
        ))
    return records


def _position_states(
    intent: dict[str, Any],
    trade_id: str,
    marks: list[float],
    mark_dates: list[str],
    model_path_id: str,
) -> list[BacktestPositionState]:
    entry = float(marks[0])
    peak = entry
    states: list[BacktestPositionState] = []
    for index, mark in enumerate(marks):
        peak = max(peak, float(mark))
        states.append(BacktestPositionState(
            artifact_type="backtest_position_state",
            state_id=f"{trade_id}-state-{index:03d}",
            trade_id=trade_id,
            intent_id=str(intent["intent_id"]),
            symbol=str(intent["symbol"]),
            signal_id=str(intent["signal_id"]),
            candidate_strategy=str(intent["candidate_strategy"]),
            option_structure=str(intent["option_structure"]),
            state_date=str(mark_dates[index]),
            step_index=index,
            premium_mark=float(mark),
            unrealized_pnl=float(mark) - entry,
            drawdown_from_trade_peak=float(mark) - peak,
            pricing_source_tier="model_priced",
            data_source_tier=str(intent["data_source_tier"]),
            real_history_used=False,
            real_option_chain_used=False,
            fixture_only=True,
            model_priced=True,
            quote_priced=False,
            not_real_backtest_evidence=True,
            paper_only=True,
            live_blocked=True,
            reason_codes=["model_priced_position_state", model_path_id, "premium_units_only"],
            record_hash="",
        ))
    return states


def _no_trade_entry_decision(intent: dict[str, Any]) -> BacktestEntryDecision:
    return BacktestEntryDecision(
        artifact_type="backtest_entry_decision",
        decision_id=f"{intent['intent_id']}-entry-no-trade",
        intent_id=str(intent["intent_id"]),
        symbol=str(intent["symbol"]),
        signal_id=str(intent["signal_id"]),
        signal_family=str(intent["signal_family"]),
        signal_date=str(intent["signal_date"]),
        direction=str(intent["direction"]),
        candidate_strategy="no_trade",
        option_structure="none",
        entry_date="",
        entry_premium=0.0,
        decision="no_trade",
        pricing_source_tier="fixture_only",
        data_source_tier=str(intent["data_source_tier"]),
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=False,
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=[*intent.get("reason_codes", []), "neutral_setup_no_trade"],
        record_hash="",
    )


def _no_trade_exit_decision(intent: dict[str, Any]) -> BacktestExitDecision:
    return BacktestExitDecision(
        artifact_type="backtest_exit_decision",
        decision_id=f"{intent['intent_id']}-exit-no-trade",
        intent_id=str(intent["intent_id"]),
        trade_id="",
        symbol=str(intent["symbol"]),
        signal_id=str(intent["signal_id"]),
        signal_family=str(intent["signal_family"]),
        signal_date=str(intent["signal_date"]),
        direction=str(intent["direction"]),
        candidate_strategy="no_trade",
        option_structure="none",
        entry_date="",
        exit_date="",
        entry_premium=0.0,
        exit_premium=0.0,
        exit_reason="invalid_no_trade_block",
        holding_steps=0,
        pricing_source_tier="fixture_only",
        data_source_tier=str(intent["data_source_tier"]),
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=False,
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=[*intent.get("reason_codes", []), "neutral_setup_no_trade"],
        record_hash="",
    )


def _history_quality_flags(intent: dict[str, Any], history_dataset_status: str) -> list[BacktestQualityFlag]:
    if history_dataset_status == "valid_real_dataset":
        return []
    return [
        _quality_flag(
            intent,
            "warning",
            "missing_real_history",
            "history spine is missing a valid real dataset; this is not real backtest evidence",
        ),
        _quality_flag(
            intent,
            "warning",
            "missing_real_option_chain",
            "real options chain is absent; quote-priced backtest records are forbidden",
        ),
    ]


def _quality_flag(intent: dict[str, Any], severity: str, reason_code: str, message: str) -> BacktestQualityFlag:
    return BacktestQualityFlag(
        artifact_type="backtest_quality_flag",
        flag_id=f"{intent.get('intent_id', 'missing-intent')}-{reason_code}",
        severity=severity,
        symbol=str(intent.get("symbol", "")),
        signal_id=str(intent.get("signal_id", "")),
        reason_code=reason_code,
        message=message,
        pricing_source_tier="model_priced" if intent.get("candidate_strategy") in {"long_call", "long_put"} else "fixture_only",
        data_source_tier=str(intent.get("data_source_tier", "fixture_only")),
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=bool(intent.get("candidate_strategy") in {"long_call", "long_put"}),
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        flag_hash="",
    )

