"""Market structure, trap, and volatility-regime engine over validated real history.

Deterministic, leak-free feature extraction the honest lane can consume:

- swing highs/lows (k-bar fractals) and clustered support/resistance zones
- bull/bear trap events: a close breaks a recent swing level then closes back
  through it within TRAP_CONFIRM_BARS (failed breakout / liquidity grab proxy)
- volume anomalies: z-score vs trailing window (institutional footprint proxy)
- variance risk premium (VRP) proxy: VIX implied variance minus SPY trailing
  realized variance; rich implied vol is a long-premium headwind (IV-crush risk)
- entry blackout windows derived from traps and VRP richness, plus a
  filter-value analysis that re-scores the real trade records with blackouts
  applied - measuring whether avoidance would have improved net P&L.

Everything is computed from bars at or before the event date. No fixtures, no
network, no options chains. Paper-only, live-blocked, not edge evidence.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from dopey_backtest.trade_records_recovery import (
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)
from dopey_core.repo_paths import REPORTS_DIR
from dopey_data.history_validator import validate_default_history_dataset
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
STRUCTURE_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "market_structure"
SWING_LEVELS_PATH = STRUCTURE_ARTIFACT_DIR / "swing_levels.jsonl"
SR_ZONES_PATH = STRUCTURE_ARTIFACT_DIR / "support_resistance_zones.jsonl"
TRAP_EVENTS_PATH = STRUCTURE_ARTIFACT_DIR / "trap_events.jsonl"
VOLUME_ANOMALIES_PATH = STRUCTURE_ARTIFACT_DIR / "volume_anomalies.jsonl"
VRP_SERIES_PATH = STRUCTURE_ARTIFACT_DIR / "variance_risk_premium_series.jsonl"
BLACKOUT_WINDOWS_PATH = STRUCTURE_ARTIFACT_DIR / "entry_blackout_windows.jsonl"
FILTER_VALUE_PATH = STRUCTURE_ARTIFACT_DIR / "structure_filter_value_analysis.json"
STRUCTURE_SUMMARY_PATH = STRUCTURE_ARTIFACT_DIR / "market_structure_summary.json"
STRUCTURE_REPORT_PATH = REPORTS_DIR / "DOPEY_MARKET_STRUCTURE_ENGINE_REPORT.md"

SWING_FRACTAL_K = 3
SR_CLUSTER_TOLERANCE_PCT = 0.015
SR_MIN_TOUCHES = 2
TRAP_LOOKBACK_BARS = 40
TRAP_CONFIRM_BARS = 3
VOLUME_Z_WINDOW = 20
VOLUME_Z_THRESHOLD = 3.0
VRP_REALIZED_WINDOW = 20
VRP_RICH_Z = 1.0
BLACKOUT_BARS_AFTER_TRAP = 2
STRUCTURE_START_DATE = "2014-06-01"


def run_market_structure_engine() -> dict[str, Any]:
    dataset = validate_default_history_dataset()
    if dataset["dataset_status"] != "valid_real_dataset":
        summary = {
            "artifact_type": "market_structure_summary",
            "structure_status": "blocked_missing_valid_real_history",
            "paper_only": True,
            "live_blocked": True,
        }
        _write_json(STRUCTURE_SUMMARY_PATH, summary)
        return summary
    bars_by_symbol = _group_bars(dataset["bars_loaded"])
    swings: list[dict[str, Any]] = []
    zones: list[dict[str, Any]] = []
    traps: list[dict[str, Any]] = []
    volume_anomalies: list[dict[str, Any]] = []
    for symbol, rows in sorted(bars_by_symbol.items()):
        if symbol == "VIX":
            continue
        symbol_swings = _swing_levels(symbol, rows)
        swings.extend(symbol_swings)
        zones.extend(_sr_zones(symbol, symbol_swings, rows))
        traps.extend(_trap_events(symbol, rows, symbol_swings))
        volume_anomalies.extend(_volume_anomalies(symbol, rows))
    vrp_series = _vrp_series(bars_by_symbol.get("SPY", []), bars_by_symbol.get("VIX", []))
    blackouts = _blackout_windows(traps, vrp_series)
    filter_value = _filter_value_analysis(blackouts)
    summary = {
        "artifact_type": "market_structure_summary",
        "structure_status": "market_structure_computed_real_history",
        "structure_start_date": STRUCTURE_START_DATE,
        "symbols_analyzed": sorted(symbol for symbol in bars_by_symbol if symbol != "VIX"),
        "swing_level_count": len(swings),
        "sr_zone_count": len(zones),
        "trap_event_count": len(traps),
        "bull_trap_count": sum(1 for record in traps if record["trap_type"] == "bull_trap"),
        "bear_trap_count": sum(1 for record in traps if record["trap_type"] == "bear_trap"),
        "volume_anomaly_count": len(volume_anomalies),
        "vrp_observation_count": len(vrp_series),
        "vrp_rich_day_count": sum(1 for record in vrp_series if record["vrp_rich"]),
        "blackout_window_count": len(blackouts),
        "filter_value": filter_value,
        "leak_policy": "all_features_use_bars_at_or_before_event_date",
        "data_source_tier": "local_real_history",
        "real_history_used": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    STRUCTURE_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(SWING_LEVELS_PATH, swings)
    _write_jsonl(SR_ZONES_PATH, zones)
    _write_jsonl(TRAP_EVENTS_PATH, traps)
    _write_jsonl(VOLUME_ANOMALIES_PATH, volume_anomalies)
    _write_jsonl(VRP_SERIES_PATH, vrp_series)
    _write_jsonl(BLACKOUT_WINDOWS_PATH, blackouts)
    _write_json(FILTER_VALUE_PATH, filter_value)
    _write_json(STRUCTURE_SUMMARY_PATH, summary)
    _write_report(summary)
    return summary


def _group_bars(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in bars:
        if str(bar["date"]) < STRUCTURE_START_DATE:
            continue
        grouped[str(bar["symbol"])].append(
            {
                "date": str(bar["date"]),
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "adjusted_close": float(bar["adjusted_close"]),
                "volume": int(bar["volume"]),
            }
        )
    for rows in grouped.values():
        rows.sort(key=lambda row: row["date"])
    return dict(grouped)


def _swing_levels(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    swings: list[dict[str, Any]] = []
    k = SWING_FRACTAL_K
    for index in range(k, len(rows) - k):
        window = rows[index - k : index + k + 1]
        row = rows[index]
        if row["high"] == max(item["high"] for item in window):
            swings.append(_swing(symbol, row, "swing_high", row["high"], index))
        if row["low"] == min(item["low"] for item in window):
            swings.append(_swing(symbol, row, "swing_low", row["low"], index))
    return swings


def _swing(symbol: str, row: dict[str, Any], kind: str, level: float, index: int) -> dict[str, Any]:
    return {
        "artifact_type": "market_structure_swing_level",
        "symbol": symbol,
        "date": row["date"],
        "swing_type": kind,
        "level": round(level, 6),
        "bar_index": index,
        "confirm_lag_bars": SWING_FRACTAL_K,
        "paper_only": True,
        "live_blocked": True,
    }


def _sr_zones(symbol: str, swings: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    levels = sorted(record["level"] for record in swings)
    zones: list[dict[str, Any]] = []
    cluster: list[float] = []
    for level in levels:
        if not cluster or level <= cluster[0] * (1.0 + SR_CLUSTER_TOLERANCE_PCT):
            cluster.append(level)
        else:
            if len(cluster) >= SR_MIN_TOUCHES:
                zones.append(_zone(symbol, cluster))
            cluster = [level]
    if len(cluster) >= SR_MIN_TOUCHES:
        zones.append(_zone(symbol, cluster))
    last_close = rows[-1]["close"] if rows else 0.0
    for zone in zones:
        zone["distance_from_last_close_pct"] = (
            round((zone["zone_mid"] - last_close) / last_close, 6) if last_close else 0.0
        )
    return zones


def _zone(symbol: str, cluster: list[float]) -> dict[str, Any]:
    return {
        "artifact_type": "market_structure_sr_zone",
        "symbol": symbol,
        "zone_low": round(min(cluster), 6),
        "zone_high": round(max(cluster), 6),
        "zone_mid": round(sum(cluster) / len(cluster), 6),
        "touch_count": len(cluster),
        "paper_only": True,
        "live_blocked": True,
    }


def _trap_events(symbol: str, rows: list[dict[str, Any]], swings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Failed-breakout detector.

    Bull trap: close breaks above the max swing-high of the trailing lookback,
    then closes back below that level within TRAP_CONFIRM_BARS. Bear trap is
    the mirror. The swing set at each bar only includes swings CONFIRMED by
    then (fractal confirmation lags SWING_FRACTAL_K bars) - no lookahead.
    """
    highs_by_index: list[tuple[int, float]] = [
        (record["bar_index"], record["level"]) for record in swings if record["swing_type"] == "swing_high"
    ]
    lows_by_index: list[tuple[int, float]] = [
        (record["bar_index"], record["level"]) for record in swings if record["swing_type"] == "swing_low"
    ]
    events: list[dict[str, Any]] = []
    for index in range(TRAP_LOOKBACK_BARS, len(rows) - TRAP_CONFIRM_BARS):
        confirmed_highs = [
            level
            for swing_index, level in highs_by_index
            if swing_index + SWING_FRACTAL_K <= index and swing_index >= index - TRAP_LOOKBACK_BARS
        ]
        confirmed_lows = [
            level
            for swing_index, level in lows_by_index
            if swing_index + SWING_FRACTAL_K <= index and swing_index >= index - TRAP_LOOKBACK_BARS
        ]
        close = rows[index]["close"]
        prior_close = rows[index - 1]["close"]
        if confirmed_highs:
            resistance = max(confirmed_highs)
            if prior_close <= resistance < close:
                for confirm in range(1, TRAP_CONFIRM_BARS + 1):
                    if rows[index + confirm]["close"] < resistance:
                        events.append(_trap(symbol, rows, index, index + confirm, "bull_trap", resistance))
                        break
        if confirmed_lows:
            support = min(confirmed_lows)
            if prior_close >= support > close:
                for confirm in range(1, TRAP_CONFIRM_BARS + 1):
                    if rows[index + confirm]["close"] > support:
                        events.append(_trap(symbol, rows, index, index + confirm, "bear_trap", support))
                        break
    return events


