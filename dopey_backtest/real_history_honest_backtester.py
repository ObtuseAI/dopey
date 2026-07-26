"""Honest backtester lane over validated real OHLCV history.

For each real directional setup this lane prices a model-priced long option
along the SAME symbol's actual forward bars (no round-robin path reuse):

- entry: next trading day's open after signal_date (no same-bar lookahead)
- strike: at-the-money at entry (adjusted price units)
- expiry: ENTRY_TENOR_CALENDAR_DAYS after entry; Black-Scholes marks at each
  subsequent daily close with time decay
- implied vol proxy: trailing realized volatility through signal_date times
  IV_RISK_PREMIUM_MULTIPLIER (real chains absent; marks stay model_priced)
- exits: the existing honest exit engine (premium stop/target/time stop)

Truth labels: real_history_used=true and fixture_only=false on every record
(the underlying path is real); pricing stays model_priced and quote_priced
stays zero because no real options chain exists, so promotion-blocking
claims remain blocked upstream. Paper-only, live-blocked.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from dopey_data.history_validator import validate_default_history_dataset
from dopey_options.option_pricing_models import option_pricing_input, price_european_option
from dopey_research_pipeline.artifact_io import write_jsonl_atomic_streaming
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .model_priced_trade_simulator import (
    default_exit_config,
    max_drawdown_model_units,
    model_unit_equity_curve,
    simulate_intent_with_marks,
)
from .signal_trade_mapper import load_directional_setup_signals, map_signal_records_to_trade_intents
from .backtest_models import BACKTEST_ENGINE_VERSION, stable_backtest_hash
from dopey_core.repo_paths import REPORTS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKTEST_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "backtest"
SIGNAL_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "signals"
HISTORY_SPINE_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "history" / "history_spine_summary.json"
DIRECTIONAL_SETUP_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "directional_setup_signals.jsonl"
BACKTEST_SIGNAL_INPUTS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_signal_inputs.jsonl"
BACKTEST_TRADE_INTENTS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_intents.jsonl"
BACKTEST_ENTRY_DECISIONS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_entry_decisions.jsonl"
BACKTEST_EXIT_DECISIONS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_exit_decisions.jsonl"
BACKTEST_POSITION_STATES_PATH = BACKTEST_ARTIFACT_DIR / "backtest_position_states.jsonl"
BACKTEST_MARK_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_mark_records.jsonl"
BACKTEST_TRADE_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_records.jsonl"
BACKTEST_QUALITY_FLAGS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_quality_flags.jsonl"
BACKTEST_RUN_SUMMARY_PATH = BACKTEST_ARTIFACT_DIR / "backtest_run_summary.json"
BACKTEST_PROOF_PATH = BACKTEST_ARTIFACT_DIR / "backtest_proof.jsonl"
REAL_COHORT_SCOREBOARD_PATH = BACKTEST_ARTIFACT_DIR / "real_history_cohort_scoreboard.jsonl"
REAL_BACKTEST_REPORT_PATH = REPORTS_DIR / "DOPEY_REAL_HISTORY_HONEST_BACKTEST_REPORT.md"

ENTRY_TENOR_CALENDAR_DAYS = 30
IV_LOOKBACK_TRADING_DAYS = 20
IV_RISK_PREMIUM_MULTIPLIER_DEFAULT = 1.10
IV_MULTIPLIER_CLAMP = (0.70, 1.50)
CALIBRATION_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "chain_analytics" / "model_iv_calibration_summary.json"
IV_FLOOR = 0.08
IV_CAP = 2.00


def resolve_iv_multiplier() -> tuple[float, str]:
    """Market-supervised calibration loop: use the multiplier the real chain
    snapshots recommend (median chain-IV / realized-vol), clamped; fall back to
    the default when no calibration evidence exists. Provenance is returned so
    every run records where its pricing model came from."""
    if CALIBRATION_SUMMARY_PATH.exists():
        try:
            summary = json.loads(CALIBRATION_SUMMARY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}
        recommended = summary.get("recommended_multiplier_median_iv_over_rv")
        if isinstance(recommended, (int, float)) and recommended > 0:
            clamped = min(max(float(recommended), IV_MULTIPLIER_CLAMP[0]), IV_MULTIPLIER_CLAMP[1])
            return clamped, f"chain_calibrated_{summary.get('snapshot_date', 'unknown')}"
    return IV_RISK_PREMIUM_MULTIPLIER_DEFAULT, "default_uncalibrated"


def resolve_iv_multiplier_by_symbol() -> dict[str, float]:
    """Per-symbol calibrated multipliers (median chain IV/RV per symbol from
    the calibration lane, clamp-guarded); symbols absent here use the global."""
    if CALIBRATION_SUMMARY_PATH.exists():
        try:
            summary = json.loads(CALIBRATION_SUMMARY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        per_symbol = summary.get("per_symbol_multipliers")
        if isinstance(per_symbol, dict):
            resolved: dict[str, float] = {}
            for symbol, entry in per_symbol.items():
                value = entry.get("multiplier") if isinstance(entry, dict) else entry
                if isinstance(value, (int, float)) and value > 0:
                    resolved[str(symbol)] = min(max(float(value), IV_MULTIPLIER_CLAMP[0]), IV_MULTIPLIER_CLAMP[1])
            return resolved
    return {}


IV_RISK_PREMIUM_MULTIPLIER, IV_MULTIPLIER_PROVENANCE = resolve_iv_multiplier()
IV_MULTIPLIER_BY_SYMBOL = resolve_iv_multiplier_by_symbol()
IV_FALLBACK = 0.15
from dopey_options.risk_free_rate import resolve_risk_free_rate

RISK_FREE_RATE, RISK_FREE_SOURCE = resolve_risk_free_rate()
DIVIDEND_YIELD = 0.0
MAX_STEP_RECORDS_WRITTEN = 4000

# Transaction-cost model (documented assumptions for liquid ATM ~30d options;
# marks are treated as mid, fills pay half-spread + slippage + commission).
HALF_SPREAD_PCT_PER_SIDE = 0.025
SLIPPAGE_PCT_PER_SIDE = 0.005
COMMISSION_PER_SIDE_PREMIUM_UNITS = 0.0065  # $0.65/contract on $100 multiplier
COST_PCT_PER_SIDE = HALF_SPREAD_PCT_PER_SIDE + SLIPPAGE_PCT_PER_SIDE


def apply_trade_costs(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a mid-marked trade record to net-of-costs premium units.

    Entry fills above mid, exit fills below mid; both sides pay commission.
    path_pnl becomes NET; the mid-based gross is preserved alongside.
    """
    entry_mid = float(record["entry_premium"])
    exit_mid = float(record["exit_premium"])
    entry_fill = round(entry_mid * (1.0 + COST_PCT_PER_SIDE) + COMMISSION_PER_SIDE_PREMIUM_UNITS, 6)
    exit_fill = round(max(exit_mid * (1.0 - COST_PCT_PER_SIDE) - COMMISSION_PER_SIDE_PREMIUM_UNITS, 0.0), 6)
    gross = round(exit_mid - entry_mid, 6)
    net = round(exit_fill - entry_fill, 6)
    costed = dict(record)
    costed["entry_premium_mid"] = entry_mid
    costed["exit_premium_mid"] = exit_mid
    costed["entry_premium"] = entry_fill
    costed["exit_premium"] = exit_fill
    costed["path_pnl_gross_mid"] = gross
    costed["path_pnl"] = net
    costed["trade_cost_premium_units"] = round(gross - net, 6)
    costed["trade_return_model_units"] = round(net / entry_fill, 6) if entry_fill > 0 else 0.0
    costed["cost_model"] = {
        "half_spread_pct_per_side": HALF_SPREAD_PCT_PER_SIDE,
        "slippage_pct_per_side": SLIPPAGE_PCT_PER_SIDE,
        "commission_per_side_premium_units": COMMISSION_PER_SIDE_PREMIUM_UNITS,
    }
    if net > 0.0:
        costed["win_loss_marker"] = "win_model_validation_only"
    elif net < 0.0:
        costed["win_loss_marker"] = "loss_model_validation_only"
    else:
        costed["win_loss_marker"] = "flat_model_validation_only"
    return costed


