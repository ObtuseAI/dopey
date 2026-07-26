"""Held-out scanner-parameter fitness - the 3rd evolvable surface, wired.

Machinery proof: a planted directional pattern (breakouts that reliably
continue) must produce positive held-out excess; a random-walk control must
not; and below the event floor the measurement is invalid (never a score).
Held-out only, point-in-time, deflated by detector breadth.
"""
from __future__ import annotations

import pytest

import dopey.strategy_engineering.scanner_holdout_fitness as scanner_fitness
from dopey.strategy_engineering.scanner_holdout_fitness import (
    FORWARD_HORIZON,
    MIN_EVENTS,
    _matured_drift_observation,
    _select_symbols,
    evaluate_scanner_holdout,
)


def _bars(symbol: str, closes: list[float], start_year: int = 2016) -> list[dict]:
    # dense daily dates well into the held-out era (> 2021-12-31)
    from datetime import date, timedelta

    day = date(start_year, 1, 2)
    out = []
    for close in closes:
        out.append(
            {
                "date": day.isoformat(),
                "symbol": symbol,
                "open": close,
                "close": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "volume": 1_000_000,
            }
        )
        day = day + timedelta(days=1)
    return out


def _planted_breakout_series(length: int) -> list[float]:
    # ascending staircase: a 60-day flat base, a decisive breakout to a new
    # high, then 5 days of concentrated continuation ABOVE the ambient drift,
    # then a new higher base. A channel-breakout detector fires on the
    # breakout day and captures the concentrated move; a short-term-reversal
    # detector fires against it and loses - the settlement must reward the
    # former and penalize the latter.
    closes: list[float] = []
    level = 100.0
    while len(closes) < length:
        for _ in range(60):
            closes.append(level + (0.05 if len(closes) % 2 == 0 else -0.05))
        breakout = level * 1.08
        closes.append(breakout)
        for step in range(5):
            closes.append(breakout * (1.0 + 0.015 * (step + 1)))
        level = breakout * 1.08
    return closes[:length]


def _random_walk(length: int, seed: int) -> list[float]:
    # deterministic pseudo-random walk (no numpy, no Math.random)
    closes = [100.0]
    state = seed
    for _ in range(length - 1):
        state = (1103515245 * state + 12345) % 2147483648
        step = (state / 2147483648) - 0.5
        closes.append(max(1.0, closes[-1] * (1.0 + 0.02 * step)))
    return closes


def test_planted_continuation_rewards_the_right_detector() -> None:
    bars_by_symbol = {
        f"P{index:02d}": _bars(f"P{index:02d}", _planted_breakout_series(2800))
        for index in range(12)
    }
    result = evaluate_scanner_holdout(bars_by_symbol, symbol_cap=12, stride=3)
    assert result["sample_sufficient"] is True
    assert result["holdout_events"] >= MIN_EVENTS
    per = result["per_detector"]
    # the breakout detector, which fires on the continuation, must earn
    # positive held-out excess...
    assert per["channel_breakout"]["mean_excess"] > 0.0
    # ...while a detector that fires AGAINST the same moves must be penalized
    assert per["short_term_reversal"]["mean_excess"] < 0.0


def test_random_walk_is_not_rewarded() -> None:
    bars_by_symbol = {
        f"R{index:02d}": _bars(f"R{index:02d}", _random_walk(2800, seed=index * 7 + 1))
        for index in range(12)
    }
    result = evaluate_scanner_holdout(bars_by_symbol, symbol_cap=12, stride=3)
    # a random walk must not manufacture a strong positive edge
    assert result["mean_excess_over_drift"] < 0.01


def test_insufficient_sample_is_invalid_not_zero() -> None:
    bars_by_symbol = {"ONE": _bars("ONE", _planted_breakout_series(400))}
    result = evaluate_scanner_holdout(bars_by_symbol, symbol_cap=40, stride=5)
    assert result["sample_sufficient"] is False


def test_deflation_penalizes_detector_breadth() -> None:
    bars_by_symbol = {
        f"P{index:02d}": _bars(f"P{index:02d}", _planted_breakout_series(2800))
        for index in range(12)
    }
    result = evaluate_scanner_holdout(bars_by_symbol, symbol_cap=12, stride=3)
    # deflated excess is never larger in magnitude than the raw mean excess
    assert abs(result["deflated_mean_excess"]) <= abs(result["mean_excess_over_drift"]) + 1e-9


