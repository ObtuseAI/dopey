"""Mahomes layer: Release-Angle Selector + Post-Snap Read.

The selector must sweep the expression grid honestly (surviving cells only
when net > 0; a big edge finds survivors, a tiny one finds none). The
post-snap read must flag context rotation into AVOID buckets and family flips
- strictly advisory, exits stay mechanical.
"""
from __future__ import annotations

from datetime import date, timedelta

from dopey.strategy_engineering.expression_selector import evaluate_expression_grid
from dopey.strategy_engineering.post_snap_read import (
    build_post_snap_reads,
    rediagnose_position,
)


# ---------- Release-Angle Selector ----------


def test_tiny_edge_survives_nowhere() -> None:
    grid = evaluate_expression_grid(0.002, iv=0.30)
    assert grid["any_expression_survives"] is False
    assert grid["surviving_cells"] == []
    assert grid["promotion_allowed"] is False


def test_large_edge_finds_surviving_angles() -> None:
    grid = evaluate_expression_grid(0.05, iv=0.30)
    assert grid["any_expression_survives"] is True
    assert len(grid["surviving_cells"]) > 0
    # the best cell is the max net return and must be a surviving one
    best = grid["best_release_angle"]
    assert best["net_return_at_excess"] >= max(c["net"] for c in grid["surviving_cells"]) - 1e-9


def test_grid_covers_dte_and_moneyness() -> None:
    grid = evaluate_expression_grid(0.01, iv=0.30)
    priced = [c for c in grid["cells"] if c.get("cell_status") == "priced"]
    assert len(priced) == 16  # 4 DTE x 4 moneyness
    assert {c["dte_days"] for c in priced} == {14, 30, 60, 90}


def test_itm_breakeven_smaller_than_otm_short_dated() -> None:
    # at 14 DTE, the deep-ITM release needs a smaller move than the OTM one
    grid = evaluate_expression_grid(0.00616, iv=0.30)
    by_cell = {(c["dte_days"], c["moneyness"]): c for c in grid["cells"] if c.get("cell_status") == "priced"}
    assert by_cell[(14, 0.90)]["breakeven_underlying_move"] < by_cell[(14, 1.05)]["breakeven_underlying_move"]


# ---------- Post-Snap Read ----------


def _spine_rotating(stretch_now: bool) -> dict[str, tuple[list[float], list[str]]]:
    # 30 warm-up days at 100; entry day near; then optionally rotate stretched
    closes = [100.0] * 31
    dates = [(date(2020, 1, 1) + timedelta(days=i)).isoformat() for i in range(33)]
    closes.append(100.4)                       # entry day: near
    closes.append(112.0 if stretch_now else 100.5)  # frontier: rotated or not
    return {"NVDA": (closes, dates)}


def _scorecard_avoid_stretched(family: str = "momentum"):
    return {"situations": [
        {"family": family, "entry_context": "stretched_above", "call": "avoid_strong"},
        {"family": family, "entry_context": "near", "call": "neutral_monitor"},
    ]}


def _position():
    return {"position_id": "p1", "symbol": "NVDA", "signal_family": "momentum",
            "entry_date": (date(2020, 1, 1) + timedelta(days=31)).isoformat()}


def test_rotation_into_avoid_is_scramble_alert() -> None:
    read = rediagnose_position(
        _position(), _spine_rotating(stretch_now=True), _scorecard_avoid_stretched(),
        {"families": []}, (date(2020, 1, 1) + timedelta(days=32)).isoformat(),
    )
    assert read["entry_context"] == "near"
    assert read["current_context"] == "stretched_above"
    assert read["call"] == "scramble_alert"


def test_rotation_plus_family_flip_is_broken_play() -> None:
    convergence = {"families": [{"family": "momentum_continuation", "verdict": "contested_lanes_disagree"}]}
    read = rediagnose_position(
        _position(), _spine_rotating(stretch_now=True), _scorecard_avoid_stretched(),
        convergence, (date(2020, 1, 1) + timedelta(days=32)).isoformat(),
    )
    assert read["call"] == "broken_play_alert"


def test_unchanged_benign_look_is_on_schedule() -> None:
    read = rediagnose_position(
        _position(), _spine_rotating(stretch_now=False), _scorecard_avoid_stretched(),
        {"families": []}, (date(2020, 1, 1) + timedelta(days=32)).isoformat(),
    )
    assert read["call"] == "on_schedule"


def test_batch_is_advisory_only() -> None:
    result = build_post_snap_reads(
        [_position()], _spine_rotating(stretch_now=True), _scorecard_avoid_stretched(),
        {"families": []}, (date(2020, 1, 1) + timedelta(days=32)).isoformat(),
    )
    assert result["call_counts"].get("scramble_alert") == 1
    assert "STRICTLY ADVISORY" in result["exit_policy_note"]
    assert result["promotion_allowed"] is False
