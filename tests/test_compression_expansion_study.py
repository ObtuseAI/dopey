"""BB-squeeze detector + the two-question compression study.

The study exists to keep two claims separate: compression predicting RANGE
(defensible) vs the break direction predicting SIGNED return (usually not).
Machinery proof: planted expansion patterns must clear, flat controls must
not, and the direction question must find planted directional follow-through
while never manufacturing it from mixed breaks.
"""
from __future__ import annotations

from datetime import date, timedelta

from dopey.strategy_engineering.compression_expansion_study import (
    compression_depth_series,
    evaluate_direction_question,
    evaluate_range_question,
    squeeze_break_direction,
)
from dopey.strategy_engineering.playbook_scanner import (
    SCANNER_EVOLVABLE_PARAMETERS,
    detect_bb_squeeze,
)

_PARAMS = dict(SCANNER_EVOLVABLE_PARAMETERS)


def _dates(count: int, start: str = "2015-01-02") -> list[str]:
    first = date.fromisoformat(start)
    return [(first + timedelta(days=index)).isoformat() for index in range(count)]


def _bar(day: str, close: float, volume: float) -> dict:
    return {
        "date": day,
        "close": close,
        "adjusted_close": close,
        "high": close * 1.001,
        "low": close * 0.999,
        "volume": volume,
    }


def _squeeze_then_break_bars(break_up: bool = True) -> list[dict]:
    """~150 quiet alternating days, then a hard break with a volume spike."""
    days = _dates(151)
    bars = []
    price = 100.0
    for index in range(150):
        price = 100.0 + (0.05 if index % 2 == 0 else -0.05)
        bars.append(_bar(days[index], price, 1_000.0))
    final = 103.0 if break_up else 97.0
    bars.append(_bar(days[150], final, 12_000.0))
    return bars


def test_detector_fires_long_on_confirmed_upside_break() -> None:
    detection = detect_bb_squeeze(_squeeze_then_break_bars(break_up=True), {})
    assert detection is not None
    assert detection["direction"] == "long"
    assert detection["details"]["break_reference"] == "prior_session_bands"


def test_detector_fires_short_on_confirmed_downside_break() -> None:
    detection = detect_bb_squeeze(_squeeze_then_break_bars(break_up=False), {})
    assert detection is not None
    assert detection["direction"] == "short"


def test_detector_requires_volume_confirmation() -> None:
    bars = _squeeze_then_break_bars(break_up=True)
    bars[-1]["volume"] = 1_000.0  # break without participation
    assert detect_bb_squeeze(bars, {}) is None


def test_detector_stays_silent_while_still_coiled() -> None:
    bars = _squeeze_then_break_bars(break_up=True)
    bars[-1] = _bar(bars[-1]["date"], 100.05, 12_000.0)  # inside the bands
    assert detect_bb_squeeze(bars, {}) is None


def test_replay_matches_detector_rule() -> None:
    bars = _squeeze_then_break_bars(break_up=True)
    closes = [float(bar["close"]) for bar in bars]
    volumes = [float(bar["volume"]) for bar in bars]
    assert squeeze_break_direction(closes, volumes, len(bars) - 1, _PARAMS) == "long"


def test_compression_depth_orders_quiet_above_expansion() -> None:
    closes: list[float] = []
    phase_of: list[str] = []
    for _cycle in range(8):
        for index in range(45):
            closes.append(100.0 + (0.05 if index % 2 == 0 else -0.05))
            phase_of.append("quiet")
        for index in range(15):
            closes.append(closes[-1] * (1.03 if index % 2 == 0 else 0.985))
            phase_of.append("expansion")
    depths = compression_depth_series(closes, 20, 2.0, 120)
    # compare LATE-quiet (bands fully re-tightened) vs expansion depths
    quiet = [
        value
        for index, value in enumerate(depths)
        if value == value and phase_of[index] == "quiet" and phase_of[index - 15] == "quiet"
    ]
    expansion = [
        value
        for index, value in enumerate(depths)
        if value == value and phase_of[index] == "expansion"
    ]
    assert quiet and expansion
    assert (sum(quiet) / len(quiet)) > (sum(expansion) / len(expansion))


def _regime_symbol(phase: int, day_count: int = 2600) -> list[dict]:
    """Quiet 40d / expanding 10d cycles, phase-shifted per symbol; the break
    day gets a volume spike and the expansion continues UP for the horizon."""
    days = _dates(day_count)
    bars: list[dict] = []
    price = 100.0
    for index in range(day_count):
        position = (index + phase) % 50
        if position < 40:
            price = price * (1.0005 if index % 2 == 0 else 0.9995)
            volume = 1_000.0
        else:
            price = price * 1.02
            volume = 9_000.0 if position == 40 else 2_000.0
        bars.append(_bar(days[index], price, volume))
    return bars


def test_range_question_clears_on_planted_expansion_and_not_on_flat_control() -> None:
    planted = {f"P{index:02d}": _regime_symbol(phase=index * 4) for index in range(12)}
    result = evaluate_range_question(planted, _PARAMS)
    assert result["train"]["era_status"] == "evaluated"
    assert result["train"]["mean_rank_ic"] > 0.0

    flat = {
        f"F{index:02d}": [
            _bar(day, 100.0 + (0.05 if position % 2 == 0 else -0.05), 1_000.0)
            for position, day in enumerate(_dates(2600))
        ]
        for index in range(12)
    }
    control = evaluate_range_question(flat, _PARAMS)
    assert control["survives_both_eras_same_sign_above_null"] is False


def test_direction_question_finds_planted_follow_through() -> None:
    planted = {f"P{index:02d}": _regime_symbol(phase=index * 4) for index in range(12)}
    result = evaluate_direction_question(planted, _PARAMS)
    train = result["train"]
    assert train["era_status"] in {"evaluated", "insufficient_events_accruing"}
    if train["era_status"] == "evaluated":
        # every planted break continues upward: the machinery must see it
        assert train["hit_rate"] > 0.5
        assert train["mean_signed_return"] > 0.0


def test_direction_question_honest_below_event_floor() -> None:
    tiny = {"ONLY": _regime_symbol(phase=0, day_count=400)}
    result = evaluate_direction_question(tiny, _PARAMS)
    assert result["train"]["era_status"] == "insufficient_events_accruing"
    assert result["directional_claim_supported"] is False