def compute_real_history_trade_records(
    exit_config: Any = None,
    history_dataset_status: str = "valid_real_dataset",
) -> dict[str, Any]:
    """Pure in-memory compute of the honest-lane trades (NO artifact writes).

    Extracted so research harnesses (e.g. the external evolution fitness in
    operator_tools/operator_evolve_fitness.py) can score alternative exit
    configs against the same engine without touching pipeline artifacts.
    run_real_history_honest_backtester() calls this and then persists.
    """
    signal_records = [
        record
        for record in load_directional_setup_signals(DIRECTIONAL_SETUP_SIGNALS_PATH)
        if str(record.get("data_source_tier", "")) == "local_real_history"
    ]
    mapped = map_signal_records_to_trade_intents(signal_records)
    trade_intents = mapped["trade_intents"]
    quality_flags: list[dict[str, Any]] = list(mapped["quality_flags"])
    bars_by_symbol = _real_bars_by_symbol()
    if exit_config is None:
        exit_config = default_exit_config()

    entry_decisions: list[dict[str, Any]] = []
    exit_decisions: list[dict[str, Any]] = []
    position_states: list[dict[str, Any]] = []
    mark_records: list[dict[str, Any]] = []
    trade_records: list[dict[str, Any]] = []
    skipped_no_forward_bars = 0
    skipped_missing_symbol = 0
    iv_fallback_count = 0

    for intent in trade_intents:
        strategy = str(intent["candidate_strategy"])
        if strategy == "no_trade":
            continue
        symbol = str(intent["symbol"])
        rows = bars_by_symbol.get(symbol)
        if not rows:
            skipped_missing_symbol += 1
            continue
        built = _build_real_marks(intent, rows, exit_config.max_holding_steps)
        if built is None:
            skipped_no_forward_bars += 1
            continue
        marks, mark_dates, path_id, iv_used, iv_fell_back = built
        if iv_fell_back:
            iv_fallback_count += 1
        simulated = simulate_intent_with_marks(
            intent, marks, mark_dates, path_id, history_dataset_status, exit_config
        )
        entry_decisions.extend(_relabel(record) for record in simulated["entry_decisions"])
        exit_decisions.extend(_relabel(record) for record in simulated["exit_decisions"])
        position_states.extend(_relabel(record) for record in simulated["position_states"])
        mark_records.extend(_relabel(record) for record in simulated["mark_records"])
        for record in simulated["trade_records"]:
            relabeled = apply_trade_costs(_relabel(record))
            relabeled["iv_proxy_used"] = iv_used
            relabeled["record_hash"] = stable_backtest_hash(relabeled)
            trade_records.append(relabeled)
        quality_flags.extend(simulated["quality_flags"])

    return {
        "signal_inputs": mapped["signal_inputs"],
        "trade_intents": trade_intents,
        "entry_decisions": entry_decisions,
        "exit_decisions": exit_decisions,
        "position_states": position_states,
        "mark_records": mark_records,
        "trade_records": trade_records,
        "quality_flags": quality_flags,
        "skipped_no_forward_bars": skipped_no_forward_bars,
        "skipped_missing_symbol": skipped_missing_symbol,
        "iv_fallback_count": iv_fallback_count,
    }


