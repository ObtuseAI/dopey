from __future__ import annotations

from pathlib import Path
from typing import cast

from dopey.technical.candle_intelligence import (
    detect_candlestick_patterns,
    detect_divergences,
)
from dopey_dashboard.chart_state import build_chart_state
from dopey_equity_swing.market_structure import Bar


def _bar(index: int, open_value: float, close: float, volume: int) -> Bar:
    return cast(
        Bar,
        {
            "date": f"2026-01-{index + 1:03d}",
            "open": open_value,
            "high": max(open_value, close) + 0.5,
            "low": min(open_value, close) - 0.5,
            "close": close,
            "volume": volume,
        },
    )


def _hidden_divergence_history() -> list[Bar]:
    closes: list[float] = []
    closes.extend(100.0 + index * 0.4 for index in range(30))
    closes.extend(111.6 - (index + 1) * 0.135 for index in range(10))
    closes.extend(110.25 + (index + 1) * 0.7375 for index in range(20))
    closes.extend(125.0 - (index + 1) * 2.0 for index in range(5))
    closes.extend(115.0 + (index + 1) * 0.7 for index in range(25))
    return [
        _bar(
            index,
            closes[index - 1] if index > 0 else close - 0.1,
            close,
            1_000_000 + index * 1_000,
        )
        for index, close in enumerate(closes)
    ]


def test_chart_state_uses_hash_pinned_real_history_and_all_versioned_indicators() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    chart = build_chart_state(repository_root, "SPY", "daily")

    assert len(chart["bars"]) == 180
    assert chart["indicator_count"] == 62
    assert chart["synthetic_data_used"] is False
    assert chart["network_fetch_performed"] is False
    assert chart["paper_only"] is True and chart["live_blocked"] is True
    assert chart["source_proof"]["symbol_validation_status"] == "valid_real_symbol_dataset"
    assert chart["grounded_structure_evidence"]["viewport_is_detector_input"] is False
    assert chart["grounded_structure_evidence"]["image_pixels_are_detector_input"] is False
    assert chart["grounded_structure_evidence"]["structure_count"] > 0
    assert chart["blind_replay_evidence"]["future_data_visible_during_frozen_detection"] is False
    assert chart["blind_replay_evidence"]["outcome"]["not_option_pnl_evidence"] is True


def test_candlestick_and_hidden_divergence_arsenal_emits_falsifiable_evidence() -> None:
    history = _hidden_divergence_history()
    prior = _bar(len(history), 130.0, 126.0, 1_200_000)
    engulfing = _bar(len(history) + 1, 125.0, 131.0, 1_300_000)

    candles = detect_candlestick_patterns([*history, prior, engulfing], 6)
    divergences = detect_divergences(history, 260)

    assert any(record["pattern"] == "bullish_engulfing" for record in candles)
    assert any(
        record["divergence_type"] == "hidden_bullish"
        and record["oscillator"] == "RSI"
        for record in divergences
    )
    assert all(record["pattern_is_not_truth"] is True for record in candles)
    assert all(record["not_trade_decision"] is True for record in divergences)
    assert all(record["failure_condition"] for record in [*candles, *divergences])