def _trap(
    symbol: str,
    rows: list[dict[str, Any]],
    break_index: int,
    fail_index: int,
    trap_type: str,
    level: float,
) -> dict[str, Any]:
    return {
        "artifact_type": "market_structure_trap_event",
        "symbol": symbol,
        "trap_type": trap_type,
        "break_date": rows[break_index]["date"],
        "fail_date": rows[fail_index]["date"],
        "confirm_bars": fail_index - break_index,
        "level": round(level, 6),
        "break_close": round(rows[break_index]["close"], 6),
        "fail_close": round(rows[fail_index]["close"], 6),
        "detected_at_date": rows[fail_index]["date"],
        "paper_only": True,
        "live_blocked": True,
    }


def _volume_anomalies(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    for index in range(VOLUME_Z_WINDOW, len(rows)):
        window = [float(row["volume"]) for row in rows[index - VOLUME_Z_WINDOW : index]]
        mean = sum(window) / len(window)
        variance = sum((value - mean) ** 2 for value in window) / max(len(window) - 1, 1)
        deviation = math.sqrt(variance)
        if deviation <= 0.0:
            continue
        z_score = (float(rows[index]["volume"]) - mean) / deviation
        if z_score >= VOLUME_Z_THRESHOLD:
            prior_close = float(rows[index - 1]["close"])
            price_change = rows[index]["close"] / prior_close - 1.0 if prior_close > 0 else 0.0
            anomalies.append(
                {
                    "artifact_type": "market_structure_volume_anomaly",
                    "symbol": symbol,
                    "date": rows[index]["date"],
                    "volume_z_score": round(z_score, 4),
                    "price_change_pct": round(price_change, 6),
                    "divergent": bool(abs(price_change) < 0.002),
                    "paper_only": True,
                    "live_blocked": True,
                }
            )
    return anomalies


def _vrp_series(spy_rows: list[dict[str, Any]], vix_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vix_by_date = {row["date"]: row["close"] for row in vix_rows}
    closes = [row["adjusted_close"] for row in spy_rows]
    dates = [row["date"] for row in spy_rows]
    series: list[dict[str, Any]] = []
    vrp_values: list[float] = []
    for index in range(VRP_REALIZED_WINDOW, len(spy_rows)):
        date = dates[index]
        vix_close = vix_by_date.get(date)
        if vix_close is None:
            continue
        window = closes[index - VRP_REALIZED_WINDOW : index + 1]
        returns = [math.log(later / earlier) for earlier, later in zip(window, window[1:]) if earlier > 0 and later > 0]
        if len(returns) < 2:
            continue
        mean = sum(returns) / len(returns)
        realized_var = (sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)) * 252.0
        implied_var = (vix_close / 100.0) ** 2
        vrp = implied_var - realized_var
        vrp_values.append(vrp)
        history = vrp_values[:-1][-252:]
        if len(history) >= 60:
            history_mean = sum(history) / len(history)
            history_var = sum((value - history_mean) ** 2 for value in history) / (len(history) - 1)
            history_dev = math.sqrt(max(history_var, 1e-12))
            vrp_z = (vrp - history_mean) / history_dev
        else:
            vrp_z = 0.0
        series.append(
            {
                "artifact_type": "variance_risk_premium_observation",
                "date": date,
                "vix_close": round(vix_close, 4),
                "implied_variance": round(implied_var, 8),
                "realized_variance_20d": round(realized_var, 8),
                "vrp": round(vrp, 8),
                "vrp_z": round(vrp_z, 4),
                "vrp_rich": bool(vrp_z >= VRP_RICH_Z),
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return series


def _blackout_windows(traps: list[dict[str, Any]], vrp_series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for trap in traps:
        direction_blocked = "long_call" if trap["trap_type"] == "bull_trap" else "long_put"
        windows.append(
            {
                "artifact_type": "entry_blackout_window",
                "reason": trap["trap_type"],
                "symbol": trap["symbol"],
                "start_date": trap["detected_at_date"],
                "blackout_bars": BLACKOUT_BARS_AFTER_TRAP,
                "blocks_strategy": direction_blocked,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    for observation in vrp_series:
        if observation["vrp_rich"]:
            windows.append(
                {
                    "artifact_type": "entry_blackout_window",
                    "reason": "vrp_rich_iv_crush_risk",
                    "symbol": "ALL",
                    "start_date": observation["date"],
                    "blackout_bars": 1,
                    "blocks_strategy": "both",
                    "paper_only": True,
                    "live_blocked": True,
                }
            )
    return windows


def _filter_value_analysis(blackouts: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-score existing real trade records with blackout filters applied."""
    resolution = resolve_default_backtest_trade_ledger()
    symbol_blackouts: dict[str, set[str]] = defaultdict(set)
    global_blackouts: set[str] = set()
    for window in blackouts:
        if window["symbol"] == "ALL":
            global_blackouts.add(window["start_date"])
        else:
            symbol_blackouts[(window["symbol"], window["blocks_strategy"])].add(window["start_date"])
    trade_count = 0
    kept_count = 0
    excluded_count = 0
    kept_pnl = 0.0
    excluded_pnl = 0.0
    for trade in iter_verified_trade_records(resolution):
        pnl = float(trade.get("path_pnl", 0.0))
        signal_date = str(trade.get("signal_date", ""))
        key = (
            str(trade.get("symbol", "")),
            str(trade.get("candidate_strategy", "")),
        )
        blocked = signal_date in global_blackouts or signal_date in symbol_blackouts.get(
            key, set()
        )
        trade_count += 1
        if blocked:
            excluded_count += 1
            excluded_pnl += pnl
        else:
            kept_count += 1
            kept_pnl += pnl
    if trade_count == 0:
        return {"filter_analysis_status": "blocked_empty_backtest_records"}
    return {
        "filter_analysis_status": "complete",
        "trades_total": trade_count,
        "trades_kept": kept_count,
        "trades_excluded": excluded_count,
        "net_pnl_unfiltered": round(kept_pnl + excluded_pnl, 6),
        "net_pnl_filtered": round(kept_pnl, 6),
        "net_pnl_excluded_trades": round(excluded_pnl, 6),
        "filter_improved_net": kept_pnl > kept_pnl + excluded_pnl,
        "average_excluded_trade_pnl": (
            round(excluded_pnl / excluded_count, 6) if excluded_count else 0.0
        ),
        "average_kept_trade_pnl": (
            round(kept_pnl / kept_count, 6) if kept_count else 0.0
        ),
        "backtest_trade_resolution_status": resolution["status"],
        "backtest_trade_source_sha256": resolution["source_sha256"],
        "backtest_trade_resolved_sha256": resolution["resolved_sha256"],
        "backtest_trade_incident_recovery_used": resolution[
            "incident_recovery_used"
        ],
        "backtest_trade_authoritative_evidence": resolution[
            "authoritative_evidence"
        ],
        "backtest_trade_verified_record_count": resolution[
            "verified_record_hash_count"
        ],
        "not_edge_evidence": True,
    }


def _write_report(summary: dict[str, Any]) -> None:
    filter_value = summary["filter_value"]
    lines = [
        "# DOPEY Market Structure Engine Report",
        "",
        "## Objective",
        "Deterministic market-structure, trap, and volatility-regime features over validated real history.",
        "",
        "## Feature Families",
        f"- swing levels: `{summary['swing_level_count']}` (k={SWING_FRACTAL_K} fractals, confirmation lag recorded)",
        f"- support/resistance zones: `{summary['sr_zone_count']}` (cluster tolerance {SR_CLUSTER_TOLERANCE_PCT:.1%})",
        f"- trap events: `{summary['trap_event_count']}` (bull `{summary['bull_trap_count']}` / bear `{summary['bear_trap_count']}`)",
        f"- volume anomalies: `{summary['volume_anomaly_count']}` (z >= {VOLUME_Z_THRESHOLD})",
        f"- VRP observations: `{summary['vrp_observation_count']}` (rich days: `{summary['vrp_rich_day_count']}`)",
        f"- entry blackout windows: `{summary['blackout_window_count']}`",
        "",
        "## Filter Value (blackouts applied to real trade records)",
        f"- status: `{filter_value.get('filter_analysis_status')}`",
        f"- trades excluded: `{filter_value.get('trades_excluded', 0)}` of `{filter_value.get('trades_total', 0)}`",
        f"- net P&L unfiltered: `{filter_value.get('net_pnl_unfiltered', 0.0)}`",
        f"- net P&L filtered: `{filter_value.get('net_pnl_filtered', 0.0)}`",
        f"- average excluded-trade P&L: `{filter_value.get('average_excluded_trade_pnl', 0.0)}`",
        f"- filter improved net: `{filter_value.get('filter_improved_net', False)}`",
        "",
        "## Honest Limits",
        "- Structure features are hypotheses, not edge evidence; arbitration happens in the truth layer.",
        "- VRP proxy uses VIX vs SPY realized variance; per-symbol implied vol requires real chains.",
        "- paper_only: `true`; live_blocked: `true`.",
    ]
    STRUCTURE_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