def run_real_history_honest_backtester() -> dict[str, Any]:
    history_summary = _load_json(HISTORY_SPINE_SUMMARY_PATH)
    history_dataset_status = str(history_summary.get("dataset_status", "missing_real_dataset"))
    if history_dataset_status != "valid_real_dataset":
        summary = _blocked_summary(history_dataset_status)
        _write_json(BACKTEST_RUN_SUMMARY_PATH, summary)
        return summary
    computed = compute_real_history_trade_records(
        default_exit_config(), history_dataset_status
    )
    mapped = {"signal_inputs": computed["signal_inputs"]}
    trade_intents = computed["trade_intents"]
    quality_flags = computed["quality_flags"]
    entry_decisions = computed["entry_decisions"]
    exit_decisions = computed["exit_decisions"]
    position_states = computed["position_states"]
    mark_records = computed["mark_records"]
    trade_records = computed["trade_records"]
    skipped_no_forward_bars = computed["skipped_no_forward_bars"]
    skipped_missing_symbol = computed["skipped_missing_symbol"]
    iv_fallback_count = computed["iv_fallback_count"]

    equity_curve = model_unit_equity_curve(trade_records)
    total_pnl = round(sum(float(record.get("path_pnl", 0.0)) for record in trade_records), 6)
    win_count = sum(1 for record in trade_records if str(record.get("win_loss_marker", "")).startswith("win_"))
    loss_count = sum(1 for record in trade_records if str(record.get("win_loss_marker", "")).startswith("loss_"))
    scoreboard = _cohort_scoreboard(trade_records)
    marks_written = mark_records[:MAX_STEP_RECORDS_WRITTEN]
    states_written = position_states[:MAX_STEP_RECORDS_WRITTEN]
    quality_flags.extend(_run_quality_flags(len(mark_records), len(marks_written)))

    summary = {
        "artifact_type": "backtest_run_summary",
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "backtest_lane": "real_history_model_priced",
        "backtest_status": "valid_real_history_model_priced_backtest_complete",
        "history_dataset_status": history_dataset_status,
        "real_history_used": True,
        "real_option_chain_used": False,
        "pricing_source_tier_distribution": {
            "fixture_only": 0,
            "model_priced": len(trade_records),
            "quote_priced": 0,
        },
        "data_source_tier_distribution": {"local_real_history": len(trade_intents)},
        "trade_intent_count": len(trade_intents),
        "trade_record_count": len(trade_records),
        "long_call_trade_count": sum(1 for record in trade_records if record["candidate_strategy"] == "long_call"),
        "long_put_trade_count": sum(1 for record in trade_records if record["candidate_strategy"] == "long_put"),
        "no_trade_count": sum(1 for record in trade_intents if record["candidate_strategy"] == "no_trade"),
        "blocked_policy_violation_count": sum(
            1 for flag in quality_flags if flag.get("reason_code") == "blocked_policy_violation"
        ),
        "model_priced_trade_count": len(trade_records),
        "quote_priced_trade_count": 0,
        "fixture_only_trade_count": 0,
        "skipped_no_forward_bars": skipped_no_forward_bars,
        "skipped_missing_symbol": skipped_missing_symbol,
        "iv_fallback_count": iv_fallback_count,
        "entry_policy": "next_trading_day_open_after_signal_date",
        "option_model": {
            "tenor_calendar_days": ENTRY_TENOR_CALENDAR_DAYS,
            "strike_policy": "at_the_money_entry_open_adjusted_units",
            "iv_proxy": f"realized_vol_{IV_LOOKBACK_TRADING_DAYS}d_x_{IV_RISK_PREMIUM_MULTIPLIER}",
            "iv_multiplier_provenance": IV_MULTIPLIER_PROVENANCE,
            "per_symbol_multipliers_active": len(IV_MULTIPLIER_BY_SYMBOL),
            "risk_free_rate": RISK_FREE_RATE,
            "risk_free_source": RISK_FREE_SOURCE,
            "dividend_yield": DIVIDEND_YIELD,
            "price_units": "adjusted_close_units",
        },
        "total_path_pnl_model_units": total_pnl,
        "total_path_pnl_gross_mid_model_units": round(
            sum(float(record.get("path_pnl_gross_mid", 0.0)) for record in trade_records), 6
        ),
        "total_trade_costs_model_units": round(
            sum(float(record.get("trade_cost_premium_units", 0.0)) for record in trade_records), 6
        ),
        "cost_model": {
            "half_spread_pct_per_side": HALF_SPREAD_PCT_PER_SIDE,
            "slippage_pct_per_side": SLIPPAGE_PCT_PER_SIDE,
            "commission_per_side_premium_units": COMMISSION_PER_SIDE_PREMIUM_UNITS,
        },
        "average_path_pnl_model_units": round(total_pnl / len(trade_records), 6) if trade_records else 0.0,
        "max_drawdown_model_units": max_drawdown_model_units(equity_curve),
        "win_count": win_count,
        "loss_count": loss_count,
        # 7 signal families fan out over shared (symbol, date, side) paths, so
        # run-level totals sum correlated duplicates; this is the true count of
        # independent paths and per-cohort stats are the comparable unit.
        "unique_directional_paths": len({
            (str(record.get("symbol", "")), str(record.get("signal_date", "")), str(record.get("candidate_strategy", "")))
            for record in trade_records
        }),
        "aggregate_totals_note": "run-level totals sum family-overlapping duplicate paths; per-cohort stats are the comparable unit",
        "mark_records_total": len(mark_records),
        "mark_records_written": len(marks_written),
        "position_states_total": len(position_states),
        "position_states_written": len(states_written),
        "step_records_sampled": len(mark_records) > MAX_STEP_RECORDS_WRITTEN,
        "quality_flags": sorted({str(flag.get("reason_code", "")) for flag in quality_flags if flag.get("reason_code")}),
        "not_real_backtest_evidence": True,
        "not_real_backtest_evidence_reason": "options_marks_model_priced_no_real_chain",
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
        "next_recommended_target": "DOPEY_STATISTICAL_TRUTH_LAYER_ON_REAL_HISTORY",
        "artifact_paths": _artifact_paths(),
    }
    summary["run_hash"] = stable_backtest_hash(summary)
    BACKTEST_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(BACKTEST_SIGNAL_INPUTS_PATH, mapped["signal_inputs"])
    _write_jsonl(BACKTEST_TRADE_INTENTS_PATH, trade_intents)
    _write_jsonl(BACKTEST_ENTRY_DECISIONS_PATH, entry_decisions)
    _write_jsonl(BACKTEST_EXIT_DECISIONS_PATH, exit_decisions)
    _write_jsonl(BACKTEST_POSITION_STATES_PATH, states_written)
    _write_jsonl(BACKTEST_MARK_RECORDS_PATH, marks_written)
    _write_jsonl(BACKTEST_TRADE_RECORDS_PATH, trade_records)
    _write_jsonl(BACKTEST_QUALITY_FLAGS_PATH, quality_flags)
    _write_json(BACKTEST_RUN_SUMMARY_PATH, summary)
    _write_jsonl(BACKTEST_PROOF_PATH, [_proof(summary)])
    _write_jsonl(REAL_COHORT_SCOREBOARD_PATH, scoreboard)
    _write_report(summary, scoreboard)
    return summary