def test_only_holdout_era_is_scored() -> None:
    # all bars BEFORE the train_end split -> zero held-out events
    bars_by_symbol = {
        f"T{index:02d}": _bars(f"T{index:02d}", _planted_breakout_series(1000), start_year=2012)
        for index in range(12)
    }
    result = evaluate_scanner_holdout(bars_by_symbol, symbol_cap=12, stride=3)
    assert result["holdout_events"] == 0
    assert result["sample_sufficient"] is False


def test_drift_baseline_uses_only_fully_matured_windows() -> None:
    dates = [f"2022-01-{day:02d}" for day in range(1, 15)]
    closes = [100.0] * len(dates)
    closes[FORWARD_HORIZON] = 110.0
    closes[FORWARD_HORIZON + 1] = 1_000.0

    assert (
        _matured_drift_observation(
            closes,
            dates,
            FORWARD_HORIZON - 1,
        )
        is None
    )
    observation = _matured_drift_observation(
        closes,
        dates,
        FORWARD_HORIZON,
    )
    assert observation is not None
    assert round(observation, 6) == 0.1

    result = evaluate_scanner_holdout(
        {
            "PIT": _bars(
                "PIT",
                _planted_breakout_series(2_800),
            )
        },
        symbol_cap=1,
        stride=5,
    )
    assert result["drift_baseline_policy"] == (
        "point_in_time_only_fully_matured_forward_windows"
    )


def test_symbol_cap_is_hash_spread_not_alphabetical_prefix() -> None:
    available = [f"S{index:03d}" for index in range(100)]

    selected = _select_symbols(available, 20)

    assert selected == _select_symbols(list(reversed(available)), 20)
    assert set(selected) != set(sorted(available)[:20])


def test_detector_exceptions_invalidate_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_detector(
        bars: list[dict],
        context: dict,
    ) -> None:
        del bars, context
        raise RuntimeError("detector failure")

    monkeypatch.setattr(
        scanner_fitness,
        "SELF_CONTAINED_DIRECTIONAL",
        {"broken": broken_detector},
    )
    result = evaluate_scanner_holdout(
        {"FAIL": _bars("FAIL", _planted_breakout_series(2_800))},
        symbol_cap=1,
        stride=50,
    )

    assert result["sample_sufficient"] is False
    assert result["detector_exception_count"] > 0
    assert result["detector_exception_counts"]["broken:RuntimeError"] > 0
    assert (
        result["detector_exception_budget_status"]
        == "breached_measurement_invalid"
    )


def test_pooled_fitness_deduplicates_cofired_symbol_date_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_long(
        bars: list[dict],
        context: dict,
    ) -> dict[str, object]:
        del bars, context
        return {
            "direction": "long",
            "strength": 1.0,
            "details": {},
        }

    monkeypatch.setattr(
        scanner_fitness,
        "SELF_CONTAINED_DIRECTIONAL",
        {
            "cofire_a": always_long,
            "cofire_b": always_long,
            "cofire_c": always_long,
        },
    )
    bars_by_symbol = {
        "COFIRE": _bars(
            "COFIRE",
            _planted_breakout_series(2_800),
        )
    }

    result = evaluate_scanner_holdout(
        bars_by_symbol,
        symbol_cap=1,
        stride=5,
    )

    assert result["holdout_event_unit"] == "unique_symbol_date"
    assert result["raw_detector_events"] == 3 * result["holdout_events"]
    assert result["cofired_detector_event_duplicates"] == (
        result["raw_detector_events"] - result["holdout_events"]
    )
    assert result["event_deduped_mean_excess_over_drift"] == (
        result["mean_excess_over_drift"]
    )
    assert (
        result["event_deduplication_policy_version"]
        == "symbol-date-mean-cofire-v1"
    )
    assert (
        result["drift_baseline_policy_version"]
        == "point-in-time-matured-forward-windows-v2"
    )
    assert len(result["source_universe_hash"]) == 64
    assert (
        result["source_hash_policy_version"]
        == "selected-symbol-bars-sha256-v1"
    )
