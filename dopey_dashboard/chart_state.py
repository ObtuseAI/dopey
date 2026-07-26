"""Read-only, provenance-bound chart intelligence for the desktop surface."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from dopey.chronos.clocks import ClockDomain, ClockStamp
from dopey.protocols.identity import canonical_hash
from dopey.technical.batch_a import calculate_indicator_series
from dopey.technical.evidence import build_timeframe_measurements
from dopey.technical.foundry import ALL_TECHNICAL_SPECS
from dopey.technical.history_adapter import load_validated_symbol_history
from dopey.technical.structure_patterns import build_structure_pattern_evidence
from dopey_chart_vision.grounded_structure_engine import (
    BLIND_REPLAY_VERSION,
    build_blind_replay_evidence,
    build_grounded_structure_evidence,
)
from dopey_equity_swing.market_structure import Bar, resample_bars


CHART_TIMEFRAMES: Final[tuple[str, ...]] = ("daily", "weekly", "monthly")
SYMBOL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9.\-]{1,12}$")
DISPLAY_BARS: Final[dict[str, int]] = {"daily": 180, "weekly": 156, "monthly": 120}
ANALYSIS_BARS: Final[dict[str, int]] = {"daily": 900, "weekly": 420, "monthly": 180}
REPLAY_REVEAL_BARS: Final[dict[str, int]] = {"daily": 5, "weekly": 4, "monthly": 3}


def _sma(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        output.append(None if index < period - 1 else running / period)
    return output


def _ema(values: Sequence[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    current = sum(values[:period]) / period
    output[period - 1] = current
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        current = alpha * values[index] + (1.0 - alpha) * current
        output[index] = current
    return output


def _bollinger(values: Sequence[float], period: int) -> tuple[list[float | None], list[float | None]]:
    upper: list[float | None] = []
    lower: list[float | None] = []
    for index in range(len(values)):
        if index < period - 1:
            upper.append(None)
            lower.append(None)
            continue
        window = values[index - period + 1 : index + 1]
        mean = sum(window) / period
        deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
        upper.append(mean + 2.0 * deviation)
        lower.append(mean - 2.0 * deviation)
    return upper, lower


def _anchored_vwap(rows: Sequence[Bar]) -> list[float | None]:
    output: list[float | None] = []
    active_year = ""
    numerator = 0.0
    denominator = 0.0
    for row in rows:
        year = str(row["date"])[:4]
        if year != active_year:
            active_year = year
            numerator = 0.0
            denominator = 0.0
        typical = (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3.0
        volume = float(row["volume"])
        numerator += typical * volume
        denominator += volume
        output.append(None if denominator <= 0.0 else numerator / denominator)
    return output


def _rounded_series(values: Sequence[float | None], offset: int) -> list[float | None]:
    return [None if value is None else round(float(value), 8) for value in values[offset:]]


def _chart_bars(rows: Sequence[Bar]) -> list[dict[str, object]]:
    return [
        {
            "date": str(row["date"]),
            "open": round(float(row["open"]), 8),
            "high": round(float(row["high"]), 8),
            "low": round(float(row["low"]), 8),
            "close": round(float(row["close"]), 8),
            "volume": int(row["volume"]),
        }
        for row in rows
    ]


def _clock(timeframe: str, as_of: str, data_version: str) -> ClockStamp:
    event_time = datetime.now(timezone.utc).isoformat()
    market_time = f"{as_of}T00:00:00+00:00"
    domain = {
        "daily": ClockDomain.DAILY,
        "weekly": ClockDomain.WEEKLY,
        "monthly": ClockDomain.MONTHLY,
    }[timeframe]
    return ClockStamp(
        domain=domain,
        event_time=event_time,
        market_time=market_time,
        data_version=data_version,
        agent_version="dopey-chart-intelligence-v1",
        policy_version="paper-research-only-v1",
        model_version="deterministic-technical-evidence-v1",
        parent_event_id="desktop-chart-request",
        session_id=f"chart-{as_of}",
    )


def _indicator_snapshot(measurements: Sequence[dict[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "indicator": str(record["indicator"]),
            "value": record.get("value"),
            "percentile": record.get("percentile"),
            "slope": record.get("slope"),
            "state": str(record.get("state", "unknown")),
            "reliability": record.get("reliability"),
            "limitations": list(record.get("limitations", [])),
        }
        for record in measurements
    ]


def build_chart_state(repository_root: Path, symbol: str, timeframe: str) -> dict[str, object]:
    """Build a bounded chart payload from the hash-pinned real-history manifest."""

    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip().lower()
    if SYMBOL_PATTERN.fullmatch(normalized_symbol) is None:
        raise ValueError(f"chart symbol is invalid: symbol={symbol!r}")
    if normalized_timeframe not in CHART_TIMEFRAMES:
        raise ValueError(
            "chart timeframe is unsupported: "
            f"timeframe={timeframe!r}, allowed={CHART_TIMEFRAMES}"
        )
    manifest_path = (
        repository_root.resolve()
        / "dopey_data"
        / "history"
        / "history_dataset_manifest.json"
    )
    daily_rows, proof = load_validated_symbol_history(normalized_symbol, manifest_path)
    resampled = resample_bars(daily_rows, normalized_timeframe)
    analysis_rows = resampled[-ANALYSIS_BARS[normalized_timeframe] :]
    if len(analysis_rows) < 60:
        raise ValueError(
            "chart history is insufficient for governed pattern analysis: "
            f"symbol={normalized_symbol}, timeframe={normalized_timeframe}, bars={len(analysis_rows)}"
        )
    as_of = str(analysis_rows[-1]["date"])
    data_version = str(proof["reproducibility_hash"])
    clock = _clock(normalized_timeframe, as_of, data_version)
    measurements = build_timeframe_measurements(
        normalized_symbol,
        normalized_timeframe,
        analysis_rows,
        clock,
        ALL_TECHNICAL_SPECS,
    )
    structure = build_structure_pattern_evidence(
        normalized_symbol,
        {normalized_timeframe: analysis_rows},
        clock,
    )[0]
    grounded_structures = build_grounded_structure_evidence(
        normalized_symbol,
        normalized_timeframe,
        analysis_rows,
        data_version,
    )
    reveal_bar_count = REPLAY_REVEAL_BARS[normalized_timeframe]
    if len(analysis_rows) - reveal_bar_count < 60:
        blind_replay: dict[str, object] = {
            "artifact_type": "grounded_blind_chart_replay",
            "schema_version": BLIND_REPLAY_VERSION,
            "replay_status": "blocked_invalid_replay_window",
            "available_bar_count": len(analysis_rows),
            "required_frozen_bar_count": 60,
            "requested_reveal_bar_count": reveal_bar_count,
            "paper_only": True,
            "live_blocked": True,
            "not_trade_decision": True,
            "not_edge_evidence": True,
        }
    else:
        blind_replay = build_blind_replay_evidence(
            normalized_symbol,
            normalized_timeframe,
            analysis_rows,
            data_version,
            reveal_bar_count,
        )
    closes = [float(row["close"]) for row in analysis_rows]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    ema20 = _ema(closes, 20)
    bollinger_upper, bollinger_lower = _bollinger(closes, 20)
    anchored_vwap = _anchored_vwap(analysis_rows)
    by_name = {spec.indicator: spec for spec in ALL_TECHNICAL_SPECS}
    rsi = calculate_indicator_series(by_name["RSI"], analysis_rows)
    macd = calculate_indicator_series(by_name["MACD_HISTOGRAM"], analysis_rows)
    display_count = min(DISPLAY_BARS[normalized_timeframe], len(analysis_rows))
    offset = len(analysis_rows) - display_count
    displayed_rows = analysis_rows[offset:]
    body: dict[str, object] = {
        "artifact_type": "desktop_chart_intelligence",
        "schema_version": "dopey-chart-intelligence-v1",
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "as_of": as_of,
        "bars": _chart_bars(displayed_rows),
        "overlays": {
            "sma20": _rounded_series(sma20, offset),
            "sma50": _rounded_series(sma50, offset),
            "ema20": _rounded_series(ema20, offset),
            "bollinger_upper": _rounded_series(bollinger_upper, offset),
            "bollinger_lower": _rounded_series(bollinger_lower, offset),
            "anchored_vwap": _rounded_series(anchored_vwap, offset),
        },
        "oscillators": {
            "rsi": _rounded_series(rsi, offset),
            "macd_histogram": _rounded_series(macd, offset),
        },
        "structure": structure["market_structure"],
        "geometric_patterns": structure["pattern_candidates"],
        "candlestick_patterns": structure["candlestick_patterns"],
        "divergences": structure["divergences"],
        "volume_profile": structure["volume_profile"],
        "regime_statistics": structure["regime_statistics"],
        "grounded_structure_evidence": grounded_structures,
        "blind_replay_evidence": blind_replay,
        "indicator_snapshot": _indicator_snapshot(measurements),
        "indicator_count": len(measurements),
        "pattern_family_count": len(structure["supported_pattern_families"]),
        "pattern_families": structure["supported_pattern_families"],
        "intraday_status": "not_requested_daily_history_only",
        "source_proof": proof,
        "patterns_are_probabilistic_not_truth": True,
        "synthetic_data_used": False,
        "network_fetch_performed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_trade_decision": True,
    }
    return {**body, "content_hash": canonical_hash(body)}