def _build_real_marks(
    intent: dict[str, Any],
    rows: list[dict[str, Any]],
    max_holding_steps: int,
) -> tuple[list[float], list[str], str, float, bool] | None:
    signal_date = str(intent["signal_date"])
    dates = [row["date"] for row in rows]
    position = _last_index_leq(dates, signal_date)
    if position is None:
        return None
    entry_position = position + 1
    if entry_position + 1 >= len(rows):
        return None
    entry_row = rows[entry_position]
    entry_spot = float(entry_row["adjusted_open"])
    if entry_spot <= 0.0:
        return None
    iv, fell_back = _iv_proxy(rows, position, str(intent.get("symbol", "")))
    option_type = "call" if intent["candidate_strategy"] == "long_call" else "put"
    strike = entry_spot
    entry_date = str(entry_row["date"])
    expiry_ordinal = _ordinal(entry_date) + ENTRY_TENOR_CALENDAR_DAYS
    marks = [
        _bs_price(intent["symbol"], option_type, strike, entry_spot, ENTRY_TENOR_CALENDAR_DAYS / 365.0, iv, entry_date)
    ]
    mark_dates = [entry_date]
    last_position = min(entry_position + max_holding_steps, len(rows) - 1)
    for step_position in range(entry_position + 1, last_position + 1):
        row = rows[step_position]
        remaining_days = max(expiry_ordinal - _ordinal(str(row["date"])), 0)
        marks.append(
            _bs_price(
                intent["symbol"],
                option_type,
                strike,
                float(row["adjusted_close"]),
                remaining_days / 365.0,
                iv,
                str(row["date"]),
            )
        )
        mark_dates.append(str(row["date"]))
    if len(marks) < 2 or marks[0] <= 0.0:
        return None
    path_id = f"real-{intent['symbol']}-{entry_date}-{option_type}"
    return marks, mark_dates, path_id, iv, fell_back


def _bs_price(
    symbol: str,
    option_type: str,
    strike: float,
    spot: float,
    time_to_expiry_years: float,
    implied_vol: float,
    valuation_date: str,
) -> float:
    pricing = price_european_option(
        option_pricing_input(
            symbol=str(symbol),
            option_type=option_type,
            strike=strike,
            expiry="",
            valuation_date=valuation_date,
            underlying_price=spot,
            time_to_expiry_years=max(time_to_expiry_years, 0.0),
            implied_vol=implied_vol,
            risk_free_rate=RISK_FREE_RATE,
            dividend_yield=DIVIDEND_YIELD,
            pricing_source_tier="model_priced",
        )
    )
    return max(round(float(pricing.model_price), 6), 0.000001)


def _iv_proxy(rows: list[dict[str, Any]], signal_position: int, symbol: str = "") -> tuple[float, bool]:
    start = max(signal_position - IV_LOOKBACK_TRADING_DAYS, 0)
    closes = [float(row["adjusted_close"]) for row in rows[start : signal_position + 1]]
    returns = [
        math.log(later / earlier)
        for earlier, later in zip(closes, closes[1:])
        if earlier > 0.0 and later > 0.0
    ]
    if len(returns) < 2:
        return IV_FALLBACK, True
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    realized = math.sqrt(max(variance, 0.0)) * math.sqrt(252.0)
    if realized <= 0.0:
        return IV_FALLBACK, True
    multiplier = IV_MULTIPLIER_BY_SYMBOL.get(symbol, IV_RISK_PREMIUM_MULTIPLIER)
    return min(max(realized * multiplier, IV_FLOOR), IV_CAP), False


def _real_bars_by_symbol() -> dict[str, list[dict[str, Any]]]:
    result = validate_default_history_dataset()
    if result["dataset_status"] != "valid_real_dataset":
        return {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in result["bars_loaded"]:
        close = float(bar["close"])
        adjustment = float(bar["adjusted_close"]) / close if close > 0.0 else 1.0
        grouped[str(bar["symbol"])].append(
            {
                "date": str(bar["date"]),
                "adjusted_open": round(float(bar["open"]) * adjustment, 10),
                "adjusted_close": float(bar["adjusted_close"]),
            }
        )
    for rows in grouped.values():
        rows.sort(key=lambda row: row["date"])
    return dict(grouped)


def _last_index_leq(dates: list[str], target: str) -> int | None:
    low, high, answer = 0, len(dates) - 1, None
    while low <= high:
        middle = (low + high) // 2
        if dates[middle] <= target:
            answer = middle
            low = middle + 1
        else:
            high = middle - 1
    return answer


def _ordinal(value: str) -> int:
    year, month, day = (int(part) for part in value.split("-"))
    from datetime import date

    return date(year, month, day).toordinal()


def _relabel(record: dict[str, Any]) -> dict[str, Any]:
    relabeled = dict(record)
    relabeled["real_history_used"] = True
    relabeled["fixture_only"] = False
    relabeled["data_source_tier"] = "local_real_history"
    if "record_hash" in relabeled:
        relabeled["record_hash"] = stable_backtest_hash(relabeled)
    return relabeled


def _cohort_scoreboard(trade_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in trade_records:
        grouped[(str(record["signal_family"]), str(record["candidate_strategy"]))].append(record)
    scoreboard: list[dict[str, Any]] = []
    for (family, strategy), records in sorted(grouped.items()):
        pnls = [float(record["path_pnl"]) for record in records]
        returns = [float(record.get("trade_return_model_units", 0.0)) for record in records]
        gross_profit = sum(value for value in pnls if value > 0.0)
        gross_loss = -sum(value for value in pnls if value < 0.0)
        wins = sum(1 for value in pnls if value > 0.0)
        row = {
            "artifact_type": "real_history_cohort_scoreboard",
            "cohort_id": f"{family}|{strategy}",
            "signal_family": family,
            "candidate_strategy": strategy,
            "sample_count": len(records),
            "win_rate": round(wins / len(records), 6) if records else 0.0,
            "net_pnl_model_units": round(sum(pnls), 6),
            "gross_profit_model_units": round(gross_profit, 6),
            "gross_loss_model_units": round(gross_loss, 6),
            "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0.0 else 0.0,
            "average_trade_return": round(sum(returns) / len(returns), 6) if returns else 0.0,
            "data_source_tier": "local_real_history",
            "real_history_used": True,
            "pricing_source_tier": "model_priced",
            "not_edge_evidence": True,
            "paper_only": True,
            "live_blocked": True,
        }
        row["record_hash"] = stable_backtest_hash(row)
        scoreboard.append(row)
    return scoreboard


def _run_quality_flags(mark_total: int, marks_written: int) -> list[dict[str, Any]]:
    flags = [
        {
            "artifact_type": "backtest_quality_flag",
            "flag_id": "real-backtest-model-priced-options",
            "severity": "warning",
            "symbol": "",
            "signal_id": "",
            "reason_code": "missing_real_option_chain",
            "message": "option marks are Black-Scholes model marks; no real options chain exists, so this is not real options-market evidence",
            "pricing_source_tier": "model_priced",
            "data_source_tier": "local_real_history",
            "real_history_used": True,
            "real_option_chain_used": False,
            "fixture_only": False,
            "model_priced": True,
            "quote_priced": False,
            "not_real_backtest_evidence": True,
            "paper_only": True,
            "live_blocked": True,
        },
        {
            "artifact_type": "backtest_quality_flag",
            "flag_id": "real-backtest-costs-modeled",
            "severity": "info",
            "symbol": "",
            "signal_id": "",
            "reason_code": "spread_slippage_commission_costs_modeled",
            "message": "path_pnl is NET of modeled half-spread, slippage, and commissions; mid-based gross preserved as path_pnl_gross_mid",
            "pricing_source_tier": "model_priced",
            "data_source_tier": "local_real_history",
            "real_history_used": True,
            "real_option_chain_used": False,
            "fixture_only": False,
            "model_priced": True,
            "quote_priced": False,
            "not_real_backtest_evidence": True,
            "paper_only": True,
            "live_blocked": True,
        },
    ]
    if mark_total > marks_written:
        flags.append(
            {
                "artifact_type": "backtest_quality_flag",
                "flag_id": "real-backtest-step-records-sampled",
                "severity": "info",
                "symbol": "",
                "signal_id": "",
                "reason_code": "step_records_sampled_for_artifact_size",
                "message": f"only the first {marks_written} of {mark_total} mark/position step records are written; trade records are complete",
                "pricing_source_tier": "model_priced",
                "data_source_tier": "local_real_history",
                "real_history_used": True,
                "real_option_chain_used": False,
                "fixture_only": False,
                "model_priced": True,
                "quote_priced": False,
                "not_real_backtest_evidence": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    for flag in flags:
        flag["flag_hash"] = stable_backtest_hash(flag)
    return flags


def _blocked_summary(history_dataset_status: str) -> dict[str, Any]:
    summary = {
        "artifact_type": "backtest_run_summary",
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "backtest_lane": "real_history_model_priced",
        "backtest_status": "blocked_missing_valid_real_history",
        "history_dataset_status": history_dataset_status,
        "real_history_used": False,
        "trade_intent_count": 0,
        "trade_record_count": 0,
        "quote_priced_trade_count": 0,
        "not_real_backtest_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["run_hash"] = stable_backtest_hash(summary)
    return summary


def _proof(summary: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "backtest_proof",
        "proof_id": "dopey-real-history-honest-backtester-v1-proof",
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "backtest_status": summary["backtest_status"],
        "history_dataset_status": summary["history_dataset_status"],
        "real_history_used": summary["real_history_used"],
        "trade_intent_count": summary["trade_intent_count"],
        "trade_record_count": summary["trade_record_count"],
        "not_real_backtest_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "no_broker": True,
        "no_credentials": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "no_orders": True,
        "paper_only": True,
        "live_blocked": True,
        "next_recommended_target": "DOPEY_STATISTICAL_TRUTH_LAYER_ON_REAL_HISTORY",
    }
    record["proof_hash"] = reproducibility_hash(record)
    return record


def _write_report(summary: dict[str, Any], scoreboard: list[dict[str, Any]]) -> None:
    top = sorted(scoreboard, key=lambda row: row["net_pnl_model_units"], reverse=True)
    lines = [
        "# DOPEY Real History Honest Backtest Report",
        "",
        "## What This Is",
        "The honest backtester running on validated, hash-pinned real OHLCV history for the first time.",
        "Underlying paths are real; option marks are Black-Scholes model marks (no real options chain).",
        "",
        "## Entry / Exit Policy",
        f"- entry: `{summary['entry_policy']}`",
        f"- option model: `{json.dumps(summary['option_model'], sort_keys=True)}`",
        "- exits: premium_stop -50%, premium_target +100%, time_stop 3 steps.",
        "",
        "## Run",
        f"- backtest_status: `{summary['backtest_status']}`",
        f"- trade_intent_count: `{summary['trade_intent_count']}`",
        f"- trade_record_count: `{summary['trade_record_count']}`",
        f"- long_call / long_put: `{summary['long_call_trade_count']}` / `{summary['long_put_trade_count']}`",
        f"- no_trade intents: `{summary['no_trade_count']}`",
        f"- skipped (no forward bars / missing symbol): `{summary['skipped_no_forward_bars']}` / `{summary['skipped_missing_symbol']}`",
        f"- total_path_pnl_model_units: `{summary['total_path_pnl_model_units']}`",
        f"- average_path_pnl_model_units: `{summary['average_path_pnl_model_units']}`",
        f"- max_drawdown_model_units: `{summary['max_drawdown_model_units']}`",
        f"- win / loss: `{summary['win_count']}` / `{summary['loss_count']}`",
        "",
        "## Cohorts (signal_family x strategy, model units)",
    ]
    for row in top:
        lines.append(
            f"- `{row['cohort_id']}`: n=`{row['sample_count']}` win_rate=`{row['win_rate']}` "
            f"PF=`{row['profit_factor']}` net=`{row['net_pnl_model_units']}`"
        )
    lines.extend(
        [
            "",
            "## Honest Limits",
            "- No real options chain: marks are model-priced; this is NOT real options-market evidence.",
            "- path_pnl is NET of a modeled cost stack (half-spread, slippage, commission); mid-based gross kept alongside.",
            "- Model-unit P&L is not account equity and not a profitability claim.",
            "- paper_only: `true`; live_blocked: `true`; promotion remains blocked upstream.",
        ]
    )
    REAL_BACKTEST_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _artifact_paths() -> dict[str, str]:
    return {
        "backtest_signal_inputs": str(BACKTEST_SIGNAL_INPUTS_PATH),
        "backtest_trade_intents": str(BACKTEST_TRADE_INTENTS_PATH),
        "backtest_entry_decisions": str(BACKTEST_ENTRY_DECISIONS_PATH),
        "backtest_exit_decisions": str(BACKTEST_EXIT_DECISIONS_PATH),
        "backtest_position_states": str(BACKTEST_POSITION_STATES_PATH),
        "backtest_mark_records": str(BACKTEST_MARK_RECORDS_PATH),
        "backtest_trade_records": str(BACKTEST_TRADE_RECORDS_PATH),
        "backtest_quality_flags": str(BACKTEST_QUALITY_FLAGS_PATH),
        "backtest_run_summary": str(BACKTEST_RUN_SUMMARY_PATH),
        "backtest_proof": str(BACKTEST_PROOF_PATH),
        "real_history_cohort_scoreboard": str(REAL_COHORT_SCOREBOARD_PATH),
        "real_history_backtest_report": str(REAL_BACKTEST_REPORT_PATH),
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"dataset_status": "missing_real_dataset"}
    text = path.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {"dataset_status": "missing_real_dataset"}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    # Streaming + atomic: the trade ledger exceeds 500MB at the full universe;
    # a list-join write spikes >1GB and a torn truncate-write was the
    # 2026-07-21 corruption incident class.
    write_jsonl_atomic_streaming(path, records)
